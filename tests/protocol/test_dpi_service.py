"""Fluxo completo de carregar/salvar com o mouse simulado: bytes exatos e preservação do que não muda."""

import tempfile
import threading
import unittest
from pathlib import Path

from hidctl.devices.fc30_mouse.dpi_service import (
    DpiBusy,
    DpiController,
    DpiError,
    OutcomeKind,
    open_mouse,
)
from hidctl.devices.fc30_mouse.values import Evidence

from .fake_mouse import FakeMouse

LOCK0 = bytes.fromhex("02f5000000000000" + "00" * 8)
LOCK1 = bytes.fromhex("02f5010000000000" + "00" * 8)
READ_ACTIVE = bytes.fromhex("02f22c0001000000" + "00" * 8)
READ_BLOCK = bytes.fromhex("02f2420020000000" + "00" * 8)
APPLY_DPI = bytes.fromhex("02f1020200000000" + "00" * 8)
APPLY_LIGHT = bytes.fromhex("02f1020400000000" + "00" * 8)
READ_LIGHT = bytes.fromhex("02f2490408000000" + "00" * 8)  # 8 bytes em 0x0449 (perfil 0)


def f3(address: int, data: str) -> bytes:
    body = bytes([2, 0xF3, address & 0xFF, address >> 8, 4, 0, 0, 0]) + bytes.fromhex(data)
    return body.ljust(16, b"\x00")


class ServiceCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.fake = FakeMouse()
        self.controller = DpiController(
            self.fake.connect, self.tmp / "backups", self.tmp / "device.lock"
        )

    def snapshot(self):
        return self.controller.load()

    def backups(self):
        folder = self.tmp / "backups"
        return sorted(folder.iterdir()) if folder.exists() else []


class LoadTest(ServiceCase):
    def test_load_only_reads_with_the_exact_frames(self):
        self.snapshot()
        self.assertEqual(self.fake.frames, [LOCK0, READ_ACTIVE, READ_BLOCK, READ_LIGHT, LOCK1])
        self.assertEqual((self.fake.f3_frames, self.fake.f1_frames), ([], []))
        self.assertEqual(self.fake.writes, [])

    def test_snapshot_content(self):
        snap = self.snapshot()
        self.assertEqual((snap.profile, snap.active_level), (0, 0))
        self.assertEqual([level.nominal for level in snap.levels], [800, 1200, 2400, 3600, 5000])
        self.assertEqual([level.code for level in snap.levels], [0x12, 0x1B, 0x37, 0x53, 0x73])
        self.assertEqual([level.evidence for level in snap.levels][0], Evidence.TESTED_PERCEIVED)
        self.assertEqual(snap.levels[1].evidence, Evidence.WRITTEN_READBACK)
        self.assertEqual(snap.raw, self.fake.block(0))
        self.assertTrue(all(level.enabled and level.symmetric for level in snap.levels))

    def test_loads_the_active_profile_not_always_zero(self):
        self.fake.memory[0x2C] = 2
        snap = self.snapshot()
        self.assertEqual(snap.profile, 2)
        self.assertEqual([level.nominal for level in snap.levels], [500, 1000, 2000, 3000, 5000])
        self.assertEqual(snap.active_level, 2)

    def test_loading_another_profile_is_read_only_and_keeps_the_active_profile_apart(
        self,
    ):
        self.fake.frames.clear()
        snap = self.controller.load(3)
        self.assertEqual((snap.profile, snap.active_profile), (3, 0))
        self.assertEqual([level.nominal for level in snap.levels], [500, 1000, 2000, 3000, 5000])
        self.assertEqual(self.fake.frames[0], LOCK0)
        self.assertEqual(
            self.fake.frames[2], bytes.fromhex("02f2620220000000" + "00" * 8)
        )  # lê 32 bytes em 0x0262
        self.assertEqual((self.fake.f3_frames, self.fake.f1_frames, self.fake.writes), ([], [], []))
        self.assertEqual(self.fake.memory[0x2C], 0)
        self.assertEqual(snap.raw, self.fake.block(3))

    def test_invalid_profile_numbers_do_not_reach_the_mouse_blocks(self):
        for bad in (-1, 5, True, "1"):
            with self.subTest(bad=bad), self.assertRaises(DpiError):
                self.controller.load(bad)
        self.assertEqual(self.fake.writes, [])

    def test_unknown_code_is_flagged_not_validated(self):
        self.fake.set_level_code(0, 2, 0x31)
        level = self.snapshot().levels[2]
        self.assertEqual((level.nominal, level.evidence, level.validated), (None, None, False))
        self.assertEqual(level.code, 0x31)

    def test_error_mapping(self):
        cases = {"absent": "absent", "permission_denied": "permission"}
        for attribute, code in cases.items():
            fake = FakeMouse()
            setattr(fake, attribute, True)
            controller = DpiController(fake.connect, self.tmp / "b")
            with self.subTest(attribute), self.assertRaises(DpiError) as raised:
                controller.load()
            self.assertEqual(raised.exception.code, code)
            self.assertEqual(fake.frames, [])

    def test_invalid_response_is_a_protocol_error(self):
        self.fake.bad_header_on_read = 2
        with self.assertRaises(DpiError) as raised:
            self.snapshot()
        self.assertEqual(raised.exception.code, "protocol")
        self.assertEqual(self.fake.frames[-1], LOCK1)  # a sessão ainda foi fechada
        self.assertEqual(self.fake.writes, [])


