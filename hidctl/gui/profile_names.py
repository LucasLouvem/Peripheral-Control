"""Nomes dos perfis: guardados **só neste computador** (o mouse não guarda nomes).

Arquivo JSON em ``~/.local/state/hidctl/profile-names.json``. Sem caminho (modo ``--demo`` e
testes), os nomes ficam só em memória. Um arquivo ilegível é ignorado, nunca apagado.
"""

import json
import os
import tempfile
from pathlib import Path

PROFILE_COUNT = 5
MAX_LENGTH = 24


def default_name(profile: int) -> str:
    return f"Perfil {profile + 1}"


class ProfileNames:
    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path else None
        self._names: dict[int, str] = {}
        self._count = 1  # perfis mostrados (o mouse tem 5 fixos; os demais ficam ocultos até o usuário "adicionar")
        if self._path is not None:
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text())
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        count = data.get("count")
        if isinstance(count, int) and not isinstance(count, bool) and 1 <= count <= PROFILE_COUNT:
            self._count = count
        for key, value in data.items():
            if key.isdigit() and 0 <= int(key) < PROFILE_COUNT and self._clean(value) is not None:
                self._names[int(key)] = self._clean(value)

    @staticmethod
    def _clean(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        text = " ".join(value.split())
        if not text or len(text) > MAX_LENGTH or any(ord(c) < 32 for c in text):
            return None
        return text

    @property
    def count(self) -> int:
        return self._count

    def set_count(self, count: int) -> bool:
        """Quantos perfis mostrar (1 a 5). ``ValueError`` fora disso; devolve se foi gravado em disco."""
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= PROFILE_COUNT:
            raise ValueError(f"quantidade de perfis inválida: {count!r}")
        self._count = count
        return self._save()

    def name(self, profile: int) -> str:
        return self._names.get(profile, default_name(profile))

    def set_name(self, profile: int, text: str) -> bool:
        """Renomeia. ``ValueError`` se o nome for inválido; devolve se foi gravado em disco.

        Vazio volta ao nome padrão. Uma falha ao gravar mantém o nome só em memória e devolve ``False``.
        """
        if (
            isinstance(profile, bool)
            or not isinstance(profile, int)
            or not 0 <= profile < PROFILE_COUNT
        ):
            raise ValueError(f"perfil inválido: {profile!r}")
        if not isinstance(text, str):
            raise ValueError("o nome deve ser um texto")
        if not text.strip():
            self._names.pop(profile, None)
        else:
            clean = self._clean(text)
            if clean is None:
                raise ValueError(
                    f"nome inválido (use até {MAX_LENGTH} caracteres, sem caracteres de controle)"
                )
            self._names[profile] = clean
        return self._save()

    def _save(self) -> bool:
        if self._path is None:
            return True
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self._path.parent, prefix=".names-")
            with os.fdopen(fd, "w") as handle:
                json.dump(
                    {
                        **{str(k): v for k, v in sorted(self._names.items())},
                        "count": self._count,
                    },
                    handle,
                    ensure_ascii=False,
                )
            os.replace(tmp, self._path)
        except OSError:
            return False
        return True
