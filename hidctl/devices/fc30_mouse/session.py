"""Sessão de configuração do mouse: ``F5 00`` … ``F5 01`` sempre em par.

Guardas de segurança:
* a sessão fecha (``F5 01``) mesmo se uma operação falhar;
* depois de qualquer erro de transporte ou de protocolo a sessão fica *invalidada*:
  nenhuma outra leitura ou escrita é enviada, e nada é repetido automaticamente;
* a escrita só aceita um plano feito de um bloco lido **nesta** sessão, grava um
  backup antes e só toca o byte ``x_code`` de um nível de DPI conhecido.
"""

import json
from datetime import datetime
from pathlib import Path

from ...core.errors import (
    HidctlError,
    ProtocolError,
    SessionError,
    TransportError,
    ValidationError,
)
from ...core.transport import FeatureTransport
from . import dpi, frames, lighting

ACTIVE_PROFILE_ADDRESS = 0x002C  # [FONTE]


class MouseSession:
    def __init__(self, transport: FeatureTransport) -> None:
        self._transport = transport
        self._token = object()
        self._opened = False
        self._failed = False

    @property
    def failed(self) -> bool:
        return self._failed

    def __enter__(self) -> "MouseSession":
        self._transport.set_feature(frames.lock_frame(False))
        self._opened = True
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if not self._opened:
            return
        self._opened = False
        try:
            self._transport.set_feature(frames.lock_frame(True))
        except TransportError:
            if exc_type is None:
                raise

    def _guard(self) -> None:
        if not self._opened:
            raise SessionError("sessão não está aberta")
        if self._failed:
            raise SessionError("sessão invalidada por erro anterior; nada mais será enviado")

    def _send(self, frame: bytes) -> None:
        self._guard()
        try:
            self._transport.set_feature(frame)
        except HidctlError:
            self._failed = True
            raise

    def read_memory(self, address: int, count: int) -> bytes:
        frame = frames.read_frame(address, count)  # valida antes de enviar
        self._send(frame)
        try:
            raw = self._transport.get_feature(frames.REPORT_ID, frames.response_length(count))
            return frames.parse_read_response(raw, address, count)
        except HidctlError:
            self._failed = True
            raise

    def read_active_profile(self) -> int:
        value = self.read_memory(ACTIVE_PROFILE_ADDRESS, 1)[0]
        if value >= len(dpi.PROFILE_BASES):
            self._failed = True
            raise ProtocolError(f"perfil ativo fora de 0-4: {value}")
        return value

    def read_dpi_block(self, profile: int) -> dpi.DpiBlock:
        if (
            isinstance(profile, bool)
            or not isinstance(profile, int)
            or not 0 <= profile < len(dpi.PROFILE_BASES)
        ):
            raise ValidationError(f"perfil inválido: {profile!r}")
        raw = self.read_memory(dpi.PROFILE_BASES[profile], dpi.BLOCK_SIZE)
        try:
            return dpi.decode_block(profile, raw, self._token)
        except HidctlError:
            self._failed = True
            raise

    def write_backup(self, plan: dpi.WritePlan, directory: Path) -> Path:
        """Grava o bloco original em disco. Chamado antes de qualquer escrita."""
        directory = Path(directory)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = directory / f"fc30-dpi-p{plan.profile}-level{plan.level}-{stamp}.json"
        payload = {
            "profile": plan.profile,
            "block_address": f"{dpi.PROFILE_BASES[plan.profile]:#06x}",
            "block_hex": plan.block_raw.hex(" "),
            "planned": {
                "level": plan.level,
                "address": f"{plan.address:#06x}",
                "old": plan.old.hex(" "),
                "new": plan.new.hex(" "),
            },
        }
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2))
        except OSError as exc:
            raise SessionError(f"backup não gravado ({exc}); nada foi enviado") from exc
        return path

    def apply_plan(self, plan: dpi.WritePlan, backup_dir: Path) -> Path:
        """Backup e um único ``F3`` de 4 bytes (um nível). **Não** envia ``F1`` (use :meth:`commit_dpi`)."""
        self._guard()
        if plan.token is not self._token:
            raise SessionError("o plano não vem de um bloco lido nesta sessão")
        if (
            plan.address not in dpi.writable_addresses()
            or len(plan.new) != dpi.WRITE_RUN
            or len(plan.old) != dpi.WRITE_RUN
        ):
            raise SessionError(f"escrita fora da região permitida: {plan.address:#06x}")
        backup = self.write_backup(plan, backup_dir)
        self._send(frames.write_frame(plan.address, plan.new))
        return backup

    def commit_dpi(self) -> None:
        """``F1 02 02``: aplica a área de DPI [FONTE]."""
        self._send(frames.apply_frame(frames.AREA_DPI))

    # ------------------------------------------------------------------ iluminação

    def read_lighting(self, profile: int) -> lighting.Lighting:
        raw = self.read_memory(lighting.window_address(profile), lighting.WINDOW_SIZE)
        return lighting.decode_window(profile, raw, self._token)

    def write_lighting_backup(self, plan: lighting.LightingPlan, directory: Path) -> Path:
        """Grava a janela original em disco, antes de qualquer escrita de iluminação."""
        directory = Path(directory)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = directory / f"fc30-light-p{plan.profile}-{stamp}.json"
        payload = {
            "kind": "lighting",
            "profile": plan.profile,
            "window_address": f"{lighting.window_address(plan.profile):#06x}",
            "window_hex": plan.window_raw.hex(" "),
            "planned": {
                "address": f"{plan.address:#06x}",
                "old": plan.old.hex(" "),
                "new": plan.new.hex(" "),
            },
        }
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2))
        except OSError as exc:
            raise SessionError(f"backup não gravado ({exc}); nada foi enviado") from exc
        return path

    def apply_lighting_plan(self, plan: lighting.LightingPlan, backup_dir: Path) -> Path:
        """Backup e um único ``F3`` dentro do registro de 6 bytes de um perfil. **Não** envia ``F1``."""
        self._guard()
        if plan.token is not self._token:
            raise SessionError("o plano não vem de uma janela lida nesta sessão")
        end = plan.address + len(plan.new)
        if (
            len(plan.old) != len(plan.new)
            or not plan.new
            or not any(
                start <= plan.address and end <= stop for start, stop in lighting.writable_ranges()
            )
        ):
            raise SessionError(
                f"escrita de iluminação fora da região permitida: {plan.address:#06x}"
            )
        backup = self.write_lighting_backup(plan, backup_dir)
        self._send(frames.write_frame(plan.address, plan.new))
        return backup

    def commit_lighting(self) -> None:
        """``F1 02 04``: aplica a área de iluminação [FONTE]."""
        self._send(frames.apply_frame(frames.AREA_LIGHTING))
