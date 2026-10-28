"""Ponto de entrada: ``python -m hidctl.gui`` (ou ``hidctl-gui``)."""

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

SIZE_PATTERN = re.compile(r"^(\d+)x(\d+)$")
MIN_SIDE, MAX_SIDE = 400, 8000


def parse_size(text: str) -> tuple[int, int]:
    """Converte ``LARGURAxALTURA``; recusa formatos e tamanhos inválidos."""
    match = SIZE_PATTERN.match(text)
    if not match:
        raise argparse.ArgumentTypeError(f"tamanho inválido: {text!r}; use LARGURAxALTURA")
    width, height = int(match.group(1)), int(match.group(2))
    if not (MIN_SIDE <= width <= MAX_SIDE and MIN_SIDE <= height <= MAX_SIDE):
        raise argparse.ArgumentTypeError(
            f"tamanho fora do intervalo {MIN_SIDE}–{MAX_SIDE} px: {text!r}"
        )
    return width, height


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hidctl-gui",
        description=(
            'Peripheral Control. Lê o DPI e a iluminação do mouse ao abrir e só grava ao clicar em "Salvar".'
        ),
    )
    parser.add_argument(
        "--size",
        type=parse_size,
        metavar="LARGURAxALTURA",
        help="tamanho inicial da janela",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="usa um mouse SIMULADO em memória (não acessa nenhum dispositivo real)",
    )
    parser.add_argument(
        "--screenshot",
        type=Path,
        metavar="ARQUIVO.png",
        help="lê o mouse, salva uma captura da janela e encerra (usa 'offscreen' se nenhuma plataforma estiver definida)",
    )
    return parser


def build_controller(demo: bool):
    """Cria o controlador de DPI: simulado (``--demo``) ou o aparelho real."""
    from .._paths import state_dir
    from ..devices.fc30_mouse.dpi_service import DpiController, open_mouse

    if demo:
        from ..devices.fc30_mouse.simulator import MouseSimulator

        simulator = MouseSimulator()
        return DpiController(simulator.connect, Path(tempfile.mkdtemp(prefix="hidctl-demo-")), None)
    base = state_dir()
    return DpiController(open_mouse, base / "backups", base / "device.lock")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.screenshot is not None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("Erro: PySide6 não está instalado; use: python -m pip install -e '.[gui]'")
        return 1

    from . import theme
    from .dpi_model import DpiModel
    from .main_window import APP_NAME, MainWindow
    from .runner import ImmediateRunner, QtRunner

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setFont(theme.app_font())
    app.setStyleSheet(theme.stylesheet())

    runner = ImmediateRunner() if args.screenshot else QtRunner()
    from .._paths import state_dir
    from .profile_names import ProfileNames
    from .recent_colors import RecentColors

    names = ProfileNames(None if args.demo else state_dir() / "profile-names.json")
    recent = RecentColors(None if args.demo else state_dir() / "recent-colors.json")
    model = DpiModel(build_controller(args.demo), runner, names, recent=recent)
    window = MainWindow(model, simulated=args.demo)
    watcher = None
    if not args.demo and args.screenshot is None:
        from .watcher import LevelWatcher

        watcher = LevelWatcher()
        watcher.level_changed.connect(model.set_live_active)
        watcher.start()
        app.aboutToQuit.connect(watcher.stop)
    if args.size:
        window.resize(*args.size)
    window.show()
    app.aboutToQuit.connect(model.wait)

    if args.screenshot is not None:
        model.reload()  # leitura (sincrona); nunca grava
        app.processEvents()
        if not window.grab().save(str(args.screenshot), "PNG"):
            print(f"Erro: não foi possível salvar {args.screenshot}")
            return 1
        print(f"Captura salva em {args.screenshot}")
        return 0
    QTimer.singleShot(0, model.reload)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
