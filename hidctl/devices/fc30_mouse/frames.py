"""Quadros do protocolo de configuração (Report ID 2, 16 bytes).

Layout [FONTE] (projetos externos; a leitura foi verificada primeiro neste aparelho
conforme docs/devices/cobra-m711.md):

    byte  0     1    2        3        4    5 6 7    8..15
          02    cmd  addr_lo  addr_hi  len  00 00 00 dados (até 8 bytes)

Resposta de leitura (GET_FEATURE do mesmo ID): ``02 08 addr_lo 6X len 00 FA FA`` seguido
de ``len`` bytes de dados, onde ``6X`` = ``0x60 | addr_hi`` [FONTE].
"""

from ...core.errors import ProtocolError, ValidationError

REPORT_ID = 0x02
FRAME_SIZE = 16
HEADER_SIZE = 8
MAX_READ = 50  # maior leitura vista nas fontes; o hardware não foi testado além disso
MAX_WRITE = 8  # dados que cabem em um quadro de 16 bytes

OP_APPLY = 0xF1
OP_READ = 0xF2
OP_WRITE = 0xF3
OP_LOCK = 0xF5

AREA_DPI = 0x02  # F1 02 02 [FONTE]
AREA_LIGHTING = 0x04  # F1 02 04 [FONTE: OpenRGB e mouse_m908]
RESPONSE_MARK = 0x08
RESPONSE_PAD = b"\xfa\xfa"
ADDR_HIGH_BASE = 0x60


def _check_address(address: int, count: int) -> None:
    if isinstance(address, bool) or not isinstance(address, int) or not 0 <= address <= 0xFFFF:
        raise ValidationError(f"endereço inválido: {address!r}")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValidationError(f"quantidade inválida: {count!r}")
    if address + count - 1 > 0xFFFF:
        raise ValidationError("intervalo ultrapassa 0xFFFF")


def _frame(op: int, b2: int, b3: int, b4: int, data: bytes = b"") -> bytes:
    body = bytes([REPORT_ID, op, b2, b3, b4, 0, 0, 0]) + data
    return body.ljust(FRAME_SIZE, b"\x00")


def lock_frame(locked: bool) -> bytes:
    """``02 F5 00`` abre a sessão; ``02 F5 01`` fecha [FONTE]."""
    return _frame(OP_LOCK, 0x01 if locked else 0x00, 0, 0)


def read_frame(address: int, count: int) -> bytes:
    _check_address(address, count)
    if count > MAX_READ:
        raise ValidationError(f"leitura de {count} bytes excede {MAX_READ}")
    return _frame(OP_READ, address & 0xFF, address >> 8, count)


def write_frame(address: int, data: bytes) -> bytes:
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise ValidationError("dados de escrita vazios ou de tipo inválido")
    if len(data) > MAX_WRITE:
        raise ValidationError(f"escrita de {len(data)} bytes excede {MAX_WRITE}")
    _check_address(address, len(data))
    return _frame(OP_WRITE, address & 0xFF, address >> 8, len(data), bytes(data))


def apply_frame(area: int) -> bytes:
    """``02 F1 02 <área>`` aplica uma área já escrita [FONTE]."""
    if isinstance(area, bool) or not isinstance(area, int) or not 0 < area <= 0xFF:
        raise ValidationError(f"área inválida: {area!r}")
    return _frame(OP_APPLY, 0x02, area, 0)


def response_length(count: int) -> int:
    return HEADER_SIZE + count


def parse_read_response(raw: bytes, address: int, count: int) -> bytes:
    """Valida o cabeçalho e devolve exatamente ``count`` bytes de dados."""
    _check_address(address, count)
    need = response_length(count)
    if len(raw) < need:
        raise ProtocolError(f"resposta curta: {len(raw)} bytes, esperado {need}")
    header = raw[:HEADER_SIZE]
    # [TESTE] Em endereço ímpar o aparelho ecoa o endereço par anterior (pedido 0x449 → cabeçalho 0x448),
    # mas os dados começam no endereço pedido (confirmado deslocando a janela em 1 byte).
    echoed = address & ~1
    expected = bytes(
        [
            REPORT_ID,
            RESPONSE_MARK,
            echoed & 0xFF,
            ADDR_HIGH_BASE | (echoed >> 8),
            count,
            0,
            0xFA,
            0xFA,
        ]
    )
    if header != expected:
        raise ProtocolError(
            f"cabeçalho inesperado: {header.hex(' ')} (esperado {expected.hex(' ')})"
        )
    return bytes(raw[HEADER_SIZE:need])
