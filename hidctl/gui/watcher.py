"""Observador do botão de DPI: thread que repassa os eventos do mouse à interface."""

import threading

from PySide6.QtCore import QThread, Signal

from ..devices.fc30_mouse import events


class LevelWatcher(QThread):
    """Emite ``level_changed(n)`` quando o botão físico troca o nível. Somente leitura."""

    level_changed = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._stop = threading.Event()

    def run(self) -> None:
        events.listen(self._stop, self.level_changed.emit)

    def stop(self) -> None:
        self._stop.set()
        self.wait(3000)
