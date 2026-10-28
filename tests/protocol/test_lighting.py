"""Iluminação: layout lido do aparelho, plano mínimo de gravação e o fluxo completo de salvar."""

import json
import unittest

from hidctl.core.errors import SessionError, ValidationError
from hidctl.devices.fc30_mouse import lighting
from hidctl.devices.fc30_mouse.dpi_service import OutcomeKind
from hidctl.devices.fc30_mouse.lighting import Effect, LightingEdit

from .test_dpi_service import (
    APPLY_DPI,
    APPLY_LIGHT,
    LOCK0,
    LOCK1,
    READ_ACTIVE,
    READ_BLOCK,
    READ_LIGHT,
    ServiceCase,
)

# Janelas reais lidas do aparelho em 2026-10-28
BREATHING = bytes.fromhex(
    "ff00000102040380"
)  # perfil 0 de fábrica do teste: vermelho, respiração, vel 2, brilho 3
WAVE = bytes.fromhex("ff00000204000280")  # perfis 1-4: onda, vel 4, brilho 2


def light_f3(address: int, data: str) -> bytes:
    raw = bytes.fromhex(data)
    return (bytes([2, 0xF3, address & 0xFF, address >> 8, len(raw), 0, 0, 0]) + raw).ljust(
        16, b"\x00"
    )


