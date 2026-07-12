import hashlib
import os
import time
from pathlib import Path
from typing import List, Optional

import requests
from runwayml import RunwayML

from video_cutter import ProgressFn, noop_progress

MODEL = "gen4.5"
RATIO = "1280:720"
DURATION_SECONDS = 4
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 600

# Persistent cache of generated clips, keyed by exact prompt text (+ model
# settings). Not cleaned up between jobs like the per-job work_dir, so an
# identical prompt reused across projects is free instead of a fresh charge.
CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "ai_clips"


def _cache_key(prompt: str) -> str:
    raw = f"{prompt}|{MODEL}|{RATIO}|{DURATION_SECONDS}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _cached_clip_path(prompt: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{_cache_key(prompt)}.mp4"


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


def generate_scene_clips(
    prompts: List[str],
    num_scenes: int,
    work_dir: str,
    on_progress: Optional[ProgressFn] = None,
) -> List[str]:
    """Generate `num_scenes` short AI video clips via Runway's text_to_video
    API, cycling through `prompts` (one or more distinct scene descriptions)
    to assign each scene's prompt. Returns local file paths, in scene order.

    Clips are cached on disk keyed by exact prompt text: a prompt already
    generated (in this job or a prior one) is reused for free instead of
    triggering a new paid generation. Only cache misses are submitted to
    Runway, and those are submitted up front so Runway can process them
    concurrently, then each is polled to completion."""
    on_progress = on_progress or noop_progress
    os.makedirs(work_dir, exist_ok=True)

    scene_prompts = [prompts[i % len(prompts)] for i in range(num_scenes)]

    clip_paths: List[Optional[str]] = [None] * num_scenes
    to_generate = []  # (scene_index, prompt) for cache misses, deduped by prompt
    seen_prompts = set()
    for i, prompt in enumerate(scene_prompts):
        cache_path = _cached_clip_path(prompt)
        if cache_path.is_file():
            clip_paths[i] = str(cache_path)
        elif prompt not in seen_prompts:
            seen_prompts.add(prompt)
            to_generate.append((i, prompt))

    if to_generate:
        client = _client()
        on_progress("submitting_scenes", 0, len(to_generate))
        tasks = [
            (i, prompt, client.text_to_video.create(
                model=MODEL,
                prompt_text=prompt,
                ratio=RATIO,
                duration=DURATION_SECONDS,
            ).id)
            for i, prompt in to_generate
        ]

        for j, (i, prompt, task_id) in enumerate(tasks):
            on_progress("generating_scenes", j, len(tasks))
            output_urls = _wait_for_task(client, task_id)
            if not output_urls:
                raise RuntimeError(f"Runway task {task_id} succeeded but returned no output")
            cache_path = _cached_clip_path(prompt)
            tmp_path = f"{cache_path}.tmp"
            _download(output_urls[0], tmp_path)
            os.replace(tmp_path, cache_path)
            clip_paths[i] = str(cache_path)
            on_progress("generating_scenes", j + 1, len(tasks))

    # Any remaining None slots share a prompt with an index generated above
    # (duplicate prompt within this same request); fill them in now.
    prompt_to_path = {scene_prompts[i]: p for i, p in enumerate(clip_paths) if p is not None}
    for i, prompt in enumerate(scene_prompts):
        if clip_paths[i] is None:
            clip_paths[i] = prompt_to_path[prompt]

    return clip_paths
