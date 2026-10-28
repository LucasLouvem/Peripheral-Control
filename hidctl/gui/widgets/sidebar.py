"""Barra lateral: logo, dispositivo e navegação."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .. import assets, icons, theme
from .common import RowButton

# DPI e iluminação ficam na tela do dispositivo; macros terão a própria seção (ainda indisponível).
NAV_ITEMS = (("document", "Macros"),)
DEVICE = "Dispositivo"


class Sidebar(QFrame):
    """Barra lateral compacta: só ícones; o nome de cada opção aparece como dica ao passar o mouse.

    Itens: **Dispositivo** (a tela atual, com DPI e iluminação), **Macros** e **Configurações**.
    Macros e Configurações ainda não existem e emitem ``unavailable``.
    """

    unavailable = Signal(str)
    WIDTH = 54

    def __init__(self, assets_dir: Path | None = None) -> None:
        super().__init__()
        self.setObjectName("sidebar")
        self.setFixedWidth(self.WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 12, 6, 10)
        layout.setSpacing(0)

        logo = QLabel()
        logo.setPixmap(icons.pixmap("mouse", theme.RED, 22, stroke=1.9))
        logo.setFixedSize(22, 22)
        logo.setToolTip("Peripheral Control")
        layout.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(14)

        self.device_button = self._device_card(assets_dir)
        layout.addWidget(self.device_button)
        layout.addSpacing(8)
        layout.addWidget(self._separator())
        layout.addSpacing(8)

        self.nav_buttons: dict[str, RowButton] = {}
        for icon_name, text in NAV_ITEMS:
            button = RowButton("nav", icon_name, text)
            button.setFixedHeight(36)
            button.clicked.connect(lambda _=False, name=text: self._navigate(name))
            self.nav_buttons[text] = button
            layout.addWidget(button)
            layout.addSpacing(4)

        layout.addStretch(1)
        layout.addWidget(self._separator())
        layout.addSpacing(10)
        self.settings_button = RowButton("nav", "gear", "Configurações")
        self.settings_button.setFixedHeight(36)
        self.settings_button.clicked.connect(lambda: self.unavailable.emit("Configurações"))
        layout.addWidget(self.settings_button)

    @property
    def active_item(self) -> str:
        """A única tela existente é a do dispositivo."""
        return DEVICE

    def _navigate(self, name: str) -> None:
        self.unavailable.emit(name)

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setObjectName("sidebarSeparator")
        line.setFixedHeight(1)
        return line

    def _device_card(self, assets_dir: Path | None) -> QPushButton:
        button = QPushButton()
        button.setObjectName("device")
        button.setFixedHeight(54)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip("Dispositivo: Cobra M711 (kit S118)")
        button.setAccessibleName("Dispositivo: Cobra M711")
        row = QHBoxLayout(button)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        accent = QFrame()
        accent.setObjectName("accentBar")
        accent.setFixedWidth(4)
        row.addWidget(accent)
        thumb = QLabel()
        thumb.setFixedSize(32, 44)
        image = assets.load_image("king_cobra_2_base.png", assets_dir)
        if image is not None:
            scaled = QPixmap.fromImage(image).scaled(
                thumb.size() * 2,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            scaled.setDevicePixelRatio(2.0)
            thumb.setPixmap(scaled)
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addStretch(1)
        row.addWidget(thumb)
        row.addStretch(1)
        for child in (accent, thumb):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        return button
