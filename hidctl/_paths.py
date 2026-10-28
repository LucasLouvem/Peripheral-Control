"""Diretórios de estado do usuário (backups, trava de acesso). Respeita ``XDG_STATE_HOME``."""

import os
from pathlib import Path


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    return (Path(base) if base else Path.home() / ".local" / "state") / "hidctl"