class RejectedBeforeAnyAccessTest(ServiceCase):
    def test_invalid_edits_never_open_the_device(self):
        snap = self.snapshot()
        before = (list(self.fake.frames), self.fake.sessions)
        bad = [
            {},
            {5: 800},
            {-1: 800},
            {True: 800},
            {0: 12000},
            {0: 10000},
            {0: 1600},
            {0: 6400},
            {0: 0},
            {0: True},
            {0: "800"},
            {0: 800.0},
            {0: None},
            {0: 800},
            {4: 5000},  # os dois últimos: sem mudança real
        ]
        for edits in bad:
            with self.subTest(edits=edits):
                outcome = self.controller.save(snap, edits)
                self.assertEqual(outcome.kind, OutcomeKind.REJECTED)
                self.assertIn("Nada foi enviado", outcome.message)
        self.assertEqual((self.fake.frames, self.fake.sessions), before)

    def test_disabled_and_asymmetric_levels_are_rejected(self):
        self.fake.memory[0x42 + 2 + 6 * 2] = 0  # nível 3 desabilitado
        self.fake.memory[0x42 + 2 + 6 * 3 + 3] = 0x16  # nível 4: y != x
        snap = self.snapshot()
        before = len(self.fake.frames)
        self.assertEqual(self.controller.save(snap, {2: 1000}).kind, OutcomeKind.REJECTED)
        self.assertEqual(self.controller.save(snap, {3: 1000}).kind, OutcomeKind.REJECTED)
        self.assertEqual(len(self.fake.frames), before)


