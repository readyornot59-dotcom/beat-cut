import shutil
import uuid
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from runwayml import APIError as RunwayAPIError
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ai_video import generate_scene_clips
from beat_detection import detect_beats
from video_cutter import cut_to_beats

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="beat-cut")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _save_upload(upload: UploadFile, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{uuid.uuid4().hex}_{upload.filename}"
    with dest_path.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    return dest_path


def _process_job(job_id: str, work_dir: Path, music_path: Path, clip_paths: List[str]) -> dict:
    tempo, beat_times = detect_beats(str(music_path))
    if len(beat_times) < 2:
        raise HTTPException(status_code=422, detail="Could not detect enough beats in the music track")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{job_id}.mp4"
    cut_to_beats(
        clips=clip_paths,
        beat_times=beat_times,
        music_path=str(music_path),
        output_path=str(output_path),
        work_dir=str(work_dir),
    )

    return {
        "job_id": job_id,
        "tempo": tempo,
        "num_beats": len(beat_times),
        "download_url": f"/api/output/{job_id}.mp4",
    }


@app.post("/api/cut")
async def cut(music: UploadFile = File(...), clips: List[UploadFile] = File(...)):
    if not clips:
        raise HTTPException(status_code=400, detail="At least one video clip is required")

    job_id = uuid.uuid4().hex
    job_dir = UPLOADS_DIR / job_id

    music_path = _save_upload(music, job_dir)
    clip_paths = [str(_save_upload(clip, job_dir)) for clip in clips]

    try:
        return _process_job(job_id, job_dir / "work", music_path, clip_paths)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


@app.post("/api/cut-ai")
async def cut_ai(music: UploadFile = File(...), prompt: str = Form(...), num_scenes: int = Form(4)):
    prompt = prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")
    if not (1 <= num_scenes <= 8):
        raise HTTPException(status_code=400, detail="num_scenes must be between 1 and 8")

    job_id = uuid.uuid4().hex
    job_dir = UPLOADS_DIR / job_id
    work_dir = job_dir / "work"

    music_path = _save_upload(music, job_dir)

    try:
        ai_clip_paths = generate_scene_clips(
            prompt=prompt, num_scenes=num_scenes, work_dir=str(work_dir / "ai_clips")
        )
        return _process_job(job_id, work_dir, music_path, ai_clip_paths)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except RunwayAPIError as e:
        raise HTTPException(status_code=502, detail=f"Runway API error: {e.message}")
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


@app.get("/api/output/{filename}")
async def get_output(filename: str):
    path = OUTPUT_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Output not found")
    return FileResponse(path, media_type="video/mp4", filename=filename)


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
