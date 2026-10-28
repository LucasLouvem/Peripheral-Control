"""Tokens visuais (amostrados da referência) e folha de estilo única."""

from PySide6.QtGui import QFont

BG = "#111316"
SIDEBAR = "#14181a"
SIDEBAR_BORDER = "#1c2023"
CARD = "#171a1d"
CARD_BORDER = "#272b2f"
SURFACE = "#1e2224"
SURFACE_HOVER = "#262a2d"
OUTLINE = "#323639"
TEXT = "#ffffff"
TEXT_SOFT = "#c9cdd0"
TEXT_DIM = "#8a9094"
TEXT_MUTE = "#717679"
RED = "#fb3b3c"
RED_BRIGHT = "#fd4440"
RED_SELECTED_BG = "#3b1d1f"
RED_SELECTED_BORDER = "#d93538"
NAV_ACTIVE_BG = "#3d2022"
ORANGE = "#fe982b"
GREEN = "#23cb61"
MACRO_ITEM = "#1f2125"
MACRO_BORDER = "#292b2e"
BAR = "#171a1c"
SLIDER_TRACK = "#2c3033"

FONT_FAMILIES = ["Inter", "Segoe UI", "Noto Sans", "Liberation Sans", "DejaVu Sans"]


def app_font() -> QFont:
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPixelSize(11)
    return font


