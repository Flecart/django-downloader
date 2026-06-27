# 🎬 Django Video Downloader

A minimal Django web app that resolves and downloads videos from Dailymotion,
Vimeo, and the hundreds of other sites supported by
[yt-dlp](https://github.com/yt-dlp/yt-dlp). Configured to deploy on
[Vercel](https://vercel.com).

Paste a URL → pick a format/quality → download.

## How it works

You paste a URL, the app lists the available formats, and on download yt-dlp
fetches the media **server-side** — stitching the fragments of an HLS/DASH
stream (how Dailymotion, Vimeo, etc. serve video) into a single playable file
in a temp dir, which is then streamed back to your browser as an attachment and
cleaned up. A static `ffmpeg` (via `imageio-ffmpeg`) is bundled so muxing works
on hosts without a system ffmpeg.

> **Serverless caveat:** This pulls the whole file through the function, which
> on Vercel has a short timeout and ephemeral `/tmp`. Short clips download fine;
> long or large videos can exceed the function timeout. For reliable downloads
> of big videos, self-host (see *Local development* below) where there is no
> timeout limit.

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
