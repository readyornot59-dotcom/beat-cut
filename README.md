# beat-cut

Auto-cuts video clips to the beat of a music track.

## Run

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cd backend && ../venv/bin/uvicorn main:app --reload
```

Open http://localhost:8000, upload a music file and one or more video clips.

## How it works

1. `backend/beat_detection.py` — uses librosa to find beat timestamps in the music.
2. `backend/video_cutter.py` — cuts the video clips (round-robin) into segments matching
   the gaps between beats, concatenates them via ffmpeg, and muxes in the music as audio.
3. `backend/main.py` — FastAPI endpoint (`POST /api/cut`) tying it together, plus a static
   file server for `frontend/`.

Requires `ffmpeg` on PATH.
