# Viral Cut AI — starter MVP

## What works
- Upload video from mobile/desktop.
- Import URLs supported by `yt-dlp` (not literally every platform; DRM, private, login-gated and unsupported links will fail).
- Render multiple vertical/square/wide MP4 clips with FFmpeg.
- Optional speech-to-text SRT captions using Faster-Whisper.
- Local persistent output folder (`DATA_DIR`).

## Important limitations
This is a deployable starter, not a hosted service. No server or database is hosted by ChatGPT. The highlight picker is currently a simple evenly-spaced heuristic, not a trained viral-moment AI. SRT is a separate subtitle file; the current MVP does not burn styled captions into the video or provide a full timeline/photo editor. A production service needs authenticated users, object storage, job queue, database, GPU/CPU workers, platform-specific permissions, and abuse/copyright controls.

## Run locally
Requires Python 3.11+ and FFmpeg installed.
```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```
Open http://localhost:8000

## Docker
```bash
docker build -t viral-cut-ai .
docker run --rm -p 8000:8000 -v viral-data:/data viral-cut-ai
```
For public deployment use a server with persistent storage and enough disk/CPU. Set `DATA_DIR=/data`.
\n## Mobile\nThe interface is responsive and includes a basic installable PWA shell. On Android Chrome, open the deployed HTTPS URL and use the browser menu → Add to Home screen. Video processing still requires the backend server to be running; the PWA shell does not process videos offline.\n