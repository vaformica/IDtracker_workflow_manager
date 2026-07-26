"""Tkinter video-intake GUI for Stage 2."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Callable

from .registry import (
    export_videos_csv,
    initialize_database,
    record_still_failure,
    record_still_success,
    upsert_video,
)
from .stills import StillGenerationError, StillResult, generate_still_png


VIDEO_FILE_TYPES = [
    ("Video files", "*.mp4 *.avi *.mov *.mkv *.mpg *.mpeg"),
    ("All files", "*"),
]


@dataclass(frozen=True)
class IntakeResult:
    """Registry and artifact result for a processed video."""

    video_id: str
    video_path: Path
    video_type: str
    still: StillResult


def register_video_and_generate_still(
    database_path: str | Path,
    video_path: str | Path,
    *,
    video_type: str,
    created_by: str,
    still_output_directory: str | Path,
    ffmpeg_executable: str = "ffmpeg",
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> IntakeResult:
    """Register one video, generate its still, and record the outcome."""

    initialize_database(database_path)
    video = upsert_video(
        database_path,
        video_path,
        video_type=video_type,
        video_type_source="manual",
        created_by=created_by,
    )

    try:
        still = generate_still_png(
            video["video_path"],
            still_output_directory,
            video["video_id"],
            ffmpeg_executable=ffmpeg_executable,
            runner=runner,
        )
    except (StillGenerationError, OSError) as error:
        record_still_failure(
            database_path,
            video["video_id"],
            error_message=str(error) or type(error).__name__,
        )
        raise

    record_still_success(
        database_path,
        video["video_id"],
        frame_number=still.frame_number,
        still_png_path=still.png_path,
    )
    return IntakeResult(
        video_id=video["video_id"],
        video_path=Path(video["video_path"]),
        video_type=video["video_type"],
        still=still,
    )


class VideoIntakeApplication:
    """Small Stage 2 GUI for registering videos and creating stills."""

    def __init__(
        self,
        root: object,
        *,
        database_path: str | Path,
        still_output_directory: str | Path,
        video_export_path: str | Path,
        ffmpeg_executable: str = "ffmpeg",
    ) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.root = root
        self.database_path = Path(database_path)
        self.still_output_directory = Path(still_output_directory)
        self.video_export_path = Path(video_export_path)
        self.ffmpeg_executable = ffmpeg_executable
        self._row_counter = 0

        root.title("IDtracker Workflow Manager — Video Intake")
        root.geometry("1100x560")

        controls = ttk.Frame(root, padding=10)
        controls.pack(fill=tk.X)

        ttk.Label(controls, text="Created by:").grid(row=0, column=0, sticky=tk.W)
        self.created_by = tk.StringVar()
        ttk.Entry(controls, textvariable=self.created_by, width=24).grid(
            row=0, column=1, padx=(4, 14)
        )

        ttk.Label(controls, text="Video type:").grid(row=0, column=2, sticky=tk.W)
        self.video_type = tk.StringVar(value="unknown")
        ttk.Combobox(
            controls,
            textvariable=self.video_type,
            values=("ba", "fight", "other", "unknown"),
            state="readonly",
            width=10,
        ).grid(row=0, column=3, padx=(4, 14))

        ttk.Button(controls, text="Add videos…", command=self._add_videos).grid(
            row=0, column=4, padx=4
        )
        ttk.Button(
            controls,
            text="Set type on selected",
            command=self._set_selected_type,
        ).grid(row=0, column=5, padx=4)
        ttk.Button(
            controls,
            text="Register and generate stills",
            command=self._process_videos,
        ).grid(row=0, column=6, padx=4)

        columns = ("video_path", "video_type", "status", "still_path")
        self.table = ttk.Treeview(root, columns=columns, show="headings")
        self.table.heading("video_path", text="Video")
        self.table.heading("video_type", text="Type")
        self.table.heading("status", text="Status")
        self.table.heading("still_path", text="Still PNG")
        self.table.column("video_path", width=430)
        self.table.column("video_type", width=80, anchor=tk.CENTER)
        self.table.column("status", width=160)
        self.table.column("still_path", width=380)
        self.table.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.status_text = tk.StringVar(
            value=f"Registry: {self.database_path}"
        )
        ttk.Label(root, textvariable=self.status_text, padding=(10, 0, 10, 10)).pack(
            fill=tk.X
        )

    def _add_videos(self) -> None:
        from tkinter import filedialog

        selected_paths = filedialog.askopenfilenames(filetypes=VIDEO_FILE_TYPES)
        existing = {
            self.table.set(item, "video_path") for item in self.table.get_children()
        }
        for selected_path in selected_paths:
            normalized_path = str(Path(selected_path).resolve(strict=False))
            if normalized_path in existing:
                continue
            self._row_counter += 1
            self.table.insert(
                "",
                "end",
                iid=f"video-{self._row_counter}",
                values=(
                    normalized_path,
                    self.video_type.get(),
                    "Ready",
                    "",
                ),
            )
            existing.add(normalized_path)

    def _set_selected_type(self) -> None:
        for item in self.table.selection():
            self.table.set(item, "video_type", self.video_type.get())

    def _process_videos(self) -> None:
        from tkinter import messagebox

        creator = self.created_by.get().strip()
        if not creator:
            messagebox.showerror("Created by required", "Enter the operator name.")
            return
        items = self.table.get_children()
        if not items:
            messagebox.showinfo("No videos", "Add at least one video first.")
            return

        successes = 0
        failures: list[str] = []
        for item in items:
            video_path = self.table.set(item, "video_path")
            video_type = self.table.set(item, "video_type")
            self.table.set(item, "status", "Processing…")
            self.root.update_idletasks()
            try:
                result = register_video_and_generate_still(
                    self.database_path,
                    video_path,
                    video_type=video_type,
                    created_by=creator,
                    still_output_directory=self.still_output_directory,
                    ffmpeg_executable=self.ffmpeg_executable,
                )
            except (StillGenerationError, OSError, ValueError) as error:
                self.table.set(item, "status", "FAILED")
                failures.append(f"{Path(video_path).name}: {error}")
            else:
                self.table.set(
                    item, "status", f"Frame {result.still.frame_number}"
                )
                self.table.set(item, "still_path", str(result.still.png_path))
                successes += 1

        export_videos_csv(self.database_path, self.video_export_path)
        self.status_text.set(
            f"Finished: {successes} succeeded, {len(failures)} failed. "
            f"Export: {self.video_export_path}"
        )
        if failures:
            messagebox.showwarning(
                "Still generation failures",
                "The failed videos remain registered and are marked FAILED:\n\n"
                + "\n".join(failures),
            )
        else:
            messagebox.showinfo(
                "Video intake complete",
                f"Processed {successes} video(s).\n\n"
                f"Video export: {self.video_export_path}",
            )


def main(argv: list[str] | None = None) -> int:
    """Launch the Stage 2 video-intake GUI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        default="idtracker_workflow.sqlite",
        help="SQLite registry path",
    )
    parser.add_argument(
        "--stills",
        default="stills/frame_2000",
        help="output directory for generated PNG stills",
    )
    parser.add_argument(
        "--video-export",
        default="exports/videos.csv",
        help="CSV export path updated after processing",
    )
    parser.add_argument(
        "--ffmpeg",
        default="ffmpeg",
        help="ffmpeg executable name or path",
    )
    args = parser.parse_args(argv)

    import tkinter as tk

    root = tk.Tk()
    initialize_database(args.database)
    VideoIntakeApplication(
        root,
        database_path=args.database,
        still_output_directory=args.stills,
        video_export_path=args.video_export,
        ffmpeg_executable=args.ffmpeg,
    )
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
