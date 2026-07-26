"""Full-resolution still generation with explicit frame fallbacks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Callable, Sequence


DEFAULT_FRAME_CANDIDATES = (2000, 1000, 0)


class StillGenerationError(RuntimeError):
    """Raised after all configured frame candidates fail."""


@dataclass(frozen=True)
class StillResult:
    """Metadata for one generated still PNG."""

    frame_number: int
    png_path: Path


def still_output_path(
    output_directory: str | Path,
    video_id: str,
    frame_number: int,
) -> Path:
    """Return the registry still path for a video and actual frame number."""

    if not video_id.strip():
        raise ValueError("video_id must not be empty")
    if frame_number < 0:
        raise ValueError("frame_number must be zero or greater")
    return (
        Path(output_directory)
        / f"{video_id.strip()}__frame_{frame_number:06d}.png"
    )


def build_ffmpeg_still_command(
    video_path: str | Path,
    output_path: str | Path,
    frame_number: int,
    *,
    ffmpeg_executable: str = "ffmpeg",
) -> list[str]:
    """Build an ffmpeg command that preserves the video's source resolution."""

    if frame_number < 0:
        raise ValueError("frame_number must be zero or greater")
    return [
        ffmpeg_executable,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"select=eq(n\\,{frame_number})",
        "-frames:v",
        "1",
        str(output_path),
    ]


def generate_still_png(
    video_path: str | Path,
    output_directory: str | Path,
    video_id: str,
    *,
    frame_candidates: Sequence[int] = DEFAULT_FRAME_CANDIDATES,
    ffmpeg_executable: str = "ffmpeg",
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> StillResult:
    """Generate a PNG from the first available candidate frame.

    The default sequence is frame 2000, frame 1000, then frame 0 (the first
    valid frame). No scaling filter is applied, so ffmpeg retains the original
    video resolution.
    """

    source = Path(video_path)
    if not source.is_file():
        raise StillGenerationError(f"video file does not exist: {source}")
    if not frame_candidates:
        raise ValueError("frame_candidates must contain at least one frame")
    if any(frame < 0 for frame in frame_candidates):
        raise ValueError("frame candidates must be zero or greater")

    destination_directory = Path(output_directory).expanduser().resolve(
        strict=False
    )
    destination_directory.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    for frame_number in frame_candidates:
        destination = still_output_path(
            destination_directory, video_id, frame_number
        )
        command = build_ffmpeg_still_command(
            source,
            destination,
            frame_number,
            ffmpeg_executable=ffmpeg_executable,
        )
        try:
            completed = runner(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as error:
            raise StillGenerationError(
                f"ffmpeg executable not found: {ffmpeg_executable}"
            ) from error

        if (
            completed.returncode == 0
            and destination.is_file()
            and destination.stat().st_size > 0
        ):
            return StillResult(frame_number=frame_number, png_path=destination)

        if destination.exists():
            destination.unlink()
        detail = (completed.stderr or "").strip() or "no PNG was created"
        errors.append(f"frame {frame_number}: {detail}")

    raise StillGenerationError(
        "still generation failed for all frame candidates; " + "; ".join(errors)
    )
