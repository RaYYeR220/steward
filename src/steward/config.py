"""Runtime settings for the Qwen Cloud LLM client."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "qwen3.7-max"
DEFAULT_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"


@dataclass(frozen=True)
class QwenSettings:
    api_key: str | None
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL


def _read_env_file(env_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, _, val = line.partition("=")
                values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def load_qwen_settings(env_file: Path | None = None) -> QwenSettings:
    """Load settings from process env first, then the .env file, then defaults."""
    if env_file is None:
        # cwd-relative: correct when the CLI runs from the repo root (the
        # documented usage); callers can pass an explicit path otherwise.
        env_file = Path.cwd() / ".env"
    file_values = _read_env_file(env_file)

    _MISSING = object()

    def get(name: str) -> str | None:
        env_val = os.environ.get(name, _MISSING)
        if env_val is not _MISSING:
            # A set-but-empty variable deliberately overrides the file
            # (e.g. QWEN_API_KEY="" forces degraded mode).
            return env_val or None
        return file_values.get(name) or None

    return QwenSettings(
        api_key=get("QWEN_API_KEY"),
        model=get("QWEN_MODEL") or DEFAULT_MODEL,
        base_url=get("QWEN_BASE_URL") or DEFAULT_BASE_URL,
    )
