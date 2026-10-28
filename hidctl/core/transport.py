"""Transporte de Feature Reports via ``/dev/hidrawN``.

Documentação consultada: kernel ``Documentation/hid/hidraw`` (HIDIOCSFEATURE e
HIDIOCGFEATURE usam o endpoint de controle; o primeiro byte do buffer é o Report ID e
``len`` deve ser um a mais que o relatório) e ``include/uapi/linux/hidraw.h``:

    HIDIOCSFEATURE(len) = _IOC(_IOC_WRITE|_IOC_READ, 'H', 0x06, len)
    HIDIOCGFEATURE(len) = _IOC(_IOC_WRITE|_IOC_READ, 'H', 0x07, len)

``_IOC``: nr nos bits 0-7, tipo em 8-15, tamanho em 16-29 e direção em 30-31
(``asm-generic/ioctl.h``).
"""

import errno
import fcntl
import os
from collections.abc import Callable
from typing import Protocol

from .errors import DeviceGone, IoFailure, PermissionDenied, TransportError

_IOC_WRITE, _IOC_READ = 1, 2
_NR_BITS, _TYPE_BITS, _SIZE_BITS = 8, 8, 14
_TYPE_SHIFT = _NR_BITS
_SIZE_SHIFT = _TYPE_SHIFT + _TYPE_BITS
_DIR_SHIFT = _SIZE_SHIFT + _SIZE_BITS
_MAX_SIZE = (1 << _SIZE_BITS) - 1


def _ioc(direction: int, kind: str, number: int, size: int) -> int:
    if not 0 < size <= _MAX_SIZE:
        raise ValueError(f"tamanho de ioctl inválido: {size}")
    return (direction << _DIR_SHIFT) | (ord(kind) << _TYPE_SHIFT) | number | (size << _SIZE_SHIFT)


def hidiocsfeature(length: int) -> int:
    return _ioc(_IOC_WRITE | _IOC_READ, "H", 0x06, length)


def hidiocgfeature(length: int) -> int:
    return _ioc(_IOC_WRITE | _IOC_READ, "H", 0x07, length)


class FeatureTransport(Protocol):
    def set_feature(self, data: bytes) -> None:
        """Envia um Feature Report; ``data[0]`` é o Report ID."""

    def get_feature(self, report_id: int, length: int) -> bytes:
        """Lê um Feature Report de ``length`` bytes (inclui o Report ID no início)."""

    def close(self) -> None: ...


def _map_oserror(exc: OSError, action: str) -> TransportError:
    if exc.errno in (errno.EACCES, errno.EPERM):
        return PermissionDenied(f"{action}: sem permissão ({exc.strerror})")
    if exc.errno in (errno.ENODEV, errno.ENXIO, errno.ENOENT):
        return DeviceGone(f"{action}: dispositivo ausente ({exc.strerror})")
    return IoFailure(f"{action}: {exc.strerror or exc}")


class HidrawTransport:
    """Abre o nó uma única vez; não solta o driver do kernel nem usa libusb."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        opener: Callable[[str, int], int] = os.open,
        ioctl: Callable[..., int] = fcntl.ioctl,
        closer: Callable[[int], None] = os.close,
    ) -> None:
        self._path = os.fspath(path)
        self._ioctl = ioctl
        self._close = closer
        try:
            self._fd: int | None = opener(self._path, os.O_RDWR)
        except OSError as exc:
            raise _map_oserror(exc, f"abrir {self._path}") from exc

    def _require_fd(self) -> int:
        if self._fd is None:
            raise IoFailure("transporte já fechado")
        return self._fd

    def set_feature(self, data: bytes) -> None:
        fd = self._require_fd()
        buffer = bytearray(data)
        try:
            written = self._ioctl(fd, hidiocsfeature(len(buffer)), buffer, True)
        except OSError as exc:
            raise _map_oserror(exc, "SET_FEATURE") from exc
        if written != len(data):
            raise IoFailure(f"SET_FEATURE: enviados {written} de {len(data)} bytes")

    def get_feature(self, report_id: int, length: int) -> bytes:
        fd = self._require_fd()
        buffer = bytearray(length)
        buffer[0] = report_id
        try:
            received = self._ioctl(fd, hidiocgfeature(length), buffer, True)
        except OSError as exc:
            raise _map_oserror(exc, "GET_FEATURE") from exc
        if received <= 0:
            raise IoFailure(f"GET_FEATURE: resposta vazia ({received})")
        return bytes(buffer[:received])

    def close(self) -> None:
        if self._fd is not None:
            fd, self._fd = self._fd, None
            self._close(fd)

    def __enter__(self) -> "HidrawTransport":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class LoggingTransport:
    """Envolve outro transporte registrando todo o tráfego em hexadecimal."""

    def __init__(self, inner: FeatureTransport, log: Callable[[str], None]) -> None:
        self._inner, self._log = inner, log

    def set_feature(self, data: bytes) -> None:
        self._log(f"SET {data.hex(' ')}")
        try:
            self._inner.set_feature(data)
        except Exception as exc:
            self._log(f"SET falhou: {exc}")
            raise

    def get_feature(self, report_id: int, length: int) -> bytes:
        self._log(f"GET id={report_id:#04x} len={length}")
        try:
            received = self._inner.get_feature(report_id, length)
        except Exception as exc:
            self._log(f"GET falhou: {exc}")
            raise
        self._log(f"RSP {received.hex(' ')}")
        return received

    def close(self) -> None:
        self._inner.close()

    def __enter__(self) -> "LoggingTransport":
        return self

    def __exit__(self, *_: object) -> None:
        pass  # quem criou o transporte interno é quem o fecha
