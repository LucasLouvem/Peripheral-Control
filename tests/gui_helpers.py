"""Auxiliares dos testes de interface: aplicação Qt offscreen e janela ligada ao mouse simulado."""

import os
import tempfile
import unittest
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

try:
    from PySide6.QtCore import QPoint, QRect, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from hidctl.devices.fc30_mouse.dpi_service import DpiController
    from hidctl.devices.fc30_mouse.simulator import MouseSimulator
    from hidctl.gui import theme
    from hidctl.gui.dpi_model import DpiModel
    from hidctl.gui.main_window import MainWindow
    from hidctl.gui.runner import ImmediateRunner
except ImportError as exc:  # PySide6 é opcional (extra "gui")
    raise unittest.SkipTest(f"PySide6 indisponível: {exc}")

APP = QApplication.instance() or QApplication(["test"])
APP.setFont(theme.app_font())
APP.setStyleSheet(theme.stylesheet())


class DeferredRunner:
    """Guarda as tarefas para o teste decidir quando elas terminam (simula a thread de trabalho)."""

    def __init__(self):
        self.jobs = []

    def submit(self, job, on_done):
        self.jobs.append((job, on_done))

    def run_all(self):
        while self.jobs:
            job, on_done = self.jobs.pop(0)
            try:
                result, error = job(), None
            except Exception as exc:  # noqa: BLE001
                result, error = None, exc
            on_done(result, error)

    def wait(self):
        self.run_all()


def click(widget) -> None:
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
    APP.processEvents()


def rect_in(ancestor, widget) -> QRect:
    return QRect(widget.mapTo(ancestor, QPoint(0, 0)), widget.size())


class WindowCase(unittest.TestCase):
    """Janela com mouse simulado. ``self.fake`` registra todo quadro enviado ao 'aparelho'."""

    load_on_start = True
    runner_class = ImmediateRunner

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.fake = MouseSimulator()
        self.runner = self.runner_class()
        self.controller = DpiController(self.fake.connect, self.tmp / "backups", None)
        self.model = DpiModel(self.controller, self.runner)
        self.window = MainWindow(self.model, simulated=True)
        self.window.show()
        APP.processEvents()
        if self.load_on_start:
            self.model.reload()
            APP.processEvents()
        self.card = self.window.dpi_card
        self.bar = self.window.action_bar

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()

    def choose(self, level: int, dpi: int) -> None:
        """Arrasta o slider do nível até o valor, como o usuário faria (só edição local)."""
        column = self.card.columns[level]
        nominals = [o.nominal for o in column._options]
        self.assertIn(dpi, nominals, f"{dpi} não está na lista")
        column.slider.setValue(nominals.index(dpi))
        APP.processEvents()

    def texts(self):
        return [c.value_label.text() for c in self.card.columns]
