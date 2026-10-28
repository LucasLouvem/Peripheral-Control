"""Transporte falso que registra todo o tráfego e responde com dados roteirizados."""

from hidctl.core.errors import IoFailure


class FakeTransport:
    def __init__(self, responses=(), fail_set_at=None, fail_get_at=None):
        self.sent: list[bytes] = []
        self.gets: list[tuple[int, int]] = []
        self.responses = list(responses)
        self.fail_set_at = fail_set_at  # índice (0-based) do SET que deve falhar
        self.fail_get_at = fail_get_at
        self.closed = False

    def set_feature(self, data: bytes) -> None:
        index = len(self.sent)
        self.sent.append(bytes(data))
        if self.fail_set_at == index:
            raise IoFailure("falha simulada no SET")

    def get_feature(self, report_id: int, length: int) -> bytes:
        index = len(self.gets)
        self.gets.append((report_id, length))
        if self.fail_get_at == index:
            raise IoFailure("falha simulada no GET")
        return self.responses.pop(0)

    def close(self) -> None:
        self.closed = True


def response(address: int, data: bytes) -> bytes:
    """Resposta de leitura no formato documentado (montada à mão, independente do parser)."""
    return (
        bytes(
            [
                0x02,
                0x08,
                address & 0xFF,
                0x60 | (address >> 8),
                len(data),
                0x00,
                0xFA,
                0xFA,
            ]
        )
        + data
    )


def hx(text: str) -> bytes:
    return bytes.fromhex(text)
