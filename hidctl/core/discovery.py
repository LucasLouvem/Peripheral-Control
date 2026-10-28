"""Descoberta de interfaces hidraw via sysfs, sem fixar números de ``/dev/hidrawN``.

A estrutura lida (todos os arquivos são somente leitura):
``class/hidraw/hidrawN/device`` é o dispositivo HID (``uevent`` traz ``HID_ID``,
``report_descriptor`` traz o descritor); o pai é a interface USB (``bInterfaceNumber``);
o avô é o dispositivo USB (``idVendor``, ``idProduct``, ``bcdDevice``).
"""

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from . import hid_descriptor
from .errors import (
    AmbiguousDevice,
    DescriptorError,
    DescriptorMismatch,
    NoDeviceFound,
    RevisionMismatch,
)


@dataclass(frozen=True)
class HidInterface:
    name: str
    node: Path
    sysfs: Path
    vendor_id: int
    product_id: int
    bcd_device: int
    interface_number: int
    descriptor: bytes


@dataclass(frozen=True)
class DeviceSpec:
    """Identidade e descritor esperados de um dispositivo suportado."""

    name: str
    vendor_id: int
    product_id: int
    bcd_device: int
    usage_page: int
    feature_sizes: Mapping[int, int]  # Report ID -> bytes no fio (com o ID)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def _hex_attr(path: Path) -> int | None:
    text = _read_text(path)
    try:
        return int(text, 16) if text else None
    except ValueError:
        return None


def _hid_id(device_dir: Path) -> tuple[int, int] | None:
    text = _read_text(device_dir / "uevent")
    for line in (text or "").splitlines():
        if line.startswith("HID_ID="):
            parts = line[len("HID_ID=") :].split(":")
            try:
                return int(parts[1], 16), int(parts[2], 16)
            except (IndexError, ValueError):
                return None
    return None


def scan(sysfs_root: Path = Path("/sys"), dev_root: Path = Path("/dev")) -> list[HidInterface]:
    """Lista todas as interfaces hidraw legíveis; entradas incompletas são ignoradas."""
    found: list[HidInterface] = []
    class_dir = sysfs_root / "class" / "hidraw"
    try:
        entries = sorted(class_dir.iterdir(), key=lambda p: p.name)
    except OSError:
        return found
    for entry in entries:
        device_dir = Path(os.path.realpath(entry / "device"))
        interface_dir = device_dir.parent
        usb_dir = interface_dir.parent
        ids = _hid_id(device_dir)
        number = _hex_attr(interface_dir / "bInterfaceNumber")
        bcd = _hex_attr(usb_dir / "bcdDevice")
        try:
            descriptor = (device_dir / "report_descriptor").read_bytes()
        except OSError:
            continue
        if ids is None or number is None or bcd is None:
            continue
        found.append(
            HidInterface(
                name=entry.name,
                node=dev_root / entry.name,
                sysfs=device_dir,
                vendor_id=ids[0],
                product_id=ids[1],
                bcd_device=bcd,
                interface_number=number,
                descriptor=descriptor,
            )
        )
    return found


def _descriptor_matches(spec: DeviceSpec, descriptor: bytes) -> bool:
    try:
        parsed = hid_descriptor.parse(descriptor)
    except DescriptorError:
        return False
    for report_id, wire in spec.feature_sizes.items():
        if parsed.wire_size("feature", report_id) != wire:
            return False
        if spec.usage_page not in parsed.pages_of("feature", report_id):
            return False
    return True


def select(spec: DeviceSpec, interfaces: Iterable[HidInterface]) -> HidInterface:
    """Escolhe a única interface que cumpre identidade, revisão e descritor de ``spec``."""
    same_id = [
        i for i in interfaces if (i.vendor_id, i.product_id) == (spec.vendor_id, spec.product_id)
    ]
    if not same_id:
        raise NoDeviceFound(
            f"{spec.name}: nenhum dispositivo {spec.vendor_id:04x}:{spec.product_id:04x}"
        )
    same_rev = [i for i in same_id if i.bcd_device == spec.bcd_device]
    if not same_rev:
        found = sorted({f"0x{i.bcd_device:04x}" for i in same_id})
        raise RevisionMismatch(
            f"{spec.name}: revisão encontrada {', '.join(found)}; suportada 0x{spec.bcd_device:04x}"
        )
    matching = [i for i in same_rev if _descriptor_matches(spec, i.descriptor)]
    if not matching:
        raise DescriptorMismatch(f"{spec.name}: nenhuma interface com o descritor esperado")
    if len(matching) > 1:
        names = ", ".join(i.name for i in matching)
        raise AmbiguousDevice(f"{spec.name}: mais de uma interface candidata ({names})")
    return matching[0]


def find(
    spec: DeviceSpec, sysfs_root: Path = Path("/sys"), dev_root: Path = Path("/dev")
) -> HidInterface:
    return select(spec, scan(sysfs_root, dev_root))
