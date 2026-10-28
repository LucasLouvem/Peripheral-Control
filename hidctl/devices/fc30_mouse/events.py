"""Eventos que o mouse envia sozinho: troca do nível de DPI pelo botão físico.

Observado no aparelho (docs/devices/cobra-m711.md): a cada aperto do botão de DPI a
interface 2 emite o Input Report ``08 02 <n> 00 00 00 00 00`` com ``n`` = novo nível (0 a 4),
exatamente o valor que passa a constar no byte 0 do bloco de DPI. O mouse não passa dos
extremos: apertar de novo no nível 4 repete o evento ``08 02 04``.

Escutar é **somente leitura**: abre o nó separadamente, não envia relatório algum e não abre
sessão (``F5``), então não interfere em leituras e gravações.
"""

import errno
import os
import select
import threading
from collections.abc import Callable

from ...core import discovery
from ...core.errors import DiscoveryError
from .dpi import LEVELS
from .spec import SPEC

REPORT_ID = 0x08
LEVEL_EVENT = 0x02
RETRY_SECONDS = 2.0
POLL_SECONDS = 0.25


def parse_level_event(data: bytes) -> int | None:
    """Nível (0-4) de um evento de troca de DPI, ou ``None`` se não for um (ou for inválido)."""
    if len(data) != 8 or data[0] != REPORT_ID or data[1] != LEVEL_EVENT:
        return None
    level = data[2]
    return level if level < LEVELS else None


def _open_node() -> int:
    found = discovery.find(SPEC)
    return os.open(found.node, os.O_RDONLY | os.O_NONBLOCK)


def listen(
    stop: threading.Event,
    on_level: Callable[[int], None],
    opener: Callable[[], int] = _open_node,
    sleep: Callable[[float], None] | None = None,
) -> None:
    """Escuta até ``stop``. Se o mouse sumir ou não houver acesso, tenta de novo a cada 2 s."""
    wait = sleep or stop.wait
    while not stop.is_set():
        try:
            fd = opener()
        except (DiscoveryError, OSError):
            wait(RETRY_SECONDS)
            continue
        try:
            while not stop.is_set():
                ready, _, _ = select.select([fd], [], [], POLL_SECONDS)
                if not ready:
                    continue
                try:
                    data = os.read(fd, 64)
                except BlockingIOError:
                    continue
                except OSError as exc:
                    if exc.errno in (errno.ENODEV, errno.EIO, errno.ENXIO, errno.EBADF):
                        break  # desconectado: volta a procurar o aparelho
                    raise
                if not data:
                    break
                level = parse_level_event(data)
                if level is not None:
                    on_level(level)
        finally:
            os.close(fd)
        if not stop.is_set():
            wait(RETRY_SECONDS)
