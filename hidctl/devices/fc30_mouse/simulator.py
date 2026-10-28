"""Mouse simulado: memória, sessão e quadros ``F1/F2/F3/F5``, com falhas injetáveis.

Implementa ``FeatureTransport`` e interpreta os quadros como o aparelho real foi observado
(docs/devices/cobra-m711.md). Usado nos testes e no modo ``--demo`` da interface; **nunca**
toca em hardware.
"""

from contextlib import contextmanager

from ...core.errors import DeviceGone, IoFailure, NoDeviceFound, PermissionDenied
from .session import MouseSession

BASES = (0x042, 0x102, 0x1B2, 0x262, 0x312)

# Blocos reais lidos do aparelho em 2026-10-28 (perfil 0 personalizado; perfis 1-4 de fábrica).
P0 = "00 00 01 12 00 12 00 00 01 1b 00 1b 00 00 01 37 00 37 00 00 01 53 00 53 00 00 01 73 00 73 00 00"
PN = "{p:02x} 00 01 0b 00 0b 00 00 01 16 00 16 00 00 01 2e 00 2e 00 00 01 45 00 45 00 00 01 73 00 73 00 00"


# Iluminação lida do aparelho em 2026-10-28: perfil 0 = vermelho em respiração; perfis 1-4 = onda de fábrica.
L0 = "ff 00 00 01 02 04 03 80"
LN = "ff 00 00 02 04 00 02 80"
LIGHT_BASE = 0x449


def initial_memory() -> bytearray:
    memory = bytearray(0x480)
    for profile in range(5):
        start = LIGHT_BASE + 8 * profile
        memory[start : start + 8] = bytes.fromhex(L0 if profile == 0 else LN)
    memory[0x2C] = 0  # perfil ativo
    memory[BASES[0] : BASES[0] + 32] = bytes.fromhex(P0)
    for profile in range(1, 5):
        memory[BASES[profile] : BASES[profile] + 32] = bytes.fromhex(PN.format(p=profile))
    return memory


class MouseSimulator:
    def __init__(self):
        self.memory = initial_memory()
        self.frames: list[bytes] = []  # todo SET recebido, em ordem
        self.writes: list[tuple[int, bytes]] = []  # (endereço, dados) de cada F3 aplicado
        self.applies: list[int] = []  # área de cada F1
        self.sessions = 0
        self.locked = False
        self.pending: tuple[int, int] | None = None
        # falhas injetáveis
        self.absent = False
        self.permission_denied = False
        self.fail_write_number: int | None = None  # 1 = primeiro F3
        self.fail_write_applies_first = False  # falha depois de gravar (estado incerto)
        self.fail_after_frames: int | None = None  # desconecta depois de N SETs
        self.fail_apply = False
        self.corrupt_after_apply: dict[int, int] = {}  # endereço -> byte (releitura divergente)
        self.bad_header_on_read: int | None = (
            None  # número da leitura (1 = primeira) com cabeçalho inválido
        )
        self.on_read = None  # callback(n_leituras) para simular alteração externa
        self.reads = 0
        self._write_count = 0

    # --- conector (substitui open_mouse) ---
    @contextmanager
    def connect(self):
        if self.absent:
            raise NoDeviceFound("simulado: sem mouse")
        if self.permission_denied:
            raise PermissionDenied("simulado: sem permissão")
        self.sessions += 1
        with MouseSession(self) as session:
            yield session

    # --- FeatureTransport ---
    def set_feature(self, data: bytes) -> None:
        if self.absent:
            raise DeviceGone("simulado: desconectado")
        if self.fail_after_frames is not None and len(self.frames) >= self.fail_after_frames:
            self.absent = True
            raise DeviceGone("simulado: desconectado no meio da operação")
        self.frames.append(bytes(data))
        op = data[1]
        if data[0] != 2:
            raise IoFailure("report inesperado")
        if op == 0xF5:
            self.locked = data[2] == 0
        elif op == 0xF2:
            self._require_session("leitura")
            self.pending = (data[2] | data[3] << 8, data[4])
        elif op == 0xF3:
            self._require_session("escrita")
            self._write_count += 1
            address, count = data[2] | data[3] << 8, data[4]
            payload = bytes(data[8 : 8 + count])
            if self.fail_write_number == self._write_count:
                if self.fail_write_applies_first:
                    self.memory[address : address + count] = payload
                    self.writes.append((address, payload))
                raise IoFailure("simulado: falha na gravação")
            self.memory[address : address + count] = payload
            self.writes.append((address, payload))
        elif op == 0xF1:
            self._require_session("aplicação")
            if self.fail_apply:
                raise IoFailure("simulado: falha no F1")
            self.applies.append(data[3])
            for address, value in self.corrupt_after_apply.items():
                self.memory[address] = value

    def get_feature(self, report_id: int, length: int) -> bytes:
        if self.absent:
            raise DeviceGone("simulado: desconectado")
        address, count = self.pending
        self.reads += 1
        if self.on_read:
            self.on_read(self.reads)
        echoed = address & ~1  # o aparelho ecoa o endereço par anterior; os dados começam no pedido
        header = bytes([2, 8, echoed & 0xFF, 0x60 | (echoed >> 8), count, 0, 0xFA, 0xFA])
        if self.bad_header_on_read == self.reads:
            header = bytes([2, 7]) + header[2:]
        return header + bytes(self.memory[address : address + count])

    def close(self) -> None:
        pass

    def _require_session(self, what: str) -> None:
        if not self.locked:
            raise IoFailure(f"simulado: {what} fora da sessão")

    # --- utilidades ---
    def block(self, profile: int) -> bytes:
        return bytes(self.memory[BASES[profile] : BASES[profile] + 32])

    def set_level_code(self, profile: int, level: int, code: int) -> None:
        """Altera 'por fora' (como outro programa): X e Y do nível."""
        start = BASES[profile] + 2 + 6 * level
        self.memory[start + 1] = code
        self.memory[start + 3] = code

    def light_window(self, profile: int) -> bytes:
        start = LIGHT_BASE + 8 * profile
        return bytes(self.memory[start : start + 8])

    @property
    def f3_frames(self) -> list[bytes]:
        return [f for f in self.frames if f[1] == 0xF3]

    @property
    def f1_frames(self) -> list[bytes]:
        return [f for f in self.frames if f[1] == 0xF1]
