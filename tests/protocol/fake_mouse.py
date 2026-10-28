"""Reexporta o simulador do pacote com o nome usado nos testes."""

from hidctl.devices.fc30_mouse.simulator import BASES, initial_memory  # noqa: F401
from hidctl.devices.fc30_mouse.simulator import MouseSimulator as FakeMouse

__all__ = ["BASES", "FakeMouse", "initial_memory"]
