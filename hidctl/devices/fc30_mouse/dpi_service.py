"""Serviço do mouse: carregar DPI e iluminação do perfil exibido e salvar o que foi alterado (sem Qt).

Fluxo de ``save`` (nada é gravado antes dele, e ``load`` só lê):

1. valida as entradas **antes** de abrir o aparelho;
2. numa única sessão, lê o perfil ativo e o bloco atual e procura conflitos com o estado
   carregado (se um nível *editado* mudou por fora, nada é gravado);
3. grava somente os níveis de DPI alterados (4 bytes cada, com backup antes) e, se houver, a
   cor da iluminação (trecho mínimo do registro, com backup), enviando um ``F1 02 02`` se houve DPI
   e um ``F1 02 04`` se houve iluminação;
4. relê na mesma sessão e só então devolve ``CONFIRMED`` (isso confirma os **dados**; o efeito
   visual da luz não é verificável por software).

O protocolo não oferece atomicidade: se algo falhar entre duas gravações, o resultado é
``PARTIAL`` ou ``UNCONFIRMED`` e o estado real é conferido por uma releitura de leitura apenas.
"""

import errno
import fcntl
import os
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ...core import discovery
from ...core.errors import (
    AmbiguousDevice,
    DescriptorMismatch,
    DeviceGone,
    HidctlError,
    NoDeviceFound,
    PermissionDenied,
    ProtocolError,
    RevisionMismatch,
    SessionError,
    TransportError,
    ValidationError,
)
from ...core.transport import HidrawTransport, LoggingTransport
from . import dpi, lighting, values
from .session import MouseSession
from .spec import SPEC

Connector = Callable[[], AbstractContextManager[MouseSession]]

LEVEL_COUNT = dpi.LEVELS