class DecodeAndPlanTest(unittest.TestCase):
    def test_decodes_the_real_windows(self):
        light = lighting.decode_window(0, BREATHING)
        self.assertEqual(
            (light.rgb, light.effect, light.speed, light.brightness, light.address),
            ((255, 0, 0), Effect.OTHER, 2, 3, 0x449),
        )
        wave = lighting.decode_window(1, WAVE)
        self.assertEqual(
            (wave.effect, wave.speed, wave.brightness, wave.address),
            (Effect.WAVE, 4, 2, 0x451),
        )
        static = lighting.decode_window(
            0, bytes.fromhex("80 40 c0 01 08 02 03 80".replace(" ", ""))
        )
        self.assertEqual(
            (static.rgb, static.effect, static.speed),
            ((0x80, 0x40, 0xC0), Effect.STATIC, 8),
        )

    def test_plan_from_wave_rewrites_the_whole_record_keeping_speed_and_brightness(
        self,
    ):
        plan = lighting.plan_lighting_change(
            lighting.decode_window(1, WAVE), LightingEdit((0, 128, 255))
        )
        self.assertEqual(
            (plan.address, plan.old.hex(), plan.new.hex()),
            (0x451, "ff0000020400", "0080ff010402"),
        )

    def test_plan_for_a_single_channel_writes_a_single_byte(self):
        static = lighting.decode_window(0, bytes.fromhex("ff00000104020380"))
        plan = lighting.plan_lighting_change(static, LightingEdit((255, 1, 0)))
        self.assertEqual((plan.address, plan.old.hex(), plan.new.hex()), (0x44A, "00", "01"))

    def test_same_static_color_needs_no_plan(self):
        static = lighting.decode_window(0, bytes.fromhex("ff00000104020380"))
        self.assertIsNone(lighting.plan_lighting_change(static, LightingEdit((255, 0, 0))))
        self.assertTrue(lighting.edit_matches(static, LightingEdit((255, 0, 0))))
        self.assertFalse(
            lighting.edit_matches(lighting.decode_window(0, WAVE), LightingEdit((255, 0, 0)))
        )  # onda → estático é mudança

    def test_wave_plan_stores_the_chosen_color_with_mode_and_speed(self):
        static = lighting.decode_window(0, bytes.fromhex("8040c00108020380"))
        plan = lighting.plan_lighting_change(static, LightingEdit((1, 2, 3), Effect.WAVE, 1))
        self.assertEqual(
            (plan.address, plan.old.hex(), plan.new.hex()),
            (0x449, "8040c0010802", "010203020100"),
        )

    def test_wave_from_static_with_the_same_color_writes_only_mode_speed_and_mode2(
        self,
    ):
        static = lighting.decode_window(0, bytes.fromhex("ff00000104020380"))
        plan = lighting.plan_lighting_change(static, LightingEdit((255, 0, 0), Effect.WAVE, 3))
        self.assertEqual(
            (plan.address, plan.old.hex(), plan.new.hex()), (0x44C, "010402", "020300")
        )

    def test_wave_speed_change_writes_one_byte(self):
        wave = lighting.decode_window(1, WAVE)
        plan = lighting.plan_lighting_change(wave, LightingEdit((255, 0, 0), Effect.WAVE, 8))
        self.assertEqual((plan.address, plan.old.hex(), plan.new.hex()), (0x455, "04", "08"))
        self.assertIsNone(
            lighting.plan_lighting_change(wave, LightingEdit((255, 0, 0), Effect.WAVE, 4))
        )
        other_color = lighting.plan_lighting_change(wave, LightingEdit((9, 9, 9), Effect.WAVE, 4))
        self.assertEqual((other_color.address, other_color.new.hex()), (0x451, "090909"))

    def test_invalid_wave_edits_are_rejected(self):
        wave = lighting.decode_window(1, WAVE)
        for edit in (
            LightingEdit((1, 2, 3), Effect.WAVE, 0),
            LightingEdit((1, 2, 3), Effect.WAVE, 9),
            LightingEdit((1, 2, 3), Effect.WAVE, True),
            LightingEdit((1, 2, 3), Effect.WAVE, None),
            LightingEdit((1, 2, 3), Effect.WAVE, "4"),
            LightingEdit((1, 2, 3), Effect.STATIC, 4),
            LightingEdit((1, 2, 3), Effect.OTHER, None),
        ):
            with self.subTest(edit), self.assertRaises(ValidationError):
                lighting.plan_lighting_change(wave, edit)

    def test_invalid_edits_are_rejected(self):
        wave = lighting.decode_window(1, WAVE)
        for bad in [
            (256, 0, 0),
            (-1, 0, 0),
            (True, 0, 0),
            ("1", 0, 0),
            (1.0, 0, 0),
            (1, 2),
            [1, 2, 3],
            (1, 2, 3, 4),
        ]:
            with self.subTest(bad), self.assertRaises(ValidationError):
                lighting.plan_lighting_change(wave, LightingEdit(bad))
        with self.assertRaises(ValidationError):
            lighting.plan_lighting_change(wave, (1, 2, 3))

    def test_window_address_rejects_profiles_outside_0_4(self):
        self.assertEqual(
            [lighting.window_address(p) for p in range(5)],
            [0x449, 0x451, 0x459, 0x461, 0x469],
        )
        for bad in (5, -1, True, "0"):
            with self.subTest(bad), self.assertRaises(ValidationError):
                lighting.window_address(bad)


