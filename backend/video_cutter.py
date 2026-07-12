import os
import subprocess
from typing import Callable, List, Optional

WIDTH, HEIGHT, FPS = 1280, 720, 30
SCALE_FILTER = (
    f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
    f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,fps={FPS}"
)

ProgressFn = Callable[[str, int, int], None]


def noop_progress(stage: str, current: int, total: int) -> None:
    pass


def run_ffmpeg(cmd: List[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg command failed: {' '.join(cmd)}\n{result.stderr}")


def get_duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}\n{result.stderr}")
    return float(result.stdout.strip())


def concat_and_mux(
    segment_paths: List[str],
    beat_times: List[float],
    music_path: str,
    output_path: str,
    work_dir: str,
    on_progress: Optional[ProgressFn] = None,
) -> str:
    """Concatenate already-cut `segment_paths` (silent video) and mux in
    `music_path`, trimmed to the [beat_times[0], beat_times[-1]] window, as
    the audio track. Returns `output_path`."""
    on_progress = on_progress or noop_progress
    os.makedirs(work_dir, exist_ok=True)

    on_progress("concatenating", 0, 1)
    concat_list_path = os.path.join(work_dir, "concat_list.txt")
    with open(concat_list_path, "w") as f:
        for seg_path in segment_paths:
            f.write(f"file '{os.path.abspath(seg_path)}'\n")

    silent_video_path = os.path.join(work_dir, "silent_concat.mp4")
    run_ffmpeg([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_list_path,
        "-c", "copy",
        silent_video_path,
    ])

    on_progress("muxing_audio", 0, 1)
    total_duration = beat_times[-1] - beat_times[0]
    run_ffmpeg([
        "ffmpeg", "-y",
        "-i", silent_video_path,
        "-ss", str(beat_times[0]), "-t", str(total_duration),
        "-i", music_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac",
        "-shortest",
        output_path,
    ])

    return output_path


def cut_to_beats(
    clips: List[str],
    beat_times: List[float],
    music_path: str,
    output_path: str,
    work_dir: str,
    on_progress: Optional[ProgressFn] = None,
) -> str:
    """Cut `clips` (cycled round-robin) into segments matching the intervals
    between consecutive `beat_times`, concatenate them, and mux in `music_path`
    (trimmed to the same window) as the audio track. Returns `output_path`."""
    if len(beat_times) < 2:
        raise ValueError("Need at least 2 beat timestamps to cut between")
    if not clips:
        raise ValueError("Need at least 1 video clip")

    on_progress = on_progress or noop_progress
    os.makedirs(work_dir, exist_ok=True)
    clip_durations = [get_duration(c) for c in clips]

    segment_paths = []
    clip_idx = 0
    cursor = 0.0

    beat_pairs = list(zip(beat_times, beat_times[1:]))
    for i, (start_t, end_t) in enumerate(beat_pairs):
        duration = end_t - start_t
        if duration <= 0:
            continue

        on_progress("cutting_segments", i + 1, len(beat_pairs))

        if cursor + duration > clip_durations[clip_idx]:
            clip_idx = (clip_idx + 1) % len(clips)
            cursor = 0.0

        remaining = clip_durations[clip_idx] - cursor
        seg_duration = min(duration, remaining) if remaining > 0 else duration

        seg_path = os.path.join(work_dir, f"segment_{i:04d}.mp4")
        run_ffmpeg([
            "ffmpeg", "-y",
            "-ss", str(cursor),
            "-i", clips[clip_idx],
            "-t", str(seg_duration),
            "-vf", SCALE_FILTER,
            "-an",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            seg_path,
        ])
        segment_paths.append(seg_path)
        cursor += seg_duration

    return concat_and_mux(segment_paths, beat_times, music_path, output_path, work_dir, on_progress)
