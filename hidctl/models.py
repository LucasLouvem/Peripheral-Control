"""Modelos independentes do protocolo USB."""

from dataclasses import dataclass, field
from enum import Enum


class DeviceKind(str, Enum):
    MOUSE = "mouse"
    KEYBOARD = "keyboard"


@dataclass
class RgbSettings:
    enabled: bool = True
    mode: str = "static"
    color: str = "#ffffff"
    brightness: int = 100
    speed: int = 50


@dataclass
class Macro:
    name: str
    actions: list[dict[str, object]] = field(default_factory=list)


@dataclass
class MouseProfile:
    name: str = "Padrão"
    dpi_stages: list[int] = field(default_factory=lambda: [800, 1600, 2400, 3200, 6400])
    active_dpi: int = 1600
    polling_rate: int = 1000
    rgb: RgbSettings = field(default_factory=RgbSettings)
    buttons: dict[str, str] = field(default_factory=dict)
    macros: list[Macro] = field(default_factory=list)


@dataclass
class DeviceInfo:
    path: str
    vendor_id: int
    product_id: int
    manufacturer: str | None
    product: str | None
    kind: DeviceKind | None = None