class SuccessfulSaveTest(ServiceCase):
    def test_single_level_exact_frames_and_preservation(self):
        snap = self.snapshot()
        original = {p: self.fake.block(p) for p in range(5)}
        self.fake.frames.clear()
        outcome = self.controller.save(snap, {0: 1000})
        self.assertEqual(outcome.kind, OutcomeKind.CONFIRMED, outcome.message)
        self.assertEqual(
            self.fake.frames,
            [
                LOCK0,
                READ_ACTIVE,
                READ_BLOCK,
                READ_LIGHT,
                f3(0x45, "16 00 16 00"),
                APPLY_DPI,
                READ_BLOCK,
                READ_LIGHT,
                LOCK1,
            ],
        )
        after = self.fake.block(0)
        self.assertEqual(
            {i for i in range(32) if after[i] != original[0][i]}, {3, 5}
        )  # só X e Y do nível 1
        self.assertEqual((after[3], after[5]), (0x16, 0x16))
        for profile in range(1, 5):
            self.assertEqual(self.fake.block(profile), original[profile])  # outros perfis intactos
        self.assertEqual(outcome.written, (0,))
        self.assertEqual(outcome.snapshot.levels[0].nominal, 1000)
        self.assertEqual(outcome.message, "Salvo e confirmado por releitura (nível 1).")

    def test_multiple_levels_write_only_the_changed_ones_with_one_apply(self):
        snap = self.snapshot()
        self.fake.frames.clear()
        # nível 5 pedido com o valor que ele já tem: não é alteração e não pode ser gravado
        outcome = self.controller.save(snap, {0: 1000, 3: 800, 4: 5000})
        self.assertEqual(outcome.kind, OutcomeKind.CONFIRMED, outcome.message)
        self.assertEqual(
            self.fake.writes,
            [
                (0x45, bytes.fromhex("16 00 16 00")),
                (0x57, bytes.fromhex("12 00 12 00")),
            ],
        )
        self.assertEqual(self.fake.f1_frames, [APPLY_DPI])
        self.assertEqual(
            [level.nominal for level in outcome.snapshot.levels], [1000, 1200, 2400, 800, 5000]
        )
        self.assertEqual(outcome.written, (0, 3))

    def test_backup_per_level_is_written_with_distinct_names(self):
        self.controller.save(self.snapshot(), {0: 1000, 3: 800})
        files = self.backups()
        self.assertEqual(len(files), 2)
        self.assertEqual(len({f.name for f in files}), 2)
        text = {f.name.split("-level")[1][0]: f.read_text() for f in files}
        self.assertIn('"old": "12 00 12 00"', text["0"])
        self.assertIn('"new": "16 00 16 00"', text["0"])
        self.assertIn('"old": "53 00 53 00"', text["3"])
        self.assertIn('"new": "12 00 12 00"', text["3"])

    def test_active_level_changed_by_the_button_is_not_a_conflict_and_is_preserved(
        self,
    ):
        snap = self.snapshot()
        self.fake.memory[0x42] = 3  # o botão físico passou para o nível 4
        outcome = self.controller.save(snap, {0: 1000})
        self.assertEqual(outcome.kind, OutcomeKind.CONFIRMED, outcome.message)
        self.assertEqual(self.fake.block(0)[0], 3)
        self.assertEqual(outcome.snapshot.active_level, 3)

    def test_external_change_in_an_unedited_level_is_preserved_not_overwritten(self):
        snap = self.snapshot()
        self.fake.set_level_code(0, 2, 0x0B)  # outro programa mudou o nível 3 para 500
        outcome = self.controller.save(snap, {0: 1000})
        self.assertEqual(outcome.kind, OutcomeKind.CONFIRMED, outcome.message)
        self.assertEqual(self.fake.block(0)[2 + 12 + 1], 0x0B)
        self.assertEqual(outcome.snapshot.levels[2].nominal, 500)

    def test_a_confirmed_snapshot_can_be_edited_again(self):
        first = self.controller.save(self.snapshot(), {0: 1000})
        second = self.controller.save(first.snapshot, {0: 5000})
        self.assertEqual(second.kind, OutcomeKind.CONFIRMED, second.message)
        self.assertEqual(self.fake.block(0)[3], 0x73)


class ConflictTest(ServiceCase):
    def test_edited_level_changed_externally_blocks_every_write(self):
        snap = self.snapshot()
        self.fake.set_level_code(0, 0, 0x16)  # o nível 1 passou a 1000 por fora
        self.fake.frames.clear()
        outcome = self.controller.save(snap, {0: 5000, 3: 800})
        self.assertEqual(outcome.kind, OutcomeKind.CONFLICT)
        self.assertIn("nível 1", outcome.message)
        self.assertEqual((self.fake.f3_frames, self.fake.f1_frames, self.fake.writes), ([], [], []))
        self.assertEqual(self.fake.frames[-1], LOCK1)
        self.assertEqual(outcome.snapshot.levels[0].nominal, 1000)  # mostra o valor atual do mouse

    def test_conflict_in_any_edited_level_prevents_writing_the_others(self):
        snap = self.snapshot()
        self.fake.set_level_code(0, 3, 0x45)
        outcome = self.controller.save(snap, {0: 1000, 3: 800})
        self.assertEqual(outcome.kind, OutcomeKind.CONFLICT)
        self.assertEqual(self.fake.block(0)[3], 0x12)  # o nível 1 também não foi gravado

    def test_active_profile_changed_blocks_the_write(self):
        snap = self.snapshot()
        self.fake.memory[0x2C] = 1
        outcome = self.controller.save(snap, {0: 1000})
        self.assertEqual(outcome.kind, OutcomeKind.CONFLICT)
        self.assertIn("perfil ativo", outcome.message)
        self.assertEqual(self.fake.writes, [])


