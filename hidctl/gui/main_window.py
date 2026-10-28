"""Janela principal: composição da tela "Visão geral"."""

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .dpi_model import DpiModel
from .widgets.action_bar import ActionBar
from .widgets.cards import DpiCard, LightingCard
from .widgets.common import Toast
from .widgets.header import Header
from .widgets.mouse_panel import MousePanel
from .widgets.sidebar import Sidebar

REFERENCE_SIZE = QSize(1000, 620)
MINIMUM_SIZE = QSize(900, 540)
FUTURE_NOTICE = "{name}: disponível futuramente"


APP_NAME = "Peripheral Control"


class MainWindow(QMainWindow):
    def __init__(
        self,
        model: DpiModel,
        assets_dir: Path | None = None,
        simulated: bool = False,
    ) -> None:
        super().__init__()
        self.model = model
        self._simulated = simulated
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(MINIMUM_SIZE)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar(assets_dir)
        layout.addWidget(self.sidebar)
        layout.addWidget(self._build_content(assets_dir), 1)

        self.toast = Toast(root)
        self.sidebar.unavailable.connect(self.show_unavailable)

        self.resize(REFERENCE_SIZE.boundedTo(self._available_size()))

    def _available_size(self) -> QSize:
        screen = self.screen()
        return screen.availableSize() if screen else REFERENCE_SIZE

    def _build_content(self, assets_dir: Path | None) -> QWidget:
        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(20, 14, 16, 18)
        top_layout.setSpacing(0)

        body = QWidget()
        body_row = QHBoxLayout(body)
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(18)

        # Coluna esquerda: cabeçalho, mouse (pequeno) e iluminação embaixo.
        left = QVBoxLayout()
        left.setSpacing(8)
        left.setContentsMargins(0, 0, 0, 0)
        self.header = Header(self.model, self._simulated)
        self.mouse_panel = MousePanel(self.model, assets_dir)
        self.lighting_card = LightingCard(self.model)
        left.addWidget(self.header)
        left.addWidget(self.mouse_panel, 1)
        left.addWidget(self.lighting_card)
        left_widget = QWidget()
        left_widget.setMinimumWidth(390)
        left_widget.setLayout(left)
        body_row.addWidget(left_widget, 46)

        # Coluna direita: perfil ativo e DPI. Macros ficam só na sua própria seção (futura).
        right = QVBoxLayout()
        right.setSpacing(8)
        right.setContentsMargins(0, 0, 0, 0)
        self.action_bar = ActionBar(self.model)
        self.dpi_card = DpiCard(self.model)
        right.addWidget(self.action_bar)
        right.addWidget(self.dpi_card, 1)
        right_widget = QWidget()
        right_widget.setMinimumWidth(380)
        right_widget.setLayout(right)
        body_row.addWidget(right_widget, 54)

        self.body_scroll = QScrollArea()
        self.body_scroll.setObjectName("body")
        self.body_scroll.setWidgetResizable(True)
        self.body_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.body_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body_scroll.setWidget(body)
        top_layout.addWidget(self.body_scroll, 1)

        column.addWidget(top, 1)
        return content

    def show_unavailable(self, name: str) -> None:
        """Itens fora da visão geral: apenas avisa, sem alterar nenhum estado."""
        self.toast.show_message(FUTURE_NOTICE.format(name=name))

    def closeEvent(self, event) -> None:
        """Nunca fecha no meio de uma gravação: o usuário espera ela terminar."""
        if self.model.busy:
            event.ignore()
            self.toast.show_message("Aguarde: há uma operação com o mouse em andamento.")
            return
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.toast.reposition()
