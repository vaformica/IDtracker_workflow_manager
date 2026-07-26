"""Mac-side SSH requests and verified artifact downloads."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from typing import Any, Callable
import uuid

from .remote_backend import PROTOCOL_VERSION


_SSH_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class SSHTransportError(RuntimeError):
    """Raised when SSH, the backend protocol, or artifact verification fails."""


@dataclass(frozen=True)
class SSHClientConfig:
    """Connection details for a Firebird backend command."""

    host: str
    remote_command: str
    remote_config_path: str
    user: str | None = None
    connect_timeout_seconds: int = 15
    request_timeout_seconds: int = 120

    def __post_init__(self) -> None:
        if not _SSH_NAME_PATTERN.fullmatch(self.host):
            raise ValueError("host must be an SSH hostname or config alias")
        if self.user is not None and not _SSH_NAME_PATTERN.fullmatch(self.user):
            raise ValueError("user contains unsupported characters")
        if not self.remote_command.strip():
            raise ValueError("remote_command must not be empty")
        if "\n" in self.remote_command or "\r" in self.remote_command:
            raise ValueError("remote_command must not contain newlines")
        if not self.remote_config_path.startswith("/"):
            raise ValueError("remote_config_path must be absolute")
        if "\n" in self.remote_config_path or "\r" in self.remote_config_path:
            raise ValueError("remote_config_path must not contain newlines")
        if self.connect_timeout_seconds <= 0:
            raise ValueError("connect_timeout_seconds must be positive")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")

    @property
    def destination(self) -> str:
        if self.user is None:
            return self.host
        return f"{self.user}@{self.host}"


def build_ssh_request_command(config: SSHClientConfig) -> list[str]:
    """Build the system SSH command for one backend request."""

    remote_invocation = " ".join(
        (
            shlex.quote(config.remote_command),
            "--config",
            shlex.quote(config.remote_config_path),
            "--request",
        )
    )
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={config.connect_timeout_seconds}",
        config.destination,
        remote_invocation,
    ]


class SSHTransport:
    """Versioned JSON request transport over the system SSH client."""

    def __init__(
        self,
        config: SSHClientConfig,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.config = config
        self.runner = runner

    def request(
        self,
        action: str,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request_id = uuid.uuid4().hex
        request = {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "action": action,
            "parameters": parameters or {},
        }
        try:
            completed = self.runner(
                build_ssh_request_command(self.config),
                input=json.dumps(request),
                capture_output=True,
                text=True,
                check=False,
                timeout=self.config.request_timeout_seconds,
            )
        except FileNotFoundError as error:
            raise SSHTransportError("system ssh executable was not found") from error
        except subprocess.TimeoutExpired as error:
            raise SSHTransportError(
                f"Firebird request timed out: {action}"
            ) from error

        if not completed.stdout.strip():
            detail = completed.stderr.strip() or "no response"
            raise SSHTransportError(
                f"Firebird returned no JSON response: {detail}"
            )
        try:
            response = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise SSHTransportError(
                "Firebird response was not valid JSON"
            ) from error
        if not isinstance(response, dict):
            raise SSHTransportError("Firebird response was not a JSON object")
        if response.get("protocol_version") != PROTOCOL_VERSION:
            raise SSHTransportError("Firebird protocol version mismatch")
        if response.get("request_id") != request_id:
            raise SSHTransportError("Firebird response request_id mismatch")
        if not response.get("ok"):
            error_details = response.get("error")
            if isinstance(error_details, dict):
                code = error_details.get("code", "REMOTE_ERROR")
                message = error_details.get("message", "unknown remote error")
            else:
                code = "REMOTE_ERROR"
                message = "unknown remote error"
            raise SSHTransportError(f"{code}: {message}")
        if completed.returncode != 0:
            raise SSHTransportError(
                f"ssh exited with status {completed.returncode}"
            )
        data = response.get("data")
        if not isinstance(data, dict):
            raise SSHTransportError("Firebird response data was not an object")
        return data


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_verified_artifact(
    config: SSHClientConfig,
    *,
    remote_path: str,
    expected_sha256: str,
    cache_directory: str | Path,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> Path:
    """Download one server-approved artifact and verify its SHA-256 digest."""

    normalized_hash = expected_sha256.strip().lower()
    if not _SHA256_PATTERN.fullmatch(normalized_hash):
        raise ValueError("expected_sha256 must be a SHA-256 hex digest")
    if not remote_path.startswith("/") or "\n" in remote_path or "\r" in remote_path:
        raise ValueError("remote_path must be an absolute path without newlines")

    cache = Path(cache_directory).expanduser()
    cache.mkdir(parents=True, exist_ok=True)
    basename = Path(remote_path).name
    if not basename:
        raise ValueError("remote_path must identify a file")
    destination = cache / f"{normalized_hash}__{basename}"
    if destination.is_file() and _sha256_file(destination) == normalized_hash:
        return destination

    temporary_file = tempfile.NamedTemporaryFile(
        prefix=".download-",
        suffix=".part",
        dir=cache,
        delete=False,
    )
    temporary_path = Path(temporary_file.name)
    temporary_file.close()
    source = f"{config.destination}:{shlex.quote(remote_path)}"
    command = [
        "scp",
        "-q",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={config.connect_timeout_seconds}",
        source,
        str(temporary_path),
    ]
    try:
        try:
            completed = runner(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=config.request_timeout_seconds,
            )
        except FileNotFoundError as error:
            raise SSHTransportError(
                "system scp executable was not found"
            ) from error
        except subprocess.TimeoutExpired as error:
            raise SSHTransportError("artifact download timed out") from error
        if completed.returncode != 0:
            detail = completed.stderr.strip() or "unknown scp error"
            raise SSHTransportError(f"artifact download failed: {detail}")
        actual_hash = _sha256_file(temporary_path)
        if actual_hash != normalized_hash:
            raise SSHTransportError(
                "downloaded artifact hash mismatch: "
                f"expected {normalized_hash}, got {actual_hash}"
            )
        temporary_path.replace(destination)
        return destination
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
