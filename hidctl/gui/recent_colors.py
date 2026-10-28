"""Cores recentes do modal de iluminação: guardadas **só neste computador** (não vão ao mouse).

Arquivo JSON em ``~/.local/state/hidctl/recent-colors.json``. Sem caminho (``--demo`` e testes) ficam só em
memória. Um arquivo ilegível é ignorado, nunca apagado.
"""

import json
import os
import tempfile
from pathlib import Path

MAX_COLORS = 12


def _valid(value: object) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 3
        and all(isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255 for c in value)
    )


class RecentColors:
    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path else None
        self._colors: list[tuple[int, int, int]] = []
        if self._path is not None:
            try:
                data = json.loads(self._path.read_text())
            except (OSError, ValueError):
                return
            if isinstance(data, list):
                self._colors = [tuple(c) for c in data if _valid(c)][:MAX_COLORS]

    @property
    def colors(self) -> tuple[tuple[int, int, int], ...]:
        """Da mais recente para a mais antiga."""
        return tuple(self._colors)

    def add(self, rgb: tuple[int, int, int]) -> bool:
        """Põe ``rgb`` no topo (sem repetir). ``ValueError`` se inválida; devolve se foi gravada em disco."""
        if not _valid(rgb):
            raise ValueError(f"cor inválida: {rgb!r}")
        rgb = tuple(rgb)
        self._colors = [rgb] + [c for c in self._colors if c != rgb][: MAX_COLORS - 1]
        return self._save()

    def _save(self) -> bool:
        if self._path is None:
            return True
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self._path.parent, prefix=".recent-")
            with os.fdopen(fd, "w") as handle:
                json.dump([list(c) for c in self._colors], handle)
            os.replace(tmp, self._path)
        except OSError:
            return False
        return True
