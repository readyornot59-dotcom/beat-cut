import os
import time
from typing import List

import requests
from runwayml import RunwayML

MODEL = "gen4.5"
RATIO = "1280:720"
DURATION_SECONDS = 4
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 600


def _client() -> RunwayML:
    api_key = os.environ.get("RUNWAYML_API_SECRET")
    if not api_key:
        raise RuntimeError(
            "RUNWAYML_API_SECRET is not set. Add it to your environment or .env file "
            "to use AI video generation."
        )
    return RunwayML(api_key=api_key)


def _wait_for_task(client: RunwayML, task_id: str) -> List[str]:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        task = client.tasks.retrieve(task_id)
        if task.status == "SUCCEEDED":
            return task.output
        if task.status == "FAILED":
            raise RuntimeError(f"Runway task {task_id} failed: {task.failure}")
        if task.status == "CANCELLED":
            raise RuntimeError(f"Runway task {task_id} was cancelled")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise RuntimeError(f"Runway task {task_id} timed out after {POLL_TIMEOUT_SECONDS}s")


def _download(url: str, dest_path: str) -> str:
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return dest_path


def generate_scene_clips(prompt: str, num_scenes: int, work_dir: str) -> List[str]:
    """Generate `num_scenes` short AI video clips from `prompt` via Runway's
    text_to_video API and download them into `work_dir`. Returns local file paths.

    All generation tasks are submitted up front so Runway can process them
    concurrently, then each is polled to completion."""
    os.makedirs(work_dir, exist_ok=True)
    client = _client()

    task_ids = [
        client.text_to_video.create(
            model=MODEL,
            prompt_text=prompt,
            ratio=RATIO,
            duration=DURATION_SECONDS,
        ).id
        for _ in range(num_scenes)
    ]

    clip_paths = []
    for i, task_id in enumerate(task_ids):
        output_urls = _wait_for_task(client, task_id)
        if not output_urls:
            raise RuntimeError(f"Runway task {task_id} succeeded but returned no output")
        dest_path = os.path.join(work_dir, f"ai_scene_{i:02d}.mp4")
        clip_paths.append(_download(output_urls[0], dest_path))

    return clip_paths
