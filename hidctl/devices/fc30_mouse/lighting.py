"""Registro de iluminação do mouse: decodificação e plano de alteração.

Layout por perfil p (0-4), janela de 8 bytes em ``LIGHT_BASE + 8·p`` [TESTE: leitura de 2026-10-28,
mesmo layout em duas fontes externas independentes]:

    +0 +1 +2   R G B (8 bits por canal)
    +3         modo1
    +4         velocidade
    +5         modo2
    +6         brilho (não editado aqui)
    +7         desconhecido (lido 0x80 nos 5 perfis; preservado, nunca escrito)

Efeitos (modo1, modo2) [TESTE]: estático ``01 02`` (editável) e onda ``02 00`` (multicolor: ignora a
cor; velocidade 1 = rápida … 8 = lenta). Qualquer outro par lido (respiração ``01 04``…) é
``Effect.OTHER``: exibido e preservado até o usuário escolher estático ou onda.
"""

from dataclasses import dataclass
from enum import Enum

from ...core.errors import ProtocolError, ValidationError

LIGHT_BASE = 0x449
LIGHT_STRIDE = 8
WINDOW_SIZE = 8
RECORD_SIZE = 6  # R G B modo1 velocidade modo2: o máximo que um plano grava
PROFILES = 5

STATIC_CODES = (0x01, 0x02)
WAVE_CODES = (0x02, 0x00)
SPEEDS = tuple(range(1, 9))  # [TESTE] 1 e 8 observados (1 = rápida, 8 = lenta); 2-7 só pela fonte


class Effect(Enum):
    STATIC = "static"
    WAVE = "wave"
    OTHER = "other"


@dataclass(frozen=True)
class Lighting:
    profile: int
    address: int
    raw: bytes  # janela inteira de 8 bytes
    rgb: tuple[int, int, int]
    effect: Effect
    speed: int
    brightness: int
    token: object | None = None

    @property
    def record(self) -> bytes:
        return self.raw[:RECORD_SIZE]


@dataclass(frozen=True)
class LightingEdit:
    """Edição pendente. Estático usa ``rgb`` (velocidade preservada); onda usa ``speed`` 1-8 e também guarda ``rgb``
    no registro (a onda do aparelho é multicolor e não o exibe, docs/devices/cobra-m711.md)."""

    rgb: tuple[int, int, int]
    effect: Effect = Effect.STATIC
    speed: int | None = None


@dataclass(frozen=True)
class LightingPlan:
    profile: int
    address: int  # onde começa o trecho a gravar
    old: bytes
    new: bytes
    window_raw: bytes
    token: object | None


# Nome mostrado para o par (modo1, modo2). [TESTE] estático, onda e respiração (vista no aparelho);
# os demais vêm só de fontes externas (mouse_m908) e não foram exercitados aqui.
EFFECT_NAMES = {
    (0x00, 0x00): "Desligada",
    (0x01, 0x01): "Respiração arco-íris",
    (0x01, 0x02): "Estático",
    (0x01, 0x04): "Respiração",
    (0x01, 0x08): "Arco-íris",
    (0x01, 0x10): "Piscando",
    (0x02, 0x00): "Onda",
    (0x03, 0x00): "Reativo (botão)",
    (0x04, 0x00): "Aleatório",
    (0x06, 0x00): "Alternado",
    (0x07, 0x00): "Reativo",
}


def effect_name(light: Lighting) -> str:
    return EFFECT_NAMES.get((light.raw[3], light.raw[5]), "Efeito desconhecido")


def window_address(profile: int) -> int:
    if isinstance(profile, bool) or not isinstance(profile, int) or not 0 <= profile < PROFILES:
        raise ValidationError(f"perfil inválido: {profile!r}")
    return LIGHT_BASE + LIGHT_STRIDE * profile


def writable_ranges() -> frozenset[tuple[int, int]]:
    """Janelas (início, fim exclusivo) onde a sessão aceita gravar: só o registro de 6 bytes de cada perfil."""
    return frozenset((window_address(p), window_address(p) + RECORD_SIZE) for p in range(PROFILES))


def _effect_of(mode1: int, mode2: int) -> Effect:
    if (mode1, mode2) == STATIC_CODES:
        return Effect.STATIC
    if (mode1, mode2) == WAVE_CODES:
        return Effect.WAVE
    return Effect.OTHER


def decode_window(profile: int, raw: bytes, token: object | None = None) -> Lighting:
    address = window_address(profile)
    if len(raw) != WINDOW_SIZE:
        raise ProtocolError(f"janela de iluminação com {len(raw)} bytes, esperado {WINDOW_SIZE}")
    return Lighting(
        profile=profile,
        address=address,
        raw=bytes(raw),
        rgb=(raw[0], raw[1], raw[2]),
        effect=_effect_of(raw[3], raw[5]),
        speed=raw[4],
        brightness=raw[6],
        token=token,
    )


def validate_edit(edit: LightingEdit) -> None:
    if not isinstance(edit, LightingEdit):
        raise ValidationError("edição de iluminação inválida")
    if not isinstance(edit.rgb, tuple) or len(edit.rgb) != 3:
        raise ValidationError(f"cor inválida: {edit.rgb!r}")
    for channel in edit.rgb:
        if isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel <= 255:
            raise ValidationError(f"canal RGB fora de 0-255: {channel!r}")
    if edit.effect is Effect.STATIC:
        if edit.speed is not None:
            raise ValidationError("a velocidade só existe na onda")
    elif edit.effect is Effect.WAVE:
        if (
            isinstance(edit.speed, bool)
            or not isinstance(edit.speed, int)
            or edit.speed not in SPEEDS
        ):
            raise ValidationError(f"velocidade fora de {SPEEDS[0]}-{SPEEDS[-1]}: {edit.speed!r}")
    else:
        raise ValidationError(f"efeito não suportado: {edit.effect!r}")


def target_record(current: Lighting, edit: LightingEdit) -> bytes:
    """Os 6 bytes do registro depois da edição: estático (velocidade preservada) ou onda (a cor escolhida fica
    guardada no registro, mas o aparelho a ignora ao exibir a onda)."""
    validate_edit(edit)
    if edit.effect is Effect.STATIC:
        return bytes([*edit.rgb, STATIC_CODES[0], current.speed, STATIC_CODES[1]])
    return bytes([*edit.rgb, WAVE_CODES[0], edit.speed, WAVE_CODES[1]])


def edit_matches(current: Lighting, edit: LightingEdit) -> bool:
    """O registro lido já representa a edição? (o estático ignora a velocidade)"""
    if current.effect is not edit.effect or current.rgb != edit.rgb:
        return False
    return edit.effect is Effect.STATIC or current.speed == edit.speed


def plan_lighting_change(current: Lighting, edit: LightingEdit) -> LightingPlan | None:
    """Menor trecho contíguo a gravar, ou ``None`` se o registro já está como a edição pede."""
    target = target_record(current, edit)
    old = current.record
    changed = [i for i in range(RECORD_SIZE) if old[i] != target[i]]
    if not changed:
        return None
    first, last = changed[0], changed[-1]
    return LightingPlan(
        profile=current.profile,
        address=current.address + first,
        old=old[first : last + 1],
        new=target[first : last + 1],
        window_raw=current.raw,
        token=current.token,
    )
