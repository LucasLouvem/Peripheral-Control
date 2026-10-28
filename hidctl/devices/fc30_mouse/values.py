"""Valores de DPI liberados para escrita e a evidência de cada um.

Não há campo numérico com limites e passo: o mínimo, o máximo e os incrementos aceitos pelo
aparelho **não foram comprovados**. A interface oferece uma lista de valores validados.

Cada valor é um par (rótulo nominal, código/flag guardado no aparelho). O rótulo nominal
vem da tabela de uma fonte externa (E2, ``mouse_m908``); o aparelho só guarda o código. A
estimativa física (``código × 10000/225 × 2^flag``, fonte E1) **não** foi medida.

Níveis de evidência (``Evidence``):

* ``TESTED_PERCEIVED``: gravado no aparelho, relido byte a byte e o efeito foi percebido
  pelo usuário (800, 1000, 5000);
* ``WRITTEN_READBACK``: gravado no aparelho e relido byte a byte; **sem** medição física nem
  percepção registrada;
* ``READ_ONLY``: o código existe no aparelho (lido), mas nunca foi gravado por este projeto;
* ``SOURCE_ONLY``: só aparece em fontes externas. Nunca é oferecido.

Só os dois primeiros níveis são liberados para escrita.
"""

from dataclasses import dataclass
from enum import Enum

from .dpi import CodeEntry, estimate_dpi


class Evidence(Enum):
    TESTED_PERCEIVED = "testado no aparelho"
    WRITTEN_READBACK = "gravado e relido no aparelho"
    READ_ONLY = "lido no aparelho, nunca gravado"
    SOURCE_ONLY = "somente em fontes externas"


WRITABLE = (Evidence.TESTED_PERCEIVED, Evidence.WRITTEN_READBACK)


@dataclass(frozen=True)
class ValueEntry:
    nominal: int
    code: int
    flag: int
    evidence: Evidence

    @property
    def writable(self) -> bool:
        return self.evidence in WRITABLE

    @property
    def estimate(self) -> int:
        return estimate_dpi(self.code, self.flag)


_T, _W = Evidence.TESTED_PERCEIVED, Evidence.WRITTEN_READBACK

# Ordem crescente de DPI. Todos com flag 0 (o flag 1 nunca foi gravado). Os seis ``_W`` foram
# gravados no nível 5 do perfil 0, relidos byte a byte e restaurados em 2026-10-28 (docs/devices/cobra-m711.md).
VALUES: tuple[ValueEntry, ...] = (
    ValueEntry(500, 0x0B, 0, _W),
    ValueEntry(800, 0x12, 0, _T),
    ValueEntry(1000, 0x16, 0, _T),
    ValueEntry(1200, 0x1B, 0, _W),
    ValueEntry(2000, 0x2E, 0, _W),
    ValueEntry(2400, 0x37, 0, _W),
    ValueEntry(3000, 0x45, 0, _W),
    ValueEntry(3600, 0x53, 0, _W),
    ValueEntry(5000, 0x73, 0, _T),
)


def writable_values() -> tuple[ValueEntry, ...]:
    return tuple(v for v in VALUES if v.writable)


def code_table() -> dict[int, CodeEntry]:
    """Tabela aceita por ``plan_level_change``: somente valores liberados."""
    return {
        v.nominal: CodeEntry(v.nominal, v.code, v.flag, v.evidence.name) for v in writable_values()
    }


def by_code(code: int, flag: int) -> ValueEntry | None:
    for entry in VALUES:
        if (entry.code, entry.flag) == (code, flag):
            return entry
    return None


def by_nominal(nominal: int) -> ValueEntry | None:
    for entry in VALUES:
        if entry.nominal == nominal:
            return entry
    return None
