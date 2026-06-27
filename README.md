# 🎬 Django Video Downloader

A minimal Django web app that resolves and downloads videos from Dailymotion,
Vimeo, and the hundreds of other sites supported by
[yt-dlp](https://github.com/yt-dlp/yt-dlp). Configured to deploy on
[Vercel](https://vercel.com).

Paste a URL → pick a format/quality → download.

## How it works

The app uses yt-dlp purely as a **metadata extractor**. It lists the available
formats and, when a format exposes a direct CDN URL, redirects your browser to
download straight from the source. This keeps it fast and avoids proxying large
files through the server.

> **Serverless caveat:** Vercel functions have a max duration (60s here) and no
> persistent disk. Direct-URL formats (progressive MP4) download fine because
> the browser fetches from the CDN. Fragmented HLS/DASH streams that require
> server-side muxing (and ffmpeg) will not work reliably on Vercel — for those,
> run this app on a normal host (see *Local / self-hosted* below).

## Local development

This project uses [uv](https://docs.astral.sh/uv/) to manage the environment:

```bash
uv sync                       # create .venv and install deps from pyproject.toml
uv run python manage.py runserver
```

Open http://127.0.0.1:8000.

> **Why is there still a `requirements.txt`?** Vercel's serverless Python
> builder installs dependencies from `requirements.txt`, not from uv /
> `pyproject.toml`. So `requirements.txt` is a generated lock artifact — keep it
> in sync after changing dependencies:
>
> ```bash
> uv export --no-hashes --no-dev --no-emit-project -o requirements.txt
> ```

## Deploy to Vercel

1. Push this repo to GitHub.
2. Import it in the Vercel dashboard (or run `vercel`).
3. (Optional) environment variables — none are required. The app is a public,
   stateless tool with no logins or sessions, so it runs with zero config. You
   may optionally set `DJANGO_SECRET_KEY` (any random string) to override the
   built-in default, but it does not affect who can access the site.
4. Deploy. Vercel auto-detects the Python function at `api/index.py`, installs
   `requirements.txt`, and routes all traffic to the WSGI app (see
   `vercel.json`).

Static files are served by WhiteNoise in finders mode, so no `collectstatic`
build step is needed.

## Configuration

| Env var             | Default               | Purpose                              |
|---------------------|-----------------------|--------------------------------------|
| `DJANGO_SECRET_KEY` | dev key (insecure)    | Django secret key                    |
| `DJANGO_DEBUG`      | `False`               | Enable Django debug mode             |
| `YTDLP_TIMEOUT`     | `30`                  | Socket timeout for extraction (sec)  |

## Legal

For personal, offline viewing only. Respect content creators' rights and each
site's Terms of Service. Do not redistribute copyrighted content.
