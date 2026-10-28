"""Registro de DPI do mouse: decodificação, tabela de códigos e plano de alteração.

Layout do bloco lido por perfil [FONTE; a ser confirmado pela leitura física]:

    byte 0       nível ativo (0-4)
    byte 1       0
    byte 2 + 6i  nível i: enabled, x_code, x_flag, y_code, y_flag, pad   (i = 0..4)

Total de 32 bytes, lidos em ``PROFILE_BASES[perfil]``.

[LOCAL] Nos 5 perfis lidos neste aparelho, todos os 25 registros têm ``y_code == x_code``,
flags 0 e ``pad`` 0; o byte 0 do bloco é igual ao número do perfil. Por isso a escrita
de um nível grava os 4 bytes ``x_code, x_flag, y_code, y_flag`` mantendo X = Y e os flags.
"""

from dataclasses import dataclass

from ...core.errors import ProtocolError, ValidationError

PROFILE_BASES = (0x042, 0x102, 0x1B2, 0x262, 0x312)  # [FONTE]
BLOCK_SIZE = 32
LEVELS = 5
RECORD_SIZE = 6
RECORD_OFFSET = 2
WRITE_RUN = 4  # x_code, x_flag, y_code, y_flag
CODE_MIN, CODE_MAX = 2, 140  # [FONTE]

# Fator empírico [FONTE]: DPI ≈ código × 10000/225 × 2^flag. É só uma estimativa;
# nenhuma fonte mediu o CPI real.
_ESTIMATE_FACTOR = 10000 / 225


@dataclass(frozen=True)
class Level:
    enabled: int
    x_code: int
    x_flag: int
    y_code: int
    y_flag: int
    pad: int

    def estimate(self) -> int:
        return estimate_dpi(self.x_code, self.x_flag)


@dataclass(frozen=True)
class DpiBlock:
    profile: int
    address: int
    raw: bytes
    active_level: int
    levels: tuple[Level, ...]
    token: object | None = None  # identifica a sessão que fez a leitura


@dataclass(frozen=True)
class CodeEntry:
    nominal: int
    code: int
    flag: int
    evidence: str  # ex.: "device", "sources>=2"


@dataclass(frozen=True)
class WritePlan:
    profile: int
    level: int
    address: int
    old: bytes
    new: bytes
    nominal: int
    block_raw: bytes
    token: object | None


def _current_run(level: Level) -> bytes:
    return bytes([level.x_code, level.x_flag, level.y_code, level.y_flag])


def _new_run(code: int, level: Level) -> bytes:
    """Os 4 bytes gravados: X e Y com o mesmo código; flags como lidos."""
    return bytes([code, level.x_flag, code, level.y_flag])


def estimate_dpi(code: int, flag: int) -> int:
    return round(code * _ESTIMATE_FACTOR * (2**flag))


def record_address(profile: int, level: int) -> int:
    return PROFILE_BASES[profile] + RECORD_OFFSET + RECORD_SIZE * level


def code_address(profile: int, level: int) -> int:
    """Endereço do byte ``x_code`` do nível."""
    return record_address(profile, level) + 1


def writable_addresses() -> frozenset[int]:
    return frozenset(code_address(p, i) for p in range(len(PROFILE_BASES)) for i in range(LEVELS))


