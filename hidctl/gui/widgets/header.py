"""Cabeçalho: dispositivo, estado real da conexão e perfil ativo (somente leitura)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import theme
from ..dpi_model import DpiModel
from .common import StatusDot

DEVICE_NAME = "Cobra M711"
DEVICE_SUBTITLE = "Kit S118"
SIMULATED_TOOLTIP = (
    "Modo simulado (--demo): dados fictícios em memória, nenhum mouse real é lido ou gravado."
)

# connection -> (texto, cor do ponto)
_STATUS = {
    "absent": ("Mouse não encontrado", theme.ORANGE),
    "permission": ("Sem permissão de acesso", theme.ORANGE),
    "protocol": ("Resposta inválida do mouse", theme.ORANGE),
    "unsupported": ("Modelo/revisão não suportados", theme.ORANGE),
    "error": ("Erro de comunicação", theme.ORANGE),
}


class Header(QWidget):
    """Título e, só quando há problema (mouse ausente, sem permissão…), uma linha de estado.

    Com o mouse funcionando não se mostra nada: o tipo de conexão não importa para controlá-lo.
    O selo SIMULADO só aparece com ``--demo``.
    """

    def __init__(self, model: DpiModel, simulated: bool = False) -> None:
        super().__init__()
        self._model = model
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        self.title = QLabel(DEVICE_NAME)
        self.title.setObjectName("title")
        self.subtitle = QLabel(DEVICE_SUBTITLE)
        self.subtitle.setObjectName("subtitle")
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_row.addWidget(self.title)
        title_row.addWidget(self.subtitle, 0, Qt.AlignmentFlag.AlignBottom)
        title_row.addStretch(1)
        status = QHBoxLayout()
        status.setContentsMargins(7, 0, 0, 0)
        status.setSpacing(12)
        self.dot = StatusDot(theme.TEXT_MUTE)
        status.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self.status = QLabel()
        self.status.setObjectName("status")
        self.badge = QLabel("SIMULADO")
        self.badge.setObjectName("badge")
        self.badge.setToolTip(SIMULATED_TOOLTIP)
        self.badge.setVisible(simulated)
        status.addWidget(self.status)
        status.addWidget(self.badge)
        status.addStretch(1)
        column.addLayout(title_row)
        column.addLayout(status)
        model.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        problem = _STATUS.get(self._model.connection)
        self.status.setText(problem[0] if problem else "")
        self.status.setVisible(problem is not None)
        self.dot.setVisible(problem is not None)
        if problem:
            self.dot.set_color(problem[1])
