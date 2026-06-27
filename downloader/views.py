"""
Views for the video downloader.

Design note for serverless (Vercel):
    Proxying a full video file through a serverless function is a bad idea —
    functions have short timeouts and limited memory/bandwidth. So the primary
    strategy here is to use yt-dlp purely as a *metadata extractor*: we resolve
    the list of available formats and their direct CDN URLs, then hand those
    URLs to the user's browser, which downloads straight from the source.

    For formats that do not expose a single direct URL (e.g. fragmented
    HLS/DASH manifests), a best-effort server-side streaming fallback is
    offered, with the caveat that it can hit the function timeout for large
    files. Run on a host without that limit for reliable large downloads.
"""
from __future__ import annotations

import re

from django.conf import settings
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

try:
    import yt_dlp
except ImportError:  # pragma: no cover - yt_dlp is a hard dependency
    yt_dlp = None


# Accept only http(s) URLs to avoid yt-dlp touching local files / odd schemes.
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _human_size(num_bytes):
    if not num_bytes:
        return ""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}".replace(".0 ", " ")
        size /= 1024
    return ""


def _extract_info(url):
    """Return yt-dlp's info dict for *url* without downloading anything."""
    if yt_dlp is None:
        raise RuntimeError("yt-dlp is not installed on the server.")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": settings.YTDLP_TIMEOUT,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)


def _build_formats(info):
    """Flatten yt-dlp formats into template-friendly dicts."""
    formats = []
    for fmt in info.get("formats", []) or []:
        vcodec = fmt.get("vcodec")
        acodec = fmt.get("acodec")
        has_video = vcodec not in (None, "none")
        has_audio = acodec not in (None, "none")
        if not has_video and not has_audio:
            continue

        if has_video and has_audio:
            kind = "Video + Audio"
        elif has_video:
            kind = "Video only"
        else:
            kind = "Audio only"

        height = fmt.get("height")
        resolution = fmt.get("resolution") or (f"{height}p" if height else "")
        size = fmt.get("filesize") or fmt.get("filesize_approx")

        formats.append(
            {
                "format_id": fmt.get("format_id"),
                "ext": fmt.get("ext", ""),
                "kind": kind,
                "resolution": resolution or "—",
                "fps": fmt.get("fps") or "",
                "note": fmt.get("format_note", ""),
                "size": _human_size(size),
                # A direct, fetchable URL (None for fragmented streams).
                "direct_url": fmt.get("url") if fmt.get("protocol") in
                ("https", "http") else None,
                "tbr": fmt.get("tbr") or 0,
            }
        )

    # Best/highest-bitrate first.
    formats.sort(key=lambda f: f["tbr"], reverse=True)
    return formats


@require_GET
def index(request):
    return render(request, "downloader/index.html")


@require_POST
def formats(request):
    url = (request.POST.get("url") or "").strip()
    if not _URL_RE.match(url):
        return render(
            request,
            "downloader/index.html",
            {"error": "Please enter a valid http(s) video URL.", "url": url},
        )

    try:
        info = _extract_info(url)
    except Exception as exc:  # yt-dlp raises a variety of error types
        message = str(exc).splitlines()[0] if str(exc) else "Extraction failed."
        return render(
            request,
            "downloader/index.html",
            {"error": f"Could not read that URL: {message}", "url": url},
        )

    context = {
        "url": url,
        "title": info.get("title", "video"),
        "uploader": info.get("uploader", ""),
        "duration": info.get("duration_string", ""),
        "thumbnail": info.get("thumbnail", ""),
        "formats": _build_formats(info),
    }
    return render(request, "downloader/formats.html", context)


@require_GET
def download(request):
    """
    Resolve the chosen format for *url* and deliver the file.

    If the format exposes a direct CDN URL we simply redirect the browser to
    it (fast, no server bandwidth). Otherwise we fall back to streaming the
    bytes through the server, which may time out on serverless for big files.
    """
    url = (request.GET.get("url") or "").strip()
    format_id = (request.GET.get("format_id") or "").strip()
    if not _URL_RE.match(url) or not format_id:
        return HttpResponseBadRequest("Missing or invalid url/format_id.")

    try:
        info = _extract_info(url)
    except Exception as exc:
        return HttpResponseBadRequest(f"Extraction failed: {exc}")

    chosen = None
    for fmt in info.get("formats", []) or []:
        if str(fmt.get("format_id")) == format_id:
            chosen = fmt
            break
    if chosen is None:
        return HttpResponseBadRequest("That format is no longer available.")

    title = re.sub(r"[^\w\-. ]", "_", info.get("title", "video")).strip() or "video"
    ext = chosen.get("ext", "mp4")
    filename = f"{title}.{ext}"

    direct_url = chosen.get("url")
    protocol = chosen.get("protocol", "")
    if direct_url and protocol in ("https", "http"):
        # Hand off straight to the CDN — best for serverless.
        return redirect(direct_url)

    # Fragmented stream (HLS/DASH); attempt a server-side proxy stream.
    return _stream_through_server(direct_url or url, filename)


def _stream_through_server(media_url, filename):
    import urllib.request

    try:
        upstream = urllib.request.urlopen(media_url, timeout=settings.YTDLP_TIMEOUT)
    except Exception as exc:
        return HttpResponseBadRequest(
            "This format has no direct download URL and could not be proxied "
            f"({exc}). Try a different (progressive) format."
        )

    def chunks():
        while True:
            data = upstream.read(64 * 1024)
            if not data:
                break
            yield data

    response = StreamingHttpResponse(
        chunks(), content_type="application/octet-stream"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@require_GET
def healthz(request):
    version = None
    if yt_dlp is not None:
        try:
            from yt_dlp.version import __version__ as version
        except Exception:
            version = getattr(yt_dlp, "__version__", None)
    return JsonResponse({"status": "ok", "yt_dlp": version})
