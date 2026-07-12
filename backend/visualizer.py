import os
from typing import Dict, List, Optional

from video_cutter import WIDTH, HEIGHT, FPS, ProgressFn, noop_progress, run_ffmpeg

STYLES = ["showcqt", "showspectrum", "showwaves", "avectorscope"]

# Each filter's own native rate parameter is used instead of chaining a
# separate `fps` filter afterward: chaining `fps` after these audio-driven
# filters deadlocks ffmpeg's muxing queue near end-of-stream (frames render
# almost instantly, `fps` buffers them for rate conversion, and it hangs
# waiting for more input that never comes).
STYLE_FILTERS = {
    "showcqt": f"showcqt=s={WIDTH}x{HEIGHT}:r={FPS}",
    "showspectrum": f"showspectrum=s={WIDTH}x{HEIGHT}:mode=combined:color=rainbow:scale=cbrt:fps={FPS}",
    "showwaves": f"showwaves=s={WIDTH}x{HEIGHT}:mode=cline:colors=white|cyan|magenta:r={FPS}",
    "avectorscope": f"avectorscope=s={WIDTH}x{HEIGHT}:zoom=1.5:r={FPS}",
}


def _render_style_track(music_path: str, style: str, work_dir: str) -> str:
    """Render a full-length audio-reactive visualization of `music_path`
    using the given lavfi `style`, spanning the whole track duration."""
    os.makedirs(work_dir, exist_ok=True)
    out_path = os.path.join(work_dir, f"style_{style}.mp4")
    run_ffmpeg([
        "ffmpeg", "-y",
        "-i", music_path,
        "-filter_complex", f"[0:a]{STYLE_FILTERS[style]}[v]",
        "-map", "[v]",
        "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        out_path,
    ])
    return out_path


def cut_visualizer_to_beats(
    music_path: str,
    beat_times: List[float],
    num_styles: int,
    work_dir: str,
    on_progress: Optional[ProgressFn] = None,
) -> List[str]:
    """Render `num_styles` full-track audio-reactive visualizations and cut
    segments directly from the matching timestamp in each, alternating
    styles at every beat so the switch lands exactly on the cut. Returns
    segment file paths in order, ready for video_cutter.concat_and_mux."""
    on_progress = on_progress or noop_progress
    styles = STYLES[: max(1, min(num_styles, len(STYLES)))]

    styles_dir = os.path.join(work_dir, "styles")
    style_tracks: Dict[str, str] = {}
    for i, style in enumerate(styles):
        on_progress("rendering_styles", i + 1, len(styles))
        style_tracks[style] = _render_style_track(music_path, style, styles_dir)

    segment_dir = os.path.join(work_dir, "visualizer_segments")
    os.makedirs(segment_dir, exist_ok=True)

    segment_paths = []
    beat_pairs = list(zip(beat_times, beat_times[1:]))
    for i, (start_t, end_t) in enumerate(beat_pairs):
        duration = end_t - start_t
        if duration <= 0:
            continue

        on_progress("cutting_segments", i + 1, len(beat_pairs))
        style = styles[i % len(styles)]
        seg_path = os.path.join(segment_dir, f"vseg_{i:04d}.mp4")
        run_ffmpeg([
            "ffmpeg", "-y",
            "-ss", str(start_t),
            "-i", style_tracks[style],
            "-t", str(duration),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            seg_path,
        ])
        segment_paths.append(seg_path)

    return segment_paths