def decode_block(profile: int, raw: bytes, token: object | None = None) -> DpiBlock:
    """Decodifica 32 bytes; qualquer incoerência levanta ``ProtocolError`` (hipótese de layout errada)."""
    if (
        not isinstance(profile, int)
        or isinstance(profile, bool)
        or not 0 <= profile < len(PROFILE_BASES)
    ):
        raise ValidationError(f"perfil inválido: {profile!r}")
    if len(raw) != BLOCK_SIZE:
        raise ProtocolError(f"bloco de DPI com {len(raw)} bytes, esperado {BLOCK_SIZE}")
    active = raw[0]
    if active >= LEVELS:
        raise ProtocolError(f"nível ativo fora de 0-4: {active}")
    levels = []
    for i in range(LEVELS):
        start = RECORD_OFFSET + RECORD_SIZE * i
        enabled, x_code, x_flag, y_code, y_flag, pad = raw[start : start + RECORD_SIZE]
        if enabled not in (0, 1) or x_flag not in (0, 1):
            raise ProtocolError(
                f"registro do nível {i} incoerente: {raw[start : start + RECORD_SIZE].hex(' ')}"
            )
        if not CODE_MIN <= x_code <= CODE_MAX:
            raise ProtocolError(f"código X do nível {i} fora de {CODE_MIN}-{CODE_MAX}: {x_code}")
        levels.append(Level(enabled, x_code, x_flag, y_code, y_flag, pad))
    return DpiBlock(profile, PROFILE_BASES[profile], bytes(raw), active, tuple(levels), token)


def plan_level_change(
    block: DpiBlock, level: int, target_dpi: int, table: dict[int, CodeEntry]
) -> WritePlan:
    """Planeja trocar **somente** o byte ``x_code`` de um nível, sem enviar nada.

    Rejeita: nível inválido, nível desabilitado, DPI fora da tabela, mudança de ``flag``
    (fora do escopo desta etapa) e valor igual ao atual.
    """
    if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level < LEVELS:
        raise ValidationError(f"nível inválido: {level!r}")
    if isinstance(target_dpi, bool) or not isinstance(target_dpi, int):
        raise ValidationError(f"DPI inválido: {target_dpi!r}")
    entry = table.get(target_dpi)
    if entry is None:
        raise ValidationError(f"DPI {target_dpi} não está na tabela de códigos verificados")
    current = block.levels[level]
    if not current.enabled:
        raise ValidationError(f"nível {level} está desabilitado")
    if current.y_code != current.x_code or current.y_flag != current.x_flag:
        raise ValidationError(f"nível {level} tem X e Y diferentes; não é alterado automaticamente")
    if entry.flag != current.x_flag:
        raise ValidationError("mudança de flag fora do escopo desta etapa")
    if entry.code == current.x_code:
        raise ValidationError(f"nível {level} já usa o código {entry.code:#04x}")
    return WritePlan(
        profile=block.profile,
        level=level,
        address=code_address(block.profile, level),
        old=_current_run(current),
        new=_new_run(entry.code, current),
        nominal=target_dpi,
        block_raw=block.raw,
        token=block.token,
    )


def plan_code_restore(block: DpiBlock, level: int, original_code: int) -> WritePlan:
    """Planeja devolver o byte ``x_code`` de um nível ao valor **lido antes** no aparelho.

    A evidência do valor é a própria leitura anterior (backup), não a tabela de códigos.
    Mantém as mesmas guardas de :func:`plan_level_change`, exceto a de tabela.
    """
    if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level < LEVELS:
        raise ValidationError(f"nível inválido: {level!r}")
    if (
        isinstance(original_code, bool)
        or not isinstance(original_code, int)
        or not CODE_MIN <= original_code <= CODE_MAX
    ):
        raise ValidationError(f"código inválido: {original_code!r}")
    current = block.levels[level]
    if not current.enabled:
        raise ValidationError(f"nível {level} está desabilitado")
    if current.y_code != current.x_code or current.y_flag != current.x_flag:
        raise ValidationError(f"nível {level} tem X e Y diferentes; não é alterado automaticamente")
    if original_code == current.x_code:
        raise ValidationError(f"nível {level} já usa o código {original_code:#04x}")
    return WritePlan(
        profile=block.profile,
        level=level,
        address=code_address(block.profile, level),
        old=_current_run(current),
        new=_new_run(original_code, current),
        nominal=estimate_dpi(original_code, current.x_flag),
        block_raw=block.raw,
        token=block.token,
    )