class SaveLightingTest(ServiceCase):
    def test_load_includes_the_lighting_of_the_shown_profile(self):
        snap = self.controller.load(2)
        self.assertEqual((snap.lighting.profile, snap.lighting.raw), (2, WAVE))

    def test_light_only_save_exact_frames_and_preservation(self):
        snap = self.snapshot()
        before = bytes(self.fake.memory)
        self.fake.frames.clear()
        outcome = self.controller.save(snap, {}, LightingEdit((0, 128, 255)))
        self.assertEqual(outcome.kind, OutcomeKind.CONFIRMED, outcome.message)
        self.assertEqual(
            self.fake.frames,
            [
                LOCK0,
                READ_ACTIVE,
                READ_BLOCK,
                READ_LIGHT,
                light_f3(0x449, "0080ff010202"),
                APPLY_LIGHT,
                READ_BLOCK,
                READ_LIGHT,
                LOCK1,
            ],
        )
        self.assertEqual(
            self.fake.light_window(0), bytes.fromhex("0080ff0102020380")
        )  # vel 2, brilho 3 e byte 7 preservados
        changed = {i for i in range(len(before)) if before[i] != self.fake.memory[i]}
        self.assertEqual(
            changed, {0x449, 0x44A, 0x44B, 0x44E}
        )  # nada fora do registro: DPI e demais perfis intactos
        self.assertTrue(outcome.light_written)
        self.assertEqual(outcome.snapshot.lighting.rgb, (0, 128, 255))
        self.assertEqual(outcome.snapshot.lighting.effect, Effect.STATIC)
        self.assertIn("(iluminação)", outcome.message)
        self.assertIn("não é verificada", outcome.message)

    def test_wave_save_writes_mode_and_speed_then_applies(self):
        snap = self.snapshot()
        self.fake.frames.clear()
        outcome = self.controller.save(snap, {}, LightingEdit((255, 0, 0), Effect.WAVE, 1))
        self.assertEqual(outcome.kind, OutcomeKind.CONFIRMED, outcome.message)
        self.assertEqual(self.fake.writes, [(0x44C, bytes.fromhex("020100"))])
        self.assertEqual(self.fake.light_window(0).hex(), "ff00000201000380")
        self.assertEqual(self.fake.f1_frames, [APPLY_LIGHT])
        self.assertEqual(outcome.snapshot.lighting.effect, Effect.WAVE)

    def test_dpi_and_light_in_one_save_send_both_applies(self):
        snap = self.snapshot()
        self.fake.frames.clear()
        outcome = self.controller.save(snap, {0: 1000}, LightingEdit((1, 2, 3)))
        self.assertEqual(outcome.kind, OutcomeKind.CONFIRMED, outcome.message)
        self.assertEqual(
            self.fake.writes,
            [
                (0x45, bytes.fromhex("16 00 16 00")),
                (0x449, bytes.fromhex("010203010202")),
            ],
        )
        self.assertEqual(self.fake.f1_frames, [APPLY_DPI, APPLY_LIGHT])
        self.assertEqual((outcome.written, outcome.light_written), ((0,), True))
        self.assertIn("nível 1; iluminação", outcome.message)

    def test_dpi_only_save_never_touches_lighting(self):
        snap = self.snapshot()
        self.fake.frames.clear()
        self.controller.save(snap, {0: 1000})
        self.assertEqual(self.fake.f1_frames, [APPLY_DPI])
        self.assertEqual([w[0] for w in self.fake.writes], [0x45])
        self.assertEqual(self.fake.light_window(0), BREATHING)

    def test_saving_another_profile_writes_only_its_own_window(self):
        snap = self.controller.load(2)
        outcome = self.controller.save(snap, {}, LightingEdit((9, 9, 9)))
        self.assertEqual(outcome.kind, OutcomeKind.CONFIRMED, outcome.message)
        self.assertEqual(self.fake.writes, [(0x459, bytes.fromhex("090909010402"))])
        self.assertEqual(self.fake.light_window(0), BREATHING)
        self.assertEqual(self.fake.light_window(1), WAVE)

    def test_backup_of_the_original_window_is_written_before_the_f3(self):
        self.controller.save(self.snapshot(), {}, LightingEdit((0, 128, 255)))
        files = [f for f in self.backups() if f.name.startswith("fc30-light-p0-")]
        self.assertEqual(len(files), 1)
        data = json.loads(files[0].read_text())
        self.assertEqual(
            (data["window_hex"], data["planned"]["old"], data["planned"]["new"]),
            ("ff 00 00 01 02 04 03 80", "ff 00 00 01 02 04", "00 80 ff 01 02 02"),
        )

    def test_invalid_or_unchanged_light_sends_nothing(self):
        self.fake.memory[0x449 : 0x449 + 8] = bytes.fromhex("00ff000102020380")
        snap = self.snapshot()
        cases = {
            "igual ao atual": LightingEdit((0, 255, 0)),
            "canal 256": LightingEdit((256, 0, 0)),
            "bool": LightingEdit((True, 0, 0)),
            "tipo errado": (1, 2, 3),
        }
        for label, edit in cases.items():
            with self.subTest(label):
                self.fake.frames.clear()
                outcome = self.controller.save(snap, {}, edit)
                self.assertEqual(outcome.kind, OutcomeKind.REJECTED)
                self.assertEqual(self.fake.frames, [])
        self.assertEqual(self.fake.light_window(0), bytes.fromhex("00ff000102020380"))

    def test_external_change_of_the_light_is_a_conflict_and_nothing_is_written(self):
        snap = self.snapshot()
        self.fake.memory[0x449] = 0x10  # outro programa mudou o vermelho
        self.fake.frames.clear()
        outcome = self.controller.save(snap, {0: 1000}, LightingEdit((0, 128, 255)))
        self.assertEqual(outcome.kind, OutcomeKind.CONFLICT)
        self.assertEqual(
            (self.fake.f3_frames, self.fake.f1_frames), ([], [])
        )  # nem o DPI foi gravado
        self.assertEqual(outcome.snapshot.lighting.rgb, (0x10, 0, 0))

    def test_failure_of_the_light_write_after_the_dpi_write_is_partial(self):
        snap = self.snapshot()
        self.fake.fail_write_number = 2  # o F3 da luz
        outcome = self.controller.save(snap, {0: 1000}, LightingEdit((0, 128, 255)))
        self.assertEqual(outcome.kind, OutcomeKind.PARTIAL, outcome.message)
        self.assertEqual((outcome.written, outcome.light_written), ((0,), False))
        self.assertIn("gravados na memória do mouse: nível 1", outcome.message)
        self.assertIn("não gravados: iluminação", outcome.message)
        self.assertEqual(self.fake.f1_frames, [])  # sem aplicar
        self.assertEqual(self.fake.light_window(0), BREATHING)

    def test_failure_of_the_only_light_write_is_not_written(self):
        snap = self.snapshot()
        self.fake.fail_write_number = 1
        outcome = self.controller.save(snap, {}, LightingEdit((0, 128, 255)))
        self.assertEqual(outcome.kind, OutcomeKind.NOT_WRITTEN)
        self.assertEqual(self.fake.f1_frames, [])

    def test_divergent_light_readback_is_unconfirmed(self):
        snap = self.snapshot()
        self.fake.corrupt_after_apply = {0x449: 0x11}
        outcome = self.controller.save(snap, {}, LightingEdit((0, 128, 255)))
        self.assertEqual(outcome.kind, OutcomeKind.UNCONFIRMED)
        self.assertIn("na iluminação", outcome.message)
        self.assertNotIn("Salvo e confirmado", outcome.message)

    def test_disconnect_before_the_light_apply_reports_what_could_not_be_confirmed(
        self,
    ):
        snap = self.snapshot()
        self.fake.frames.clear()
        self.fake.fail_after_frames = 5  # lock, 3 leituras e o F3: cai no F1
        outcome = self.controller.save(snap, {}, LightingEdit((0, 128, 255)))
        self.assertEqual(outcome.kind, OutcomeKind.UNCONFIRMED)
        self.assertIn("INCERTO", outcome.message)


class SessionGuardTest(ServiceCase):
    def plan_and_session(self, make):
        with self.fake.connect() as session:
            light = session.read_lighting(0)
            self.fake.frames.clear()
            plan = make(light)
            with self.assertRaises(SessionError):
                session.apply_lighting_plan(plan, self.tmp / "backups")
        self.assertEqual(self.fake.f3_frames, [])
        self.assertEqual(self.backups(), [])

    def test_plan_for_the_brightness_byte_is_refused(self):
        self.plan_and_session(
            lambda level: lighting.LightingPlan(0, 0x44F, b"\x03", b"\x01", level.raw, level.token)
        )

    def test_plan_that_crosses_the_record_end_is_refused(self):
        self.plan_and_session(
            lambda level: lighting.LightingPlan(
                0, 0x44E, b"\x04\x03", b"\x02\x01", level.raw, level.token
            )
        )

    def test_plan_from_another_session_is_refused(self):
        self.plan_and_session(
            lambda level: lighting.LightingPlan(0, 0x449, b"\xff", b"\x00", level.raw, object())
        )


if __name__ == "__main__":
    unittest.main()