class FailureTest(ServiceCase):
    def edits3(self):
        return {0: 1000, 3: 800, 4: 1000}

    def test_failure_on_the_second_of_three_writes_is_partial_and_not_retried(self):
        snap = self.snapshot()
        self.fake.fail_write_number = 2
        self.fake.frames.clear()
        outcome = self.controller.save(snap, self.edits3())
        self.assertEqual(outcome.kind, OutcomeKind.PARTIAL)
        self.assertEqual(outcome.written, (0,))
        self.assertIn("PARCIAL", outcome.message)
        self.assertIn("nível 1", outcome.message)
        self.assertEqual(
            len(self.fake.f3_frames), 2
        )  # o terceiro F3 nunca foi enviado e nada foi repetido
        self.assertEqual(self.fake.f1_frames, [])  # sem F1 depois de falha
        after = self.fake.block(0)
        self.assertEqual((after[3], after[2 + 18 + 1], after[2 + 24 + 1]), (0x16, 0x53, 0x73))
        self.assertEqual(
            outcome.snapshot.levels[0].nominal, 1000
        )  # estado real conferido por releitura

    def test_failure_that_still_wrote_the_frame_is_reported_from_the_reread_not_assumed(
        self,
    ):
        snap = self.snapshot()
        self.fake.fail_write_number = 2
        self.fake.fail_write_applies_first = True  # o quadro chegou, mas o erro foi reportado
        outcome = self.controller.save(snap, self.edits3())
        self.assertEqual(outcome.kind, OutcomeKind.PARTIAL)
        self.assertEqual(outcome.written, (0, 3))

    def test_failure_on_the_first_write_reports_nothing_written(self):
        snap = self.snapshot()
        self.fake.fail_write_number = 1
        before = self.fake.block(0)
        outcome = self.controller.save(snap, {0: 1000})
        self.assertEqual(outcome.kind, OutcomeKind.NOT_WRITTEN)
        self.assertEqual(self.fake.block(0), before)
        self.assertIn("edição foi mantida", outcome.message)

    def test_failure_to_apply_after_writing_is_partial(self):
        snap = self.snapshot()
        self.fake.fail_apply = True
        outcome = self.controller.save(snap, {0: 1000, 3: 800})
        self.assertEqual(outcome.kind, OutcomeKind.PARTIAL)
        self.assertEqual(outcome.written, (0, 3))
        self.assertFalse(outcome.ok)

    def test_divergent_readback_is_never_reported_as_success(self):
        snap = self.snapshot()
        self.fake.corrupt_after_apply = {
            0x45: 0x12,
            0x47: 0x12,
        }  # o mouse "desfaz" o nível 1 depois do F1
        outcome = self.controller.save(snap, {0: 1000})
        self.assertEqual(outcome.kind, OutcomeKind.UNCONFIRMED)
        self.assertFalse(outcome.ok)
        self.assertIn("NÃO confirmou", outcome.message)
        self.assertIn("nível 1", outcome.message)
        self.assertEqual(
            outcome.snapshot.levels[0].nominal, 800
        )  # mostra o que o mouse realmente tem

    def test_partially_divergent_readback_is_also_unconfirmed(self):
        snap = self.snapshot()
        self.fake.corrupt_after_apply = {0x45: 0x12}  # só o X é desfeito: nível assimétrico
        outcome = self.controller.save(snap, {0: 1000})
        self.assertEqual(outcome.kind, OutcomeKind.UNCONFIRMED)
        self.assertIsNone(outcome.snapshot.levels[0].nominal)

    def test_disconnect_after_the_first_write_is_uncertain(self):
        snap = self.snapshot()
        self.fake.frames.clear()
        self.fake.fail_after_frames = 6  # lock, 3 leituras, 1 F3, 2º F3 -> desconecta no F1
        outcome = self.controller.save(snap, {0: 1000, 3: 800})
        self.assertEqual(outcome.kind, OutcomeKind.UNCONFIRMED)
        self.assertIn("INCERTO", outcome.message)
        self.assertEqual(self.fake.f1_frames, [])
        self.assertIsNone(outcome.snapshot)

    def test_device_absent_or_without_permission_before_anything(self):
        snap = self.snapshot()
        self.fake.frames.clear()
        self.fake.absent = True
        outcome = self.controller.save(snap, {0: 1000})
        self.assertEqual(outcome.kind, OutcomeKind.DEVICE_ERROR)
        self.assertIn("desconectado", outcome.message)
        self.fake.absent = False
        self.fake.permission_denied = True
        outcome = self.controller.save(snap, {0: 1000})
        self.assertEqual(outcome.kind, OutcomeKind.DEVICE_ERROR)
        self.assertIn("permissão", outcome.message)
        self.assertEqual(self.fake.frames, [])

    def test_invalid_response_before_writing_writes_nothing(self):
        snap = self.snapshot()
        self.fake.bad_header_on_read = self.fake.reads + 2  # a leitura do bloco
        outcome = self.controller.save(snap, {0: 1000})
        self.assertEqual(outcome.kind, OutcomeKind.NOT_WRITTEN)
        self.assertIn("Resposta inválida", outcome.message)
        self.assertEqual(self.fake.writes, [])

    def test_backup_failure_prevents_the_write(self):
        snap = self.snapshot()
        blocker = self.tmp / "arquivo"
        blocker.write_text("x")
        controller = DpiController(self.fake.connect, blocker / "sub", None)
        outcome = controller.save(snap, {0: 1000})
        self.assertEqual(outcome.kind, OutcomeKind.NOT_WRITTEN)
        self.assertEqual(self.fake.f3_frames, [])
        self.assertEqual(self.fake.block(0)[3], 0x12)


