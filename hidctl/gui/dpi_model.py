"""Estado da interface para o DPI e a iluminação reais: edição local e operações no aparelho.

Regras (docs/dpi-interface.md):

* ``set_value`` e ``set_light`` só mudam este estado local; nada é enviado ao mouse;
* ``discard`` volta a edição ao último estado conhecido do mouse, sem I/O;
* só ``save`` grava, e o sucesso só é declarado quando o serviço confirmou por releitura;
* ``loaded`` é sempre o melhor conhecimento do estado **real** do mouse (inclusive após falhas),
  e as edições pendentes são preservadas em qualquer falha.
"""

from PySide6.QtCore import QObject, Signal

from ..core.errors import ValidationError
from ..devices.fc30_mouse import lighting, values
from ..devices.fc30_mouse.dpi_service import (
    DpiBusy,
    DpiController,
    DpiError,
    DpiSnapshot,
    OutcomeKind,
    SaveOutcome,
)
from .profile_names import ProfileNames
from .recent_colors import RecentColors
from .runner import ImmediateRunner

LOADING, IDLE, SAVING = "loading", "idle", "saving"

# connection: unknown | connected | absent | permission | protocol | unsupported | error
KIND_INFO, KIND_OK, KIND_WARN, KIND_ERROR = "info", "ok", "warn", "error"