class OutcomeKind(Enum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CONFLICT = "conflict"
    NOT_WRITTEN = "not_written"
    PARTIAL = "partial"
    UNCONFIRMED = "unconfirmed"
    DEVICE_ERROR = "device_error"
    BUSY = "busy"


@dataclass(frozen=True)
class LevelView:
    index: int
    enabled: bool
    code: int
    flag: int
    y_code: int
    y_flag: int
    nominal: int | None  # rótulo nominal; None se o código não está na tabela
    evidence: values.Evidence | None
    estimate: int

    @property
    def symmetric(self) -> bool:
        return (self.y_code, self.y_flag) == (self.code, self.flag)

    @property
    def validated(self) -> bool:
        return self.evidence in values.WRITABLE

    @property
    def editable(self) -> bool:
        return self.enabled and self.symmetric

    @property
    def run(self) -> bytes:
        return bytes([self.code, self.flag, self.y_code, self.y_flag])


@dataclass(frozen=True)
class DpiSnapshot:
    profile: int  # índice 0-4 do perfil que está sendo exibido/editado
    active_profile: (
        int  # índice 0-4 do perfil ativo no mouse (pode ser outro, se o usuário só está olhando)
    )
    active_level: (
        int  # nível ativo do perfil exibido (byte 0 do bloco; ver docs/devices/cobra-m711.md)
    )
    levels: tuple[LevelView, ...]
    raw: bytes
    lighting: lighting.Lighting | None = None  # iluminação do mesmo perfil (None se não lida)


@dataclass(frozen=True)
class SaveOutcome:
    kind: OutcomeKind
    message: str
    snapshot: DpiSnapshot | None = None  # melhor conhecimento do estado real, se houve leitura
    written: tuple[int, ...] = ()  # níveis cujo novo valor foi visto na releitura
    code: str = ""  # código de erro de acesso (absent, permission, ...), quando houver
    light_written: bool = False  # a nova cor foi vista na releitura

    @property
    def ok(self) -> bool:
        return self.kind is OutcomeKind.CONFIRMED


class DpiError(HidctlError):
    """Erro de carga com um código estável e uma mensagem para o usuário."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class DpiBusy(HidctlError):
    """Outra operação (neste ou em outro processo) usa o aparelho."""


def describe_error(exc: BaseException) -> tuple[str, str]:
    """(código, mensagem para o usuário) de uma falha de acesso ao aparelho."""
    if isinstance(exc, PermissionDenied):
        return "permission", (
            "Sem permissão para acessar o mouse. Instale a regra udev do projeto "
            "(packaging/udev, veja docs/dpi-interface.md); o aplicativo não deve rodar como root."
        )
    if isinstance(exc, (NoDeviceFound, DeviceGone)):
        return (
            "absent",
            'Mouse não encontrado ou desconectado. Conecte o mouse e use "Recarregar do mouse".',
        )
    if isinstance(exc, RevisionMismatch):
        return "unsupported", f"Revisão do mouse não suportada: {exc}"
    if isinstance(exc, (DescriptorMismatch, AmbiguousDevice)):
        return (
            "unsupported",
            f"Não foi possível identificar a interface de configuração: {exc}",
        )
    if isinstance(exc, ProtocolError):
        return "protocol", f"Resposta inválida do mouse: {exc}"
    if isinstance(exc, SessionError):
        return "session", f"Operação recusada por segurança: {exc}"
    if isinstance(exc, TransportError):
        return "io", f"Erro de comunicação com o mouse: {exc}"
    return "error", str(exc)


def _view(index: int, level: dpi.Level) -> LevelView:
    entry = values.by_code(level.x_code, level.x_flag)
    symmetric = (level.y_code, level.y_flag) == (level.x_code, level.x_flag)
    known = entry if (entry and symmetric) else None
    return LevelView(
        index=index,
        enabled=bool(level.enabled),
        code=level.x_code,
        flag=level.x_flag,
        y_code=level.y_code,
        y_flag=level.y_flag,
        nominal=known.nominal if known else None,
        evidence=known.evidence if known else None,
        estimate=level.estimate(),
    )


def snapshot_from(
    block: dpi.DpiBlock, active_profile: int, light: lighting.Lighting | None = None
) -> DpiSnapshot:
    return DpiSnapshot(
        profile=block.profile,
        active_profile=active_profile,
        active_level=block.active_level,
        levels=tuple(_view(i, lv) for i, lv in enumerate(block.levels)),
        raw=block.raw,
        lighting=light,
    )


@contextmanager
def open_mouse(log: Callable[[str], None] | None = None):
    """Conector de produção: descobre o aparelho, abre o hidraw e abre a sessão."""
    found = discovery.find(SPEC)
    transport = HidrawTransport(found.node)
    try:
        wrapped = LoggingTransport(transport, log) if log else transport
        with MouseSession(wrapped) as session:
            yield session
    finally:
        transport.close()


def _expected_raw(current: bytes, plans: list[dpi.WritePlan]) -> bytes:
    data = bytearray(current)
    for plan in plans:
        start = plan.address - dpi.PROFILE_BASES[plan.profile]
        data[start : start + len(plan.new)] = plan.new
    return bytes(data)


def _level_bytes(raw: bytes, level: int) -> bytes:
    start = dpi.RECORD_OFFSET + dpi.RECORD_SIZE * level + 1
    return raw[start : start + dpi.WRITE_RUN]


def _sentence(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else text + "."


def _levels_text(levels) -> str:
    return ", ".join(str(i + 1) for i in sorted(levels))


@dataclass
class _Progress:
    phase: str = "connect"  # connect, read, write, apply, verify
    attempted: int = 0
    plans: tuple = ()
    light_plan: lighting.LightingPlan | None = None
    current: dpi.DpiBlock | None = None
    outcome: SaveOutcome | None = None


class DpiController:
    def __init__(
        self, connector: Connector, backup_dir: Path, lock_path: Path | None = None
    ) -> None:
        self._connector = connector
        self._backup_dir = Path(backup_dir)
        self._lock_path = Path(lock_path) if lock_path else None
        self._lock = threading.Lock()

    @contextmanager
    def _exclusive(self):
        if not self._lock.acquire(blocking=False):
            raise DpiBusy("Outra operação com o mouse está em andamento.")
        fd = None
        try:
            if self._lock_path is not None:
                try:
                    self._lock_path.parent.mkdir(parents=True, exist_ok=True)
                    fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR, 0o600)
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    if exc.errno in (errno.EACCES, errno.EAGAIN):
                        raise DpiBusy("Outro processo do hidctl está usando o mouse.") from exc
                    raise DpiError(
                        "lock", f"Não foi possível travar o acesso ao mouse: {exc}"
                    ) from exc
            yield
        finally:
            if fd is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)
            self._lock.release()

    # ------------------------------------------------------------------ leitura

    def load(self, profile: int | None = None) -> DpiSnapshot:
        """Lê os 5 níveis de ``profile`` (padrão: o perfil ativo). Somente leitura (``F5 00``, ``F2``, ``F5 01``).

        Olhar outro perfil **não** o ativa no mouse: o perfil ativo só é lido, nunca escrito.
        """
        with self._exclusive():
            try:
                with self._connector() as session:
                    active = session.read_active_profile()
                    shown = active if profile is None else profile
                    block = session.read_dpi_block(shown)
                    light = session.read_lighting(shown)
            except HidctlError as exc:
                raise DpiError(*describe_error(exc)) from exc
        return snapshot_from(block, active, light)

    # ------------------------------------------------------------------ gravação

    def save(
        self,
        loaded: DpiSnapshot,
        edits: dict[int, int],
        light: lighting.LightingEdit | None = None,
    ) -> SaveOutcome:
        rejection = self._validate(loaded, edits, light)
        if rejection is not None:
            return rejection
        changes = {i: v for i, v in edits.items() if v != loaded.levels[i].nominal}
        if light is not None and lighting.edit_matches(loaded.lighting, light):
            light = None
        try:
            with self._exclusive():
                return self._save_locked(loaded, changes, light)
        except DpiBusy as exc:
            return SaveOutcome(OutcomeKind.BUSY, f"{exc} Nada foi gravado.")
        except DpiError as exc:
            return SaveOutcome(
                OutcomeKind.DEVICE_ERROR,
                f"{exc.message} Nada foi gravado.",
                code=exc.code,
            )

    def _validate(
        self,
        loaded: DpiSnapshot,
        edits: dict[int, int],
        light: lighting.LightingEdit | None,
    ) -> SaveOutcome | None:
        def reject(text: str) -> SaveOutcome:
            return SaveOutcome(OutcomeKind.REJECTED, f"{text} Nada foi enviado ao mouse.")

        if not isinstance(edits, dict) or (not edits and light is None):
            return reject("Nenhuma alteração para salvar.")
        if light is not None:
            if loaded.lighting is None:
                return reject("A iluminação deste perfil não foi lida.")
            try:
                lighting.validate_edit(light)
            except ValidationError as exc:
                return reject(f"{exc}.")
        allowed = {v.nominal for v in values.writable_values()}
        for level, target in edits.items():
            if (
                isinstance(level, bool)
                or not isinstance(level, int)
                or not 0 <= level < LEVEL_COUNT
            ):
                return reject(f"Nível inválido: {level!r}.")
            if isinstance(target, bool) or not isinstance(target, int) or target not in allowed:
                return reject(f"Valor não liberado para o nível {level + 1}: {target!r}.")
            if not loaded.levels[level].editable:
                return reject(f"O nível {level + 1} está desabilitado ou tem X e Y diferentes.")
        dpi_unchanged = all(
            target == loaded.levels[level].nominal for level, target in edits.items()
        )
        light_unchanged = light is None or lighting.edit_matches(loaded.lighting, light)
        if dpi_unchanged and light_unchanged:
            return reject("Nenhuma alteração para salvar.")
        return None

    def _save_locked(
        self,
        loaded: DpiSnapshot,
        changes: dict[int, int],
        light: lighting.LightingEdit | None,
    ) -> SaveOutcome:
        progress = _Progress()
        try:
            with self._connector() as session:
                self._run(session, loaded, changes, light, progress)
        except HidctlError as exc:
            if progress.outcome is not None:  # falhou só ao fechar a sessão, depois do resultado
                note = f" Aviso: falha ao encerrar a sessão com o mouse ({exc})."
                return SaveOutcome(
                    progress.outcome.kind,
                    progress.outcome.message + note,
                    progress.outcome.snapshot,
                    progress.outcome.written,
                    progress.outcome.code,
                    progress.outcome.light_written,
                )
            return self._failure(loaded, progress, exc)
        return progress.outcome

    def _run(
        self,
        session: MouseSession,
        loaded: DpiSnapshot,
        changes: dict[int, int],
        light: lighting.LightingEdit | None,
        progress: _Progress,
    ) -> None:
        progress.phase = "read"
        profile = session.read_active_profile()
        if profile != loaded.active_profile:
            progress.outcome = SaveOutcome(
                OutcomeKind.CONFLICT,
                f"O perfil ativo no mouse mudou (agora {profile + 1}). Nada foi gravado; recarregue do mouse.",
            )
            return
        current = session.read_dpi_block(loaded.profile)
        current_light = session.read_lighting(loaded.profile)
        progress.current = current
        now = snapshot_from(current, profile, current_light)
        clashes = [i for i in changes if now.levels[i].run != loaded.levels[i].run]
        if clashes:
            progress.outcome = SaveOutcome(
                OutcomeKind.CONFLICT,
                f"O nível {_levels_text(clashes)} foi alterado por outro programa depois de carregado. "
                "Nada foi gravado; recarregue do mouse para ver os valores atuais.",
                now,
            )
            return
        if light is not None and current_light.record != loaded.lighting.record:
            progress.outcome = SaveOutcome(
                OutcomeKind.CONFLICT,
                "A iluminação foi alterada por outro programa depois de carregada. "
                "Nada foi gravado; recarregue do mouse para ver os valores atuais.",
                now,
            )
            return
        try:
            plans = [
                dpi.plan_level_change(current, i, changes[i], values.code_table())
                for i in sorted(changes)
            ]
            light_plan = (
                lighting.plan_lighting_change(current_light, light) if light is not None else None
            )
        except ValidationError as exc:
            progress.outcome = SaveOutcome(OutcomeKind.REJECTED, f"{exc}. Nada foi gravado.", now)
            return
        progress.plans = tuple(plans)
        progress.light_plan = light_plan
        progress.phase = "write"
        for plan in plans:
            session.apply_plan(plan, self._backup_dir)
            progress.attempted += 1
        if light_plan is not None:
            session.apply_lighting_plan(light_plan, self._backup_dir)
        progress.phase = "apply"
        if plans:
            session.commit_dpi()
        if light_plan is not None:
            session.commit_lighting()
        progress.phase = "verify"
        after = session.read_dpi_block(loaded.profile)
        after_light = session.read_lighting(loaded.profile)
        expected = _expected_raw(current.raw, plans)
        expected_window = _expected_window(current_light.raw, light_plan)
        shown = snapshot_from(after, profile, after_light)
        dpi_ok = after.raw[1:] == expected[1:]
        light_ok = after_light.raw == expected_window
        if not (dpi_ok and light_ok):
            differing = [
                i
                for i in range(LEVEL_COUNT)
                if _level_bytes(after.raw, i) != _level_bytes(expected, i)
            ]
            where = ([f"no nível {_levels_text(differing) or '?'}"] if not dpi_ok else []) + (
                ["na iluminação"] if not light_ok else []
            )
            progress.outcome = SaveOutcome(
                OutcomeKind.UNCONFIRMED,
                f"A releitura NÃO confirmou os valores gravados (divergência {' e '.join(where)}). "
                "O estado do mouse é incerto; a edição foi mantida.",
                shown,
            )
            return
        done = tuple(sorted(changes))
        parts = ([f"nível {_levels_text(done)}"] if done else []) + (
            ["iluminação"] if light_plan is not None else []
        )
        note = " A luz em si não é verificada pelo programa." if light_plan is not None else ""
        progress.outcome = SaveOutcome(
            OutcomeKind.CONFIRMED,
            f"Salvo e confirmado por releitura ({'; '.join(parts)}).{note}",
            shown,
            done,
            light_written=light_plan is not None,
        )

    def _failure(self, loaded: DpiSnapshot, progress: _Progress, exc: HidctlError) -> SaveOutcome:
        code, text = describe_error(exc)
        text = _sentence(text)
        if progress.phase in ("connect", "read"):
            kind = (
                OutcomeKind.DEVICE_ERROR
                if code in ("absent", "permission", "unsupported")
                else OutcomeKind.NOT_WRITTEN
            )
            return SaveOutcome(kind, f"{text} Nada foi gravado; a edição foi mantida.", code=code)
        actual = self._reread(loaded.profile, loaded.active_profile)
        planned = {plan.level: plan for plan in progress.plans}
        light_plan = progress.light_plan
        if actual is None:
            return SaveOutcome(
                OutcomeKind.UNCONFIRMED,
                f"{text} Não foi possível reler o mouse: o estado é INCERTO (parte das alterações pode ter sido gravada). "
                "A edição foi mantida; recarregue do mouse antes de tentar de novo.",
                code=code,
            )
        block, actual_light = actual
        snap = snapshot_from(block, loaded.active_profile, actual_light)
        written = tuple(
            sorted(i for i, p in planned.items() if block.raw[_offset(p) : _offset(p) + 4] == p.new)
        )
        light_done = light_plan is not None and _window_has(actual_light.raw, light_plan)
        if progress.phase == "verify":
            return SaveOutcome(
                OutcomeKind.UNCONFIRMED,
                f"{text} A gravação e o comando de aplicação foram enviados, mas a confirmação falhou; "
                f"na releitura posterior, níveis com o novo valor: {_levels_text(written) or 'nenhum'}"
                + (
                    "; iluminação gravada."
                    if light_done
                    else ("; iluminação não gravada." if light_plan else ".")
                )
                + " A edição foi mantida.",
                snap,
                written,
                light_written=light_done,
            )
        if not written and not light_done:
            return SaveOutcome(
                OutcomeKind.NOT_WRITTEN,
                f"{text} Na releitura, nada foi alterado. A edição foi mantida.",
                snap,
            )
        missing = sorted(set(planned) - set(written))
        saved = ([f"nível {_levels_text(written)}"] if written else []) + (
            ["iluminação"] if light_done else []
        )
        unsaved = ([f"nível {_levels_text(missing)}"] if missing else []) + (
            ["iluminação"] if light_plan and not light_done else []
        )
        return SaveOutcome(
            OutcomeKind.PARTIAL,
            f"{text} GRAVAÇÃO PARCIAL: gravados na memória do mouse: {'; '.join(saved)}"
            + (f"; não gravados: {'; '.join(unsaved)}" if unsaved else "")
            + ". O comando de aplicação (F1) pode não ter sido enviado. A edição foi mantida; recarregue do mouse.",
            snap,
            written,
            light_written=light_done,
        )

    def _reread(
        self, profile: int, active_profile: int
    ) -> tuple[dpi.DpiBlock, lighting.Lighting] | None:
        try:
            with self._connector() as session:
                if session.read_active_profile() != active_profile:
                    return None
                return session.read_dpi_block(profile), session.read_lighting(profile)
        except HidctlError:
            return None


def _expected_window(window: bytes, plan: lighting.LightingPlan | None) -> bytes:
    if plan is None:
        return window
    start = plan.address - lighting.window_address(plan.profile)
    return window[:start] + plan.new + window[start + len(plan.new) :]


def _window_has(window: bytes, plan: lighting.LightingPlan) -> bool:
    start = plan.address - lighting.window_address(plan.profile)
    return window[start : start + len(plan.new)] == plan.new


def _offset(plan: dpi.WritePlan) -> int:
    return plan.address - dpi.PROFILE_BASES[plan.profile]
