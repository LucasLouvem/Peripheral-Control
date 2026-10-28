"""Bytes reais coletados do aparelho (docs/devices/cobra-m711.md)."""

import os
from pathlib import Path

MOUSE_BOOT = bytes.fromhex(
    "05 01 09 02 a1 01 09 01 a1 00 05 09 19 01 29 10 15 00 25 01 75 01 95 10 81 02 05 01 09 30 09 31 16 01 80 26 ff 7f 75 10 95 02 81 06 09 38 15 81 25 7f 75 08 95 01 81 06 05 0c 0a 38 02 95 01 81 06 c0 c0".replace(
        " ", ""
    )
)
KEYBOARD_BOOT = bytes.fromhex(
    "05 01 09 06 a1 01 05 07 19 e0 29 e7 15 00 25 01 75 01 95 08 81 02 95 01 75 08 81 01 95 06 75 08 15 00 26 ff 00 05 07 19 00 2a ff 00 81 00 c0".replace(
        " ", ""
    )
)
CONFIG_IFACE = bytes.fromhex(
    "05 0c 09 01 a1 01 85 01 05 0c 19 00 2a ff 0f 15 00 26 ff 0f 75 10 95 02 81 00 75 08 95 03 81 01 c0 "
    "06 a0 ff 09 01 a1 01 85 02 09 02 15 00 26 ff 00 75 08 95 0f b1 02 85 03 09 03 95 3f b1 02 "
    "85 04 09 04 95 ff b1 02 85 05 09 05 96 ff 03 b1 02 85 06 09 06 96 ff 07 b1 02 "
    "85 07 09 07 95 07 81 00 85 08 09 08 95 07 81 00 c0".replace(" ", "")
)


def make_usb_device(
    root: Path,
    usb_name: str,
    vid: int,
    pid: int,
    bcd: int,
    interfaces: list[tuple[int, bytes, str]],
) -> None:
    """Cria no ``root`` falso: devices/…/usbN/<usb_name>/<usb_name>:1.X/<hid>/ e class/hidraw/<hidrawN>/device."""
    usb_dir = root / "devices" / "pci0" / "usb1" / usb_name
    usb_dir.mkdir(parents=True, exist_ok=True)
    (usb_dir / "idVendor").write_text(f"{vid:04x}\n")
    (usb_dir / "idProduct").write_text(f"{pid:04x}\n")
    (usb_dir / "bcdDevice").write_text(f"{bcd:04x}\n")
    for number, descriptor, hidraw in interfaces:
        iface_dir = usb_dir / f"{usb_name}:1.{number}"
        hid_dir = iface_dir / f"0003:{vid:08X}:{pid:08X}.{number:04d}"
        hid_dir.mkdir(parents=True, exist_ok=True)
        (iface_dir / "bInterfaceNumber").write_text(f"{number:02x}\n")
        (hid_dir / "uevent").write_text(
            f"DRIVER=hid-generic\nHID_ID=0003:{vid:08X}:{pid:08X}\nHID_NAME=x\n"
        )
        (hid_dir / "report_descriptor").write_bytes(descriptor)
        class_dir = root / "class" / "hidraw" / hidraw
        class_dir.mkdir(parents=True, exist_ok=True)
        os.symlink(hid_dir, class_dir / "device")


def make_mouse(
    root: Path,
    hidraw_names=("hidraw3", "hidraw4", "hidraw5"),
    bcd: int = 0x0112,
    usb_name: str = "5-3",
) -> None:
    make_usb_device(
        root,
        usb_name,
        0x04D9,
        0xFC30,
        bcd,
        [
            (0, MOUSE_BOOT, hidraw_names[0]),
            (1, KEYBOARD_BOOT, hidraw_names[1]),
            (2, CONFIG_IFACE, hidraw_names[2]),
        ],
    )