class DpiModel(QObject):
    changed = Signal()

    def __init__(
        self,
        controller: DpiController,
        runner=None,
        names: ProfileNames | None = None,
        parent: QObject | None = None,
        recent: RecentColors | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self.names = names or ProfileNames()
        self.recent = recent or RecentColors()
        self._view_profile: int | None = None  # None = o perfil ativo do mouse
        self._runner = runner or ImmediateRunner()
        self.loaded: DpiSnapshot | None = None
        self.edits: dict[int, int] = {}
        self.light_edit: lighting.LightingEdit | None = None  # cor pendente (efeito estático)
        self._live_active: int | None = None  # nível ativo informado pelos eventos do botão físico
        self.status = IDLE
        self.connection = "unknown"
        self.message = ""
        self.message_kind = KIND_INFO

    # ------------------------------------------------------------------ consultas

    @property
    def busy(self) -> bool:
        return self.status in (LOADING, SAVING)

    @property
    def pending(self) -> bool:
        return bool(self.edits) or self.light_edit is not None

    @property
    def pending_levels(self) -> tuple[int, ...]:
        return tuple(sorted(self.edits))

    @property
    def active_level(self) -> int | None:
        """Nível ativo no mouse: o último evento do botão físico ou, antes dele, o lido do aparelho.

        Só vale para o perfil ativo no mouse; ao olhar outro perfil não há nível "ativo" a mostrar.
        """
        if self.loaded is not None and self.loaded.profile != self.loaded.active_profile:
            return None
        if self._live_active is not None:
            return self._live_active
        return self.loaded.active_level if self.loaded else None

    @property
    def light_loaded(self) -> lighting.Lighting | None:
        return self.loaded.lighting if self.loaded else None

    @property
    def light_rgb(self) -> tuple[int, int, int] | None:
        """Cor mostrada: a pendente, senão a lida do mouse."""
        if self.light_edit is not None:
            return self.light_edit.rgb
        return self.light_loaded.rgb if self.light_loaded else None

    @property
    def light_hex(self) -> str | None:
        rgb = self.light_rgb
        return None if rgb is None else "#%02x%02x%02x" % rgb

    @property
    def light_effect(self) -> lighting.Effect | None:
        """Efeito mostrado: o pendente ou o lido (``OTHER`` = efeito que o programa não edita)."""
        if self.light_edit is not None:
            return self.light_edit.effect
        return self.light_loaded.effect if self.light_loaded else None

    @property
    def light_speed(self) -> int | None:
        if self.light_edit is not None:
            return self.light_edit.speed
        return self.light_loaded.speed if self.light_loaded else None

    @property
    def light_effect_name(self) -> str | None:
        if self.light_edit is not None:
            return lighting.EFFECT_NAMES[
                lighting.STATIC_CODES
                if self.light_edit.effect is lighting.Effect.STATIC
                else lighting.WAVE_CODES
            ]
        return lighting.effect_name(self.light_loaded) if self.light_loaded else None

    @property
    def light_brightness_percent(self) -> int:
        """Brilho do mouse (níveis 1-3 do aparelho) como porcentagem, só para o desenho."""
        light = self.light_loaded
        return round(100 * light.brightness / 3) if light and 1 <= light.brightness <= 3 else 100

    @property
    def profile(self) -> int | None:
        """Perfil exibido/editado (0-4)."""
        return self.loaded.profile if self.loaded else None

    @property
    def active_profile(self) -> int | None:
        """Perfil ativo no mouse (0-4)."""
        return self.loaded.active_profile if self.loaded else None

    @property
    def visible_profiles(self) -> int:
        """Quantos perfis aparecem no menu: o escolhido pelo usuário (padrão 1), mas nunca esconde o ativo nem o exibido."""
        needed = [self.names.count]
        if self.loaded is not None:
            needed += [self.loaded.active_profile + 1, self.loaded.profile + 1]
        return min(5, max(needed))

    @property
    def can_add_profile(self) -> bool:
        return self.visible_profiles < 5 and not self.busy

    def add_profile(self) -> bool:
        """Mostra mais um dos 5 perfis do mouse e passa a exibi-lo. Só leitura: não grava nada no mouse."""
        if not self.can_add_profile:
            return False
        new = self.visible_profiles
        persisted = self.names.set_count(new + 1)
        started = self.select_profile(new)
        if not persisted:
            self._say(
                "Perfil adicionado, mas não foi possível gravar a preferência em disco; vale só até fechar o programa.",
                KIND_WARN,
            )
            self.changed.emit()
        return started

    def profile_name(self, profile: int) -> str:
        return self.names.name(profile)

    def rename_profile(self, profile: int, text: str) -> bool:
        """Renomeia só localmente (o mouse não guarda nomes). Nunca acessa o aparelho."""
        persisted = self.names.set_name(profile, text)
        if not persisted:
            self._say(
                "Nome alterado, mas não foi possível gravá-lo em disco; vale só até fechar o programa.",
                KIND_WARN,
            )
        self.changed.emit()
        return persisted

    @property
    def can_save(self) -> bool:
        return self.pending and not self.busy and self.loaded is not None

    @property
    def can_discard(self) -> bool:
        return self.pending and not self.busy

    def value_of(self, level: int) -> int | None:
        """Valor mostrado do nível: o editado, senão o do mouse (``None`` se não validado)."""
        if level in self.edits:
            return self.edits[level]
        return self.loaded.levels[level].nominal if self.loaded else None

    def saved_value_of(self, level: int) -> int | None:
        return self.loaded.levels[level].nominal if self.loaded else None

    # ------------------------------------------------------------------ edição local

    def set_live_active(self, level: int) -> None:
        """Atualiza o nível ativo a partir de um evento do mouse. Não envia nada e não mexe nas edições."""
        if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level < 5:
            return
        if level != self._live_active:
            self._live_active = level
            self.changed.emit()

    def set_value(self, level: int, dpi: int) -> None:
        """Edita localmente. Só aceita valores liberados; voltar ao valor do mouse remove a edição."""
        if self.loaded is None:
            raise ValueError("estado do mouse ainda não carregado")
        if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level < 5:
            raise ValueError(f"nível inválido: {level!r}")
        if not self.loaded.levels[level].editable:
            raise ValueError(f"o nível {level + 1} não é editável")
        allowed = {v.nominal for v in values.writable_values()}
        if isinstance(dpi, bool) or not isinstance(dpi, int) or dpi not in allowed:
            raise ValueError(f"valor não liberado: {dpi!r}")
        if dpi == self.loaded.levels[level].nominal:
            self.edits.pop(level, None)
        else:
            self.edits[level] = dpi
        self._say("", KIND_INFO)  # a mensagem anterior (ex.: "Estado lido") já não descreve a tela
        self.changed.emit()

    def _light_base(self) -> lighting.LightingEdit:
        """Ponto de partida de uma edição: a pendente, ou o que o mouse tem (efeito desconhecido vira estático)."""
        if self.light_edit is not None:
            return self.light_edit
        light = self.light_loaded
        if light.effect is lighting.Effect.WAVE:
            return lighting.LightingEdit(
                light.rgb,
                lighting.Effect.WAVE,
                light.speed if light.speed in lighting.SPEEDS else 4,
            )
        return lighting.LightingEdit(light.rgb)

    def _set_light_edit(self, edit: lighting.LightingEdit) -> None:
        try:
            lighting.validate_edit(edit)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        self.light_edit = None if lighting.edit_matches(self.light_loaded, edit) else edit
        self._say("", KIND_INFO)
        self.changed.emit()

    def _require_light(self) -> None:
        if self.light_loaded is None:
            raise ValueError("iluminação do mouse ainda não carregada")

    def set_light(self, rgb: tuple[int, int, int]) -> None:
        """Edita a cor localmente (passa para o efeito estático). Voltar ao que o mouse já tem remove a edição."""
        self._require_light()
        self._set_light_edit(
            lighting.LightingEdit(tuple(rgb) if isinstance(rgb, (tuple, list)) else rgb)
        )

    def set_light_effect(self, effect: lighting.Effect) -> None:
        self._require_light()
        base = self._light_base()
        if effect is lighting.Effect.WAVE:
            speed = (
                base.speed
                if base.speed is not None
                else (self.light_loaded.speed if self.light_loaded.speed in lighting.SPEEDS else 4)
            )
            self._set_light_edit(lighting.LightingEdit(base.rgb, effect, speed))
        else:
            self._set_light_edit(lighting.LightingEdit(base.rgb, effect))

    def set_light_speed(self, speed: int) -> None:
        """Velocidade da onda (1 = rápida … 8 = lenta). Só existe com o efeito onda."""
        self._require_light()
        base = self._light_base()
        if base.effect is not lighting.Effect.WAVE:
            raise ValueError("a velocidade só existe na onda")
        self._set_light_edit(lighting.LightingEdit(base.rgb, lighting.Effect.WAVE, speed))

    def discard(self) -> None:
        """Restaura a edição para o último estado conhecido. Não grava nada."""
        if self.busy or not self.pending:
            return
        self.edits.clear()
        self.light_edit = None
        self._say("Edição descartada; nada foi enviado ao mouse.", KIND_INFO)
        self.changed.emit()

    # ------------------------------------------------------------------ operações no aparelho

    def reload(self) -> bool:
        """Lê o estado do mouse (somente leitura) do perfil exibido. Recusa se já houver uma operação."""
        if self.busy:
            return False
        view = self._view_profile
        self.status = LOADING
        self._say("Lendo o mouse…", KIND_INFO)
        self.changed.emit()
        self._runner.submit(lambda: self._controller.load(view), self._loaded)
        return True

    def select_profile(self, profile: int) -> bool:
        """Passa a exibir/editar outro perfil. **Não** o ativa no mouse (só lê). Descarta a edição pendente."""
        if isinstance(profile, bool) or not isinstance(profile, int) or not 0 <= profile < 5:
            raise ValueError(f"perfil inválido: {profile!r}")
        if self.busy:
            return False
        if profile == self.profile and self.loaded is not None:
            return True
        had_edits = self.pending
        self.edits.clear()
        self.light_edit = None
        self._view_profile = profile
        started = self.reload()
        if had_edits:
            self._say(
                "Edição não salva do perfil anterior descartada; nada foi enviado ao mouse.",
                KIND_WARN,
            )
            self.changed.emit()
        return started

    def save(self) -> bool:
        """Envia **somente** os níveis alterados. Recusa se não houver edição ou se estiver ocupado."""
        if not self.can_save:
            return False
        loaded, edits, light = self.loaded, dict(self.edits), self.light_edit
        self.status = SAVING
        self._say("Salvando e conferindo por releitura…", KIND_INFO)
        self.changed.emit()
        self._runner.submit(lambda: self._controller.save(loaded, edits, light), self._saved)
        return True

    # ------------------------------------------------------------------ resultados (thread da UI)

    def _loaded(self, result: object, error: BaseException | None) -> None:
        self.status = IDLE
        if error is None:
            self.loaded = result
            self._view_profile = result.profile
            self._live_active = result.active_level  # a leitura é a verdade mais recente
            self.connection = "connected"
            self.edits = {
                i: v
                for i, v in self.edits.items()
                if v != result.levels[i].nominal and result.levels[i].editable
            }
            self._prune_light()
            self._say("Estado do mouse lido.", KIND_INFO)
        elif isinstance(error, DpiBusy):
            self._say(str(error), KIND_WARN)
        elif isinstance(error, DpiError):
            self.connection = (
                error.code
                if error.code in ("absent", "permission", "protocol", "unsupported")
                else "error"
            )
            self._say(error.message, KIND_ERROR)
        else:
            self.connection = "error"
            self._say(f"Erro inesperado ao ler o mouse: {error}", KIND_ERROR)
        self.changed.emit()

    def _saved(self, result: object, error: BaseException | None) -> None:
        self.status = IDLE
        if error is not None or not isinstance(result, SaveOutcome):
            kind = type(error).__name__ if error else "resultado inválido"
            self._say(
                f"Erro inesperado ao salvar ({kind}). O estado do mouse é incerto; recarregue. A edição foi mantida.",
                KIND_ERROR,
            )
            self.changed.emit()
            return
        outcome = result
        if outcome.snapshot is not None:
            self.loaded = outcome.snapshot  # melhor conhecimento do estado real
            self._live_active = outcome.snapshot.active_level
            self.connection = "connected"
        if outcome.kind is OutcomeKind.CONFIRMED:
            self.edits.clear()
            self.light_edit = None
            self._say(outcome.message, KIND_OK)
        else:
            if outcome.code in ("absent", "permission", "protocol", "unsupported"):
                self.connection = outcome.code
            if (
                self.loaded is not None
            ):  # edições que já coincidem com o estado real deixam de ser pendentes
                self.edits = {
                    i: v for i, v in self.edits.items() if v != self.loaded.levels[i].nominal
                }
                self._prune_light()
            level = (
                KIND_WARN
                if outcome.kind in (OutcomeKind.REJECTED, OutcomeKind.BUSY, OutcomeKind.CONFLICT)
                else KIND_ERROR
            )
            self._say(outcome.message, level)
        self.changed.emit()

    def _prune_light(self) -> None:
        """A cor pendente que já coincide com o estado real deixa de ser pendência."""
        if self.light_edit is not None and (
            self.light_loaded is None or lighting.edit_matches(self.light_loaded, self.light_edit)
        ):
            self.light_edit = None

    def _say(self, text: str, kind: str) -> None:
        self.message, self.message_kind = text, kind

    def wait(self) -> None:
        self._runner.wait()
