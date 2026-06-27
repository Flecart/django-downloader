"""
Views for the video downloader.

How downloading works:
    Most sites (Dailymotion, Vimeo, …) serve video as fragmented HLS/DASH —
    there is no single progressive file to hand to the browser. A naive
    "redirect to the media URL" only gives you the tiny .m3u8 *manifest*, not
    the video. So we let yt-dlp do the real work: it downloads and stitches the
    fragments into a single playable file in a temp dir, and we stream that file
    back to the browser as an attachment, cleaning up afterwards.

Serverless (Vercel) caveat:
    This pulls the whole file through the function, which has a short timeout
    and ephemeral /tmp. Short clips work; long/large videos can exceed the
    timeout. For reliable downloads of big videos, self-host (no timeout limit).
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile

from django.conf import settings
from django.http import (
    HttpResponseBadRequest,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .version import __version__

try:
    import yt_dlp
except ImportError:  # pragma: no cover - yt_dlp is a hard dependency
    yt_dlp = None


def _ffmpeg_location():
    """Path to a usable ffmpeg, or None.

    Prefer a pip-installed static binary (imageio-ffmpeg) so muxing works on
    hosts without a system ffmpeg, such as Vercel. Returning None is fine for
    combined HLS streams, which yt-dlp can stitch natively without ffmpeg.
    """
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


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
                # Stable identifier used at download time (format ids can drift
                # between requests for HLS, where they encode the bitrate).
                "height": height or "",
                "video_only": has_video and not has_audio,
                "fps": fmt.get("fps") or "",
                "note": fmt.get("format_note", ""),
                "size": _human_size(size),
                "tbr": fmt.get("tbr") or 0,
            }
        )

    # Best/highest-bitrate first.
    formats.sort(key=lambda f: f["tbr"], reverse=True)
    return formats


@require_GET
def index(request):
    return render(request, "downloader/index.html")


@require_GET
def formats(request):
    url = (request.GET.get("url") or "").strip()
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


def _format_selector(format_id, height, video_only):
    """Build a resilient yt-dlp format selector.

    Prefer the exact format id, but fall back to "best at this resolution" —
    HLS format ids encode the bitrate and can drift slightly between requests,
    so an exact-id-only match fails intermittently. Video-only formats are
    paired with the best audio (yt-dlp merges them with ffmpeg).
    """
    if height.isdigit():
        h = int(height)
        if video_only:
            return f"{format_id}+ba/bv*[height<={h}]+ba/b[height<={h}]/b"
        return f"{format_id}/b[height<={h}]/b[height<={h}]/b"
    # No height (e.g. audio-only) — fall back to best audio, then best overall.
    return f"{format_id}/ba/b"


@require_GET
def download(request):
    """Download the chosen format server-side and stream the file to the user.

    yt-dlp fetches and stitches the (usually fragmented HLS/DASH) media into a
    single playable file in a temp dir; we stream that back as an attachment
    and delete the temp dir once streaming finishes.
    """
    if yt_dlp is None:
        return HttpResponseBadRequest("yt-dlp is not installed on the server.")

    url = (request.GET.get("url") or "").strip()
    format_id = (request.GET.get("format_id") or "").strip()
    height = (request.GET.get("height") or "").strip()
    video_only = request.GET.get("video_only") == "1"
    if not _URL_RE.match(url) or not format_id:
        return HttpResponseBadRequest("Missing or invalid url/format_id.")

    selector = _format_selector(format_id, height, video_only)
    tmpdir = tempfile.mkdtemp(prefix="ytdl-")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "format": selector,
        "outtmpl": os.path.join(tmpdir, "%(title)s.%(ext)s"),
        "restrictfilenames": True,
        "merge_output_format": "mp4",
    }
    ffmpeg = _ffmpeg_location()
    if ffmpeg:
        ydl_opts["ffmpeg_location"] = ffmpeg

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as exc:
        shutil.rmtree(tmpdir, ignore_errors=True)
        message = str(exc).splitlines()[-1] if str(exc) else "Download failed."
        return HttpResponseBadRequest(f"Download failed: {message}")

    files = [
        os.path.join(tmpdir, f)
        for f in os.listdir(tmpdir)
        if os.path.isfile(os.path.join(tmpdir, f))
    ]
    if not files:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return HttpResponseBadRequest("Download produced no file.")

    # yt-dlp named the file after the video title; use that as the download name.
    path = max(files, key=os.path.getsize)
    filename = os.path.basename(path)
    return _stream_file(path, tmpdir, filename)


def _stream_file(path, tmpdir, filename):
    """Stream *path* as a download, removing *tmpdir* when finished."""
    size = os.path.getsize(path)

    def chunks():
        try:
            with open(path, "rb") as fh:
                while True:
                    data = fh.read(256 * 1024)
                    if not data:
                        break
                    yield data
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    response = StreamingHttpResponse(
        chunks(), content_type="application/octet-stream"
    )
    response["Content-Length"] = str(size)
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
    return JsonResponse(
        {"status": "ok", "version": __version__, "yt_dlp": version}
    )
