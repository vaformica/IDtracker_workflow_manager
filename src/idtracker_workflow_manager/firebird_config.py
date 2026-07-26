"""Configuration and path safeguards for the Firebird backend."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


DEFAULT_VIDEO_EXTENSIONS = (
    ".avi",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
)


class ConfigurationError(ValueError):
    """Raised when backend configuration is missing or unsafe."""


def canonical_absolute_path(path: str | Path) -> Path:
    """Return one resolved absolute path without accepting relative identity."""

    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise ConfigurationError(f"path must be absolute: {path}")
    return candidate.resolve(strict=False)


@dataclass(frozen=True)
class FirebirdBackendConfig:
    """Server-owned paths and executable settings."""

    registry_root: Path
    video_roots: tuple[Path, ...]
    toml_roots: tuple[Path, ...] = ()
    ffmpeg_executable: str = "ffmpeg"
    video_extensions: tuple[str, ...] = DEFAULT_VIDEO_EXTENSIONS
    minimum_file_age_seconds: int = 300

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "FirebirdBackendConfig":
        try:
            registry_root = canonical_absolute_path(raw["registry_root"])
            raw_video_roots = raw["video_roots"]
        except KeyError as error:
            raise ConfigurationError(
                f"missing required configuration field: {error.args[0]}"
            ) from error
        if not isinstance(raw_video_roots, list) or not raw_video_roots:
            raise ConfigurationError("video_roots must be a non-empty list")

        video_roots = tuple(
            canonical_absolute_path(path) for path in raw_video_roots
        )
        if len(set(video_roots)) != len(video_roots):
            raise ConfigurationError("video_roots must not contain duplicates")
        raw_toml_roots = raw.get("toml_roots", [])
        if not isinstance(raw_toml_roots, list):
            raise ConfigurationError("toml_roots must be a list")
        toml_roots = tuple(
            canonical_absolute_path(path) for path in raw_toml_roots
        )
        if len(set(toml_roots)) != len(toml_roots):
            raise ConfigurationError("toml_roots must not contain duplicates")

        ffmpeg = str(raw.get("ffmpeg_executable", "ffmpeg")).strip()
        if not ffmpeg:
            raise ConfigurationError("ffmpeg_executable must not be empty")

        raw_extensions = raw.get(
            "video_extensions", list(DEFAULT_VIDEO_EXTENSIONS)
        )
        if not isinstance(raw_extensions, list) or not raw_extensions:
            raise ConfigurationError("video_extensions must be a non-empty list")
        extensions = tuple(
            extension.strip().lower()
            if extension.strip().startswith(".")
            else f".{extension.strip().lower()}"
            for extension in map(str, raw_extensions)
        )
        if any(extension == "." for extension in extensions):
            raise ConfigurationError("video extensions must not be empty")
        minimum_age = raw.get("minimum_file_age_seconds", 300)
        if not isinstance(minimum_age, int) or minimum_age < 0:
            raise ConfigurationError(
                "minimum_file_age_seconds must be a non-negative integer"
            )

        return cls(
            registry_root=registry_root,
            video_roots=video_roots,
            toml_roots=toml_roots,
            ffmpeg_executable=ffmpeg,
            video_extensions=extensions,
            minimum_file_age_seconds=minimum_age,
        )

    @classmethod
    def from_json_file(cls, path: str | Path) -> "FirebirdBackendConfig":
        config_path = Path(path)
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise ConfigurationError(
                f"configuration file does not exist: {config_path}"
            ) from error
        except json.JSONDecodeError as error:
            raise ConfigurationError(
                f"configuration is not valid JSON: {error}"
            ) from error
        if not isinstance(raw, dict):
            raise ConfigurationError("configuration root must be a JSON object")
        return cls.from_mapping(raw)

    @property
    def database_path(self) -> Path:
        return self.registry_root / "database" / "idtracker_workflow.sqlite"

    @property
    def stills_directory(self) -> Path:
        return self.registry_root / "stills" / "frame_2000"

    @property
    def exports_directory(self) -> Path:
        return self.registry_root / "exports"

    @property
    def lock_path(self) -> Path:
        return self.registry_root / "locks" / "registry.lock"

    def canonical_video_path(
        self,
        path: str | Path,
        *,
        must_exist: bool = True,
        require_file: bool = True,
    ) -> Path:
        """Validate a canonical path inside one configured video root."""

        candidate = canonical_absolute_path(path)
        if not any(candidate.is_relative_to(root) for root in self.video_roots):
            raise ConfigurationError(
                f"path is outside configured video roots: {candidate}"
            )
        if must_exist and not candidate.exists():
            raise ConfigurationError(f"path does not exist: {candidate}")
        if require_file and candidate.exists() and not candidate.is_file():
            raise ConfigurationError(f"path is not a file: {candidate}")
        if require_file and candidate.suffix.lower() not in self.video_extensions:
            raise ConfigurationError(
                f"unsupported video extension: {candidate.suffix or '(none)'}"
            )
        return candidate

    @property
    def discovery_roots(self) -> tuple[Path, ...]:
        """Return unique approved video/TOML roots in configured order."""

        return tuple(dict.fromkeys((*self.video_roots, *self.toml_roots)))
