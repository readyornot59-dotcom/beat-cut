import shutil
import uuid
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from runwayml import APIError as RunwayAPIError

import jobs
from ai_video import generate_scene_clips
from beat_detection import detect_beats
from video_cutter import concat_and_mux, cut_to_beats
from visualizer import cut_visualizer_to_beats

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


def _run_cut_job(job_id: str, job_dir: Path, work_dir: Path, music_path: Path, clip_paths: List[str]) -> None:
    on_progress = lambda stage, current, total: jobs.update_progress(job_id, stage, current, total)
    try:
        jobs.update_progress(job_id, "detecting_beats")
        tempo, beat_times = detect_beats(str(music_path))
        if len(beat_times) < 2:
            jobs.mark_error(job_id, "Could not detect enough beats in the music track")
            return

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / f"{job_id}.mp4"
        cut_to_beats(
            clips=clip_paths,
            beat_times=beat_times,
            music_path=str(music_path),
            output_path=str(output_path),
            work_dir=str(work_dir),
            on_progress=on_progress,
        )
        jobs.mark_done(job_id, tempo, len(beat_times), f"/api/output/{job_id}.mp4")
    except RuntimeError as e:
        jobs.mark_error(job_id, str(e))
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def _run_cut_ai_job(job_id: str, job_dir: Path, work_dir: Path, music_path: Path, prompts: List[str], num_scenes: int) -> None:
    on_progress = lambda stage, current, total: jobs.update_progress(job_id, stage, current, total)
    try:
        ai_clip_paths = generate_scene_clips(
            prompts=prompts, num_scenes=num_scenes, work_dir=str(work_dir / "ai_clips"), on_progress=on_progress
        )

        jobs.update_progress(job_id, "detecting_beats")
        tempo, beat_times = detect_beats(str(music_path))
        if len(beat_times) < 2:
            jobs.mark_error(job_id, "Could not detect enough beats in the music track")
            return

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / f"{job_id}.mp4"
        cut_to_beats(
            clips=ai_clip_paths,
            beat_times=beat_times,
            music_path=str(music_path),
            output_path=str(output_path),
            work_dir=str(work_dir),
            on_progress=on_progress,
        )
        jobs.mark_done(job_id, tempo, len(beat_times), f"/api/output/{job_id}.mp4")
    except RunwayAPIError as e:
        jobs.mark_error(job_id, f"Runway API error: {e.message}")
    except RuntimeError as e:
        jobs.mark_error(job_id, str(e))
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def _run_cut_visualizer_job(job_id: str, job_dir: Path, work_dir: Path, music_path: Path, num_styles: int) -> None:
    on_progress = lambda stage, current, total: jobs.update_progress(job_id, stage, current, total)
    try:
        jobs.update_progress(job_id, "detecting_beats")
        tempo, beat_times = detect_beats(str(music_path))
        if len(beat_times) < 2:
            jobs.mark_error(job_id, "Could not detect enough beats in the music track")
            return

        segment_paths = cut_visualizer_to_beats(
            str(music_path), beat_times, num_styles, str(work_dir), on_progress=on_progress
        )

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / f"{job_id}.mp4"
        concat_and_mux(
            segment_paths, beat_times, str(music_path), str(output_path), str(work_dir), on_progress=on_progress
        )
        jobs.mark_done(job_id, tempo, len(beat_times), f"/api/output/{job_id}.mp4")
    except RuntimeError as e:
        jobs.mark_error(job_id, str(e))
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


@app.post("/api/cut")
async def cut(background_tasks: BackgroundTasks, music: UploadFile = File(...), clips: List[UploadFile] = File(...)):
    if not clips:
        raise HTTPException(status_code=400, detail="At least one video clip is required")

    job_id = uuid.uuid4().hex
    job_dir = UPLOADS_DIR / job_id

    music_path = _save_upload(music, job_dir)
    clip_paths = [str(_save_upload(clip, job_dir)) for clip in clips]

    jobs.create_job(job_id)
    background_tasks.add_task(_run_cut_job, job_id, job_dir, job_dir / "work", music_path, clip_paths)

    return {"job_id": job_id}


@app.post("/api/cut-ai")
async def cut_ai(
    background_tasks: BackgroundTasks,
    music: UploadFile = File(...),
    prompt: str = Form(...),
    num_scenes: int = Form(4),
):
    prompts = [line.strip() for line in prompt.splitlines() if line.strip()]
    if not prompts:
        raise HTTPException(status_code=400, detail="At least one scene prompt is required")
    if not (1 <= num_scenes <= 8):
        raise HTTPException(status_code=400, detail="num_scenes must be between 1 and 8")

    job_id = uuid.uuid4().hex
    job_dir = UPLOADS_DIR / job_id
    work_dir = job_dir / "work"

    music_path = _save_upload(music, job_dir)

    jobs.create_job(job_id)
    background_tasks.add_task(_run_cut_ai_job, job_id, job_dir, work_dir, music_path, prompts, num_scenes)

    return {"job_id": job_id}


@app.post("/api/cut-visualizer")
async def cut_visualizer(background_tasks: BackgroundTasks, music: UploadFile = File(...), num_styles: int = Form(3)):
    if not (1 <= num_styles <= 4):
        raise HTTPException(status_code=400, detail="num_styles must be between 1 and 4")

    job_id = uuid.uuid4().hex
    job_dir = UPLOADS_DIR / job_id
    work_dir = job_dir / "work"

    music_path = _save_upload(music, job_dir)

    jobs.create_job(job_id)
    background_tasks.add_task(_run_cut_visualizer_job, job_id, job_dir, work_dir, music_path, num_styles)

    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/output/{filename}")
async def get_output(filename: str):
    path = OUTPUT_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Output not found")
    return FileResponse(path, media_type="video/mp4", filename=filename)


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
