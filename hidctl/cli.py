"""CLI de diagnóstico do projeto."""

import argparse
import json
from datetime import datetime
from pathlib import Path

from .hid_devices import list_devices


def _devices() -> int:
    try:
        devices = list_devices()
    except RuntimeError as exc:
        print(f"Erro: {exc}")
        return 1

    if not devices:
        print("Nenhum dispositivo HID encontrado.")
        return 0

    for device in devices:
        print(
            f"{device.vendor_id:04x}:{device.product_id:04x}  "
            f"{device.manufacturer or '-'} / {device.product or '-'}  "
            f"{device.path}"
        )
    return 0


def _dpi_inspect(print_node: bool) -> int:
    """Identifica o mouse pelo sysfs. Não abre nenhum nó hidraw."""
    from .core import discovery
    from .core.errors import DiscoveryError
    from .devices.fc30_mouse.spec import SPEC

    try:
        found = discovery.find(SPEC)
    except DiscoveryError as exc:
        print(f"Erro: {exc}")
        return 1
    if print_node:
        print(found.node)
        return 0
    print(f"dispositivo : {SPEC.name}")
    print(f"interface   : {found.interface_number} ({found.name}, {found.node})")
    print(f"VID:PID     : {found.vendor_id:04x}:{found.product_id:04x}")
    print(f"bcdDevice   : 0x{found.bcd_device:04x}")
    print(f"descritor   : {len(found.descriptor)} bytes")
    return 0


def _dpi_read(profile: str, trace: bool) -> int:
    """Leitura somente: ``F5 00``, ``F2`` do perfil ativo e dos blocos de DPI, ``F5 01``."""
    from .core import discovery
    from .core.errors import HidctlError, PermissionDenied
    from .core.transport import HidrawTransport, LoggingTransport
    from .devices.fc30_mouse import dpi
    from .devices.fc30_mouse.session import MouseSession
    from .devices.fc30_mouse.spec import SPEC

    try:
        found = discovery.find(SPEC)
        transport = HidrawTransport(found.node)
    except PermissionDenied as exc:
        print(f"Erro: {exc}")
        print("Sem permissão para o nó hidraw. Veja packaging/udev/ e docs/devices/cobra-m711.md.")
        return 2
    except HidctlError as exc:
        print(f"Erro: {exc}")
        return 1

    log = print if trace else (lambda _line: None)
    dump: dict[str, object] = {
        "interface": found.name,
        "bcdDevice": f"0x{found.bcd_device:04x}",
    }
    try:
        with (
            LoggingTransport(transport, log) as logged,
            MouseSession(logged) as session,
        ):
            active = session.read_active_profile()
            print(f"perfil ativo : {active}")
            wanted = (
                range(len(dpi.PROFILE_BASES))
                if profile == "all"
                else [active if profile == "active" else int(profile)]
            )
            blocks = []
            for number in wanted:
                block = session.read_dpi_block(number)
                blocks.append(block)
                print(f"perfil {number} @ {block.address:#06x}: {block.raw.hex(' ')}")
                print(f"  nível ativo: {block.active_level}")
                for index, level in enumerate(block.levels):
                    print(
                        f"  nível {index}: habilitado={level.enabled} x={level.x_code:#04x}/{level.x_flag} "
                        f"y={level.y_code:#04x}/{level.y_flag} (estimativa X ≈ {level.estimate()} DPI)"
                    )
            dump["active_profile"] = active
            dump["blocks"] = {str(b.profile): b.raw.hex(" ") for b in blocks}
    except HidctlError as exc:
        print(f"Erro: {exc}")
        return 1
    finally:
        transport.close()

    target = Path.home() / ".local" / "state" / "hidctl" / "dumps"
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"fc30-read-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(dump, indent=2))
    print(f"leitura salva em {path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="hidctl")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("devices", help="listar dispositivos HID")
    inspect = subparsers.add_parser(
        "dpi-inspect", help="identificar o mouse (não abre o nó hidraw)"
    )
    inspect.add_argument("--print-node", action="store_true", help="imprime só o caminho do nó")
    read = subparsers.add_parser("dpi-read", help="ler o DPI do mouse (somente leitura)")
    read.add_argument(
        "--profile",
        default="active",
        choices=["active", "all", "0", "1", "2", "3", "4"],
    )
    read.add_argument("--trace", action="store_true", help="mostra o tráfego em hexadecimal")
    args = parser.parse_args()

    if args.command == "devices":
        return _devices()
    if args.command == "dpi-inspect":
        return _dpi_inspect(args.print_node)
    if args.command == "dpi-read":
        return _dpi_read(args.profile, args.trace)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