class ConcurrencyTest(ServiceCase):
    def test_second_operation_is_refused_while_one_runs(self):
        snap = self.snapshot()
        started, release = threading.Event(), threading.Event()
        original = self.fake.on_read

        def slow(_count):
            started.set()
            release.wait(5)

        self.fake.on_read = slow
        worker = threading.Thread(target=lambda: self.controller.save(snap, {0: 1000}))
        worker.start()
        self.assertTrue(started.wait(5))
        frames = len(self.fake.frames)
        outcome = self.controller.save(snap, {3: 800})
        self.assertEqual(outcome.kind, OutcomeKind.BUSY)
        with self.assertRaises(DpiBusy):
            self.controller.load()
        self.assertEqual(len(self.fake.frames), frames)  # nada foi enviado pela segunda chamada
        self.fake.on_read = original
        release.set()
        worker.join(5)
        self.assertEqual(self.fake.block(0)[3], 0x16)  # só a primeira gravou
        self.assertEqual(self.fake.block(0)[2 + 18 + 1], 0x53)

    def test_second_process_is_refused_by_the_file_lock(self):
        other = DpiController(self.fake.connect, self.tmp / "backups", self.tmp / "device.lock")
        with self.controller._exclusive():
            outcome = other.save(self.snapshot_unlocked(), {0: 1000})
            self.assertEqual(outcome.kind, OutcomeKind.BUSY)
            self.assertIn("outro processo", outcome.message.lower())

    def snapshot_unlocked(self):
        return DpiController(self.fake.connect, self.tmp / "b").load()


class ProductionConnectorTest(unittest.TestCase):
    def test_open_mouse_reports_missing_device_without_touching_any_node(self):
        from unittest import mock

        from hidctl.core.errors import NoDeviceFound

        with (
            mock.patch(
                "hidctl.devices.fc30_mouse.dpi_service.discovery.find",
                side_effect=NoDeviceFound("x"),
            ),
            self.assertRaises(NoDeviceFound),
            open_mouse(),
        ):
            pass


if __name__ == "__main__":
    unittest.main()
