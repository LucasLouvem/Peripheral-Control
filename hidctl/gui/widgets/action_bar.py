"""Barra do topo da coluna direita: perfil (nome, renomear, trocar) e o botão Salvar.

Salvar é a única operação que grava no mouse; fechar sem salvar descarta a edição. Resultados
importantes (confirmado, falha, parcial, conflito, mouse ausente) aparecem numa linha abaixo;
mensagens apenas informativas ficam ocultas.
"""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import icons, theme
from ..dpi_model import KIND_INFO, SAVING, DpiModel
from ..profile_names import MAX_LENGTH, PROFILE_COUNT
from .common import repolish

ICON = 15
SAVE_TOOLTIP = "Grava no mouse só os níveis alterados e confirma por releitura. Fechar sem salvar descarta a edição."
RENAME_TOOLTIP = "Renomear (o nome fica só neste computador; o mouse não guarda nomes)"
ADD_TOOLTIP = "Adicionar perfil"
MAX_TOOLTIP = "Máximo de 5 perfis"


class _NameEdit(QLineEdit):
    cancelled = Signal()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.cancelled.emit()


def _icon_button(icon: str, tooltip: str) -> QPushButton:
    button = QPushButton()
    button.setObjectName("iconButton")
    button.setIcon(icons.icon(icon, theme.TEXT_SOFT, ICON))
    button.setIconSize(QSize(ICON, ICON))
    button.setFixedSize(26, 26)
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class ActionBar(QWidget):
    def __init__(self, model: DpiModel) -> None:
        super().__init__()
        self._model = model
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(4)

        self.name_label = QLabel()
        self.name_label.setObjectName("profileName")
        self.name_edit = _NameEdit()
        self.name_edit.setObjectName("profileEdit")
        self.name_edit.setMaxLength(MAX_LENGTH)
        self.name_edit.setFixedWidth(130)
        self.name_edit.hide()
        self.name_edit.returnPressed.connect(self._commit_rename)
        self.name_edit.cancelled.connect(self._cancel_rename)
        self.rename_button = _icon_button("pencil", RENAME_TOOLTIP)
        self.rename_button.clicked.connect(self._start_rename)
        self.menu_button = _icon_button("chevron-down", "Trocar de perfil")
        self.menu = QMenu(self)
        self.menu.setToolTipsVisible(True)
        self.menu_button.clicked.connect(
            lambda: self.menu.popup(
                self.menu_button.mapToGlobal(self.menu_button.rect().bottomLeft())
            )
        )
        self.profile_actions = []
        self.add_action = None

        row.addWidget(self.name_label)
        row.addWidget(self.name_edit)
        row.addWidget(self.rename_button)
        row.addWidget(self.menu_button)
        row.addStretch(1)

        self.save_button = QPushButton("Salvar")
        self.save_button.setObjectName("apply")
        self.save_button.setToolTip(SAVE_TOOLTIP)
        self.save_button.setFixedWidth(110)
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.clicked.connect(model.save)
        row.addWidget(self.save_button, 0, Qt.AlignmentFlag.AlignVCenter)
        outer.addLayout(row)

        self.message_label = QLabel()
        self.message_label.setObjectName("message")
        self.message_label.setWordWrap(True)
        self.message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        outer.addWidget(self.message_label)

        model.changed.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------------ perfil

    def _shown_profile(self) -> int:
        profile = self._model.profile
        return profile if profile is not None else 0

    def _rebuild_menu(self) -> None:
        model = self._model
        self.menu.clear()
        self.profile_actions = []
        for profile in range(model.visible_profiles):
            action = self.menu.addAction(model.profile_name(profile))
            action.setCheckable(True)
            action.setChecked(model.profile == profile)
            action.setEnabled(not model.busy)
            action.triggered.connect(lambda _=False, value=profile: model.select_profile(value))
            self.profile_actions.append(action)
        self.menu.addSeparator()
        self.add_action = self.menu.addAction("+")
        self.add_action.setEnabled(model.can_add_profile)
        self.add_action.setToolTip(
            ADD_TOOLTIP if model.visible_profiles < PROFILE_COUNT else MAX_TOOLTIP
        )
        self.add_action.triggered.connect(lambda _=False: model.add_profile())

    def _start_rename(self) -> None:
        if self._model.loaded is None:
            return
        self.name_edit.setText(self._model.profile_name(self._shown_profile()))
        self.name_label.hide()
        self.name_edit.show()
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def _finish_rename_ui(self) -> None:
        self.name_edit.hide()
        self.name_label.show()

    def _commit_rename(self) -> None:
        text = self.name_edit.text()
        self.name_edit.blockSignals(True)  # evita o "cancelar" por perda de foco ao esconder
        try:
            self._model.rename_profile(self._shown_profile(), text)
        except ValueError as exc:
            self.name_edit.blockSignals(False)
            self.name_edit.setToolTip(str(exc))
            return
        self.name_edit.blockSignals(False)
        self._finish_rename_ui()

    def _cancel_rename(self) -> None:
        if self.name_edit.isVisible():
            self._finish_rename_ui()

    # ------------------------------------------------------------------ estado

    def refresh(self) -> None:
        model = self._model
        self.name_label.setText(model.profile_name(self._shown_profile()))
        self.rename_button.setEnabled(model.loaded is not None)
        self.menu_button.setEnabled(model.loaded is not None)
        self._rebuild_menu()
        text = model.message if model.message_kind != KIND_INFO else ""
        self.message_label.setText(text)
        self.message_label.setToolTip(text)
        self.message_label.setVisible(bool(text))
        self.message_label.setProperty("kind", model.message_kind)
        repolish(self.message_label)
        self.save_button.setEnabled(model.can_save)
        self.save_button.setText("Salvando…" if model.status == SAVING else "Salvar")