def stylesheet() -> str:
    return f"""
QWidget#root {{ background: {BG}; }}
QLabel {{ background: transparent; color: {TEXT}; }}
QToolTip {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {OUTLINE}; padding: 4px 6px; }}

QFrame#sidebar {{ background: {SIDEBAR}; border-right: 1px solid {SIDEBAR_BORDER}; }}
QFrame#sidebarSeparator {{ background: {SIDEBAR_BORDER}; border: none; }}
QLabel#sectionLabel {{ color: {TEXT_DIM}; font-size: 9px; font-weight: 700; }}
QLabel#appTitle {{ font-size: 13px; font-weight: 500; }}

QPushButton#nav, QPushButton#device {{ background: transparent; border: none; border-radius: 6px; text-align: left; }}
QPushButton#nav:hover {{ background: {SURFACE}; }}
QPushButton#nav[active="true"] {{ background: {NAV_ACTIVE_BG}; }}
QPushButton#device {{ background: #25282b; border-radius: 8px; }}
QPushButton#device:hover {{ background: #2b2f32; }}
QLabel#navText {{ font-size: 12px; color: {TEXT_SOFT}; }}
QPushButton#nav[active="true"] QLabel#navText {{ color: {TEXT}; }}
QLabel#deviceName {{ font-size: 12px; font-weight: 700; }}
QFrame#accentBar {{ background: {RED_BRIGHT}; border: none; }}

QLabel#title {{ font-size: 22px; font-weight: 700; }}
QLabel#subtitle {{ color: {TEXT_DIM}; font-size: 11px; padding-bottom: 6px; }}
QLabel#status {{ color: {TEXT_SOFT}; font-size: 10px; }}
QLabel#badge {{ color: {TEXT_DIM}; border: 1px solid {OUTLINE}; border-radius: 9px;
    padding: 1px 8px; font-size: 9px; font-weight: 700; }}
QLabel#readonlyField {{ background: {SURFACE}; border: 1px solid {OUTLINE}; border-radius: 6px;
    color: {TEXT_SOFT}; font-size: 12px; padding: 0 16px; min-height: 29px; }}
QLabel#levelValue {{ color: {TEXT}; font-size: 13px; }}
QLabel#levelValue[active="true"] {{ color: {GREEN}; font-weight: 700; }}
QLabel#levelValue[edited="true"] {{ color: {ORANGE}; font-weight: 700; }}
QLabel#levelCaption {{ color: {TEXT_DIM}; font-size: 9px; }}
QSlider#levelSlider::groove:vertical {{ background: {SLIDER_TRACK}; width: 5px; border-radius: 2px; }}
QSlider#levelSlider::sub-page:vertical {{ background: {SLIDER_TRACK}; width: 5px; border-radius: 2px; }}
QSlider#levelSlider::add-page:vertical {{ background: {RED}; width: 5px; border-radius: 2px; }}
QSlider#levelSlider::handle:vertical {{ background: #eeecee; height: 14px; width: 14px; margin: 0 -5px; border-radius: 7px; }}
QSlider#levelSlider[unvalidated="true"]::handle:vertical {{ background: {TEXT_MUTE}; }}
QSlider#levelSlider:disabled::handle:vertical {{ background: {TEXT_MUTE}; }}
QSlider#levelSlider:disabled::add-page:vertical {{ background: {SLIDER_TRACK}; }}
QLabel#fieldLabel {{ color: {TEXT_SOFT}; font-size: 12px; }}
QLabel#mouseName {{ font-size: 19px; font-weight: 700; }}
QLabel#mouseSubtitle {{ color: {TEXT_DIM}; font-size: 12px; }}

QFrame#card {{ background: {CARD}; border: 1px solid {CARD_BORDER}; border-radius: 8px; }}
QLabel#cardTitle {{ font-size: 13px; font-weight: 700; }}
QLabel#cardCaption {{ color: {TEXT_SOFT}; font-size: 11px; }}
QComboBox[edited="true"] {{ color: {ORANGE}; }}
QDialog#lightingDialog {{ background: {CARD}; }}
QPushButton#tab {{ background: {SURFACE}; border: 1px solid {OUTLINE}; border-radius: 6px; color: {TEXT_SOFT};
    font-size: 11px; min-height: 31px; padding: 0 12px; }}
QPushButton#tab:hover {{ background: {SURFACE_HOVER}; }}
QPushButton#tab:checked {{ background: {RED_SELECTED_BG}; border: 1px solid {RED_SELECTED_BORDER}; color: {TEXT}; }}
QLabel#dialogHeading {{ color: {TEXT}; font-size: 13px; font-weight: 700; }}
QLineEdit#hexEdit {{ background: {SURFACE}; border: 1px solid {OUTLINE}; border-radius: 6px; color: {TEXT};
    font-size: 12px; padding: 0 8px; min-height: 29px; }}
QSpinBox {{ background: {SURFACE}; border: 1px solid {OUTLINE}; border-radius: 6px; color: {TEXT};
    font-size: 12px; padding: 0 6px; min-height: 27px; }}
QLabel#dpiValue {{ color: {RED}; font-size: 22px; font-weight: 700; }}
QLabel#percent {{ color: {TEXT_SOFT}; font-size: 11px; }}

QPushButton#dpiOption {{ background: {SURFACE}; border: 1px solid {OUTLINE}; border-radius: 6px;
    color: {TEXT}; font-size: 12px; min-height: 31px; }}
QPushButton#dpiOption:hover {{ background: {SURFACE_HOVER}; }}
QPushButton#dpiOption:checked {{ background: {RED_SELECTED_BG}; border: 2px solid {RED_SELECTED_BORDER}; }}

QPushButton#outline {{ background: {SURFACE}; border: 1px solid {OUTLINE}; border-radius: 6px;
    color: {TEXT}; font-size: 10px; padding: 0 8px; min-height: 28px; }}
QPushButton#outline:hover {{ background: {SURFACE_HOVER}; }}
QPushButton#round {{ background: {SURFACE}; border: 1px solid {OUTLINE}; border-radius: 15px; }}
QPushButton#round:hover {{ background: {SURFACE_HOVER}; }}
QPushButton#more {{ background: transparent; border: none; border-radius: 6px; color: {TEXT_SOFT}; font-size: 10px; }}
QPushButton#more:hover {{ background: {SURFACE_HOVER}; }}

QComboBox {{ background: {SURFACE}; border: 1px solid {OUTLINE}; border-radius: 6px;
    color: {TEXT}; font-size: 12px; padding: 0 28px 0 10px; min-height: 29px; }}
QComboBox:hover {{ background: {SURFACE_HOVER}; }}
QComboBox::drop-down {{ border: none; width: 0px; }}
QComboBox QAbstractItemView {{ background: {SURFACE}; border: 1px solid {OUTLINE}; color: {TEXT};
    selection-background-color: {NAV_ACTIVE_BG}; selection-color: {TEXT}; outline: none; padding: 4px; }}

QFrame#macroItem {{ background: {MACRO_ITEM}; border: 1px solid {MACRO_BORDER}; border-radius: 8px; }}
QLabel#macroName {{ font-size: 10px; font-weight: 700; }}
QLabel#macroSteps {{ color: {TEXT_DIM}; font-size: 10px; }}

QLabel#profileName {{ color: {TEXT}; font-size: 14px; font-weight: 700; padding-right: 4px; }}
QLineEdit#profileEdit {{ background: {SURFACE}; border: 1px solid {OUTLINE}; border-radius: 5px; color: {TEXT}; padding: 2px 6px; font-size: 13px; }}
QPushButton#iconButton {{ background: transparent; border: none; border-radius: 5px; }}
QPushButton#iconButton:hover {{ background: {SURFACE_HOVER}; }}
QPushButton#iconButton:disabled {{ background: transparent; }}
QMenu {{ background: {SURFACE}; border: 1px solid {OUTLINE}; padding: 4px; font-size: 12px; color: {TEXT}; }}
QMenu::item {{ padding: 5px 18px 5px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {NAV_ACTIVE_BG}; }}
QMenu::item:disabled {{ color: {TEXT_MUTE}; }}
QMenu::separator {{ height: 1px; background: {OUTLINE}; margin: 4px 6px; }}
QLabel#message {{ color: {TEXT_SOFT}; font-size: 10px; }}
QLabel#message[kind="ok"] {{ color: {GREEN}; }}
QLabel#message[kind="warn"] {{ color: {ORANGE}; }}
QLabel#message[kind="error"] {{ color: #ff7a78; }}
QPushButton#apply {{ background: {RED}; border: none; border-radius: 6px; color: {TEXT};
    font-size: 11px; font-weight: 700; min-height: 35px; min-width: 140px; }}
QPushButton#apply:hover {{ background: {RED_BRIGHT}; }}
QPushButton#apply:disabled {{ color: {TEXT_MUTE}; background: #3a2527; }}

QLabel#toast {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {OUTLINE}; border-radius: 16px;
    padding: 8px 18px; font-size: 10px; }}

QScrollArea#body {{ background: transparent; border: none; }}
QScrollArea#body > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {OUTLINE}; border-radius: 4px; min-height: 21px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QSlider::groove:horizontal {{ background: {SLIDER_TRACK}; height: 5px; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {RED}; height: 5px; border-radius: 2px; }}
QSlider::add-page:horizontal {{ background: {SLIDER_TRACK}; height: 5px; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: #eeecee; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
"""
