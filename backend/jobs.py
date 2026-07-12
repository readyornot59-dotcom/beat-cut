import threading
import time
from typing import Optional

_lock = threading.Lock()
_jobs: dict = {}


def create_job(job_id: str) -> None:
    with _lock:
        _jobs[job_id] = {
            "status": "running",
            "stage": "starting",
            "current": 0,
            "total": 0,
            "started_at": time.time(),
            "tempo": None,
            "num_beats": None,
            "download_url": None,
            "detail": None,
        }


def update_progress(job_id: str, stage: str, current: int = 0, total: int = 0) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(stage=stage, current=current, total=total)


def mark_done(job_id: str, tempo: float, num_beats: int, download_url: str) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(
                status="done",
                stage="done",
                tempo=tempo,
                num_beats=num_beats,
                download_url=download_url,
            )


def mark_error(job_id: str, detail: str) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(status="error", detail=detail)


def get_job(job_id: str) -> Optional[dict]:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None
