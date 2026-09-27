"""Shared config loader. Paths in settings.yaml are resolved from the repo root."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_FILE = ROOT / "config" / "settings.yaml"


def load_settings() -> dict:
    with open(SETTINGS_FILE) as f:
        return yaml.safe_load(f)


def path(key: str) -> Path:
    """Return an absolute path for a key under `paths:` and make sure its parent exists.

    Any path can be overridden with an env var, e.g. GTM_WAREHOUSE=/tmp/gtm.duckdb.
    """
    override = os.environ.get(f"GTM_{key.upper()}")
    p = Path(override) if override else ROOT / load_settings()["paths"][key]
    target_dir = p.parent if p.suffix else p
    target_dir.mkdir(parents=True, exist_ok=True)
    return p
