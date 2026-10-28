"""Descoberta HID. Nenhuma operação de escrita é feita neste módulo."""

from .models import DeviceInfo


def list_devices() -> list[DeviceInfo]:
    """Lista dispositivos HID conectados, se hidapi estiver instalado."""
    try:
        import hid  # type: ignore
    except ImportError as exc:
        raise RuntimeError("hidapi não está instalado; use: python -m pip install hidapi") from exc

    devices: list[DeviceInfo] = []
    for item in hid.enumerate():
        devices.append(
            DeviceInfo(
                path=item["path"].decode(errors="replace")
                if isinstance(item["path"], bytes)
                else str(item["path"]),
                vendor_id=int(item.get("vendor_id", 0)),
                product_id=int(item.get("product_id", 0)),
                manufacturer=item.get("manufacturer_string"),
                product=item.get("product_string"),
            )
        )
    return devices
