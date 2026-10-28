"""Sessão: ordem dos quadros, guardas e ausência de envio quando algo é rejeitado."""

import json
import tempfile
import unittest
from pathlib import Path

from hidctl.core.errors import IoFailure, ProtocolError, SessionError, ValidationError
from hidctl.devices.fc30_mouse import dpi
from hidctl.devices.fc30_mouse.dpi import CodeEntry
from hidctl.devices.fc30_mouse.session import MouseSession

from .fakes import FakeTransport, hx, response
from .test_dpi import RAW

LOCK0 = hx("02f50000000000000000000000000000")
LOCK1 = hx("02f50100000000000000000000000000")
READ_ACTIVE = hx("02f22c00010000000000000000000000")
READ_BLOCK0 = hx("02f2420020000000" + "00" * 8)
APPLY_DPI = hx("02f10202000000000000000000000000")
TABLE = {1700: CodeEntry(1700, 0x26, 0, "test"), 1600: CodeEntry(1600, 0x24, 0, "test")}


class SessionCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)


class ReadSequenceTest(SessionCase):
    def test_read_sequence_is_lock_reads_unlock_with_exact_bytes(self):
        t = FakeTransport([response(0x2C, b"\x00"), response(0x42, RAW)])
        with MouseSession(t) as session:
            self.assertEqual(session.read_active_profile(), 0)
            block = session.read_dpi_block(0)
        self.assertEqual(t.sent, [LOCK0, READ_ACTIVE, READ_BLOCK0, LOCK1])
        self.assertEqual(t.gets, [(2, 9), (2, 40)])
        self.assertEqual(block.raw, RAW)
        self.assertEqual(block.active_level, 1)

    def test_unlock_is_sent_even_if_the_caller_raises(self):
        t = FakeTransport()
        with self.assertRaises(RuntimeError), MouseSession(t):
            raise RuntimeError("falha do chamador")
        self.assertEqual(t.sent, [LOCK0, LOCK1])

    def test_invalid_read_arguments_send_nothing_but_the_lock_pair(self):
        t = FakeTransport()
        with MouseSession(t) as session:
            for bad in ((-1, 1), (0, 0), (0, 51)):
                with self.subTest(bad), self.assertRaises(ValidationError):
                    session.read_memory(*bad)
            with self.assertRaises(ValidationError):
                session.read_dpi_block(9)
        self.assertEqual(t.sent, [LOCK0, LOCK1])

    def test_active_profile_out_of_range_is_a_protocol_error(self):
        t = FakeTransport([response(0x2C, b"\x07")])
        with self.assertRaises(ProtocolError), MouseSession(t) as session:
            session.read_active_profile()
        self.assertEqual(t.sent, [LOCK0, READ_ACTIVE, LOCK1])


class FailureHandlingTest(SessionCase):
    def test_bad_response_stops_everything_without_retry(self):
        bad = bytearray(response(0x2C, b"\x00"))
        bad[1] = 0x07
        t = FakeTransport([bytes(bad), response(0x2C, b"\x00")])
        with MouseSession(t) as session:
            with self.assertRaises(ProtocolError):
                session.read_active_profile()
            self.assertTrue(session.failed)
            with self.assertRaises(SessionError):
                session.read_active_profile()  # não repete
        self.assertEqual(t.sent, [LOCK0, READ_ACTIVE, LOCK1])  # só 1 leitura enviada
        self.assertEqual(len(t.gets), 1)

    def test_transport_failure_invalidates_the_session_and_still_unlocks(self):
        t = FakeTransport(fail_set_at=1)
        with MouseSession(t) as session:
            with self.assertRaises(IoFailure):
                session.read_active_profile()
            with self.assertRaises(SessionError):
                session.read_memory(0x42, 32)
        self.assertEqual(t.sent, [LOCK0, READ_ACTIVE, LOCK1])

    def test_failed_get_invalidates(self):
        t = FakeTransport(fail_get_at=0)
        with MouseSession(t) as session:
            with self.assertRaises(IoFailure):
                session.read_active_profile()
            self.assertTrue(session.failed)

    def test_failure_to_unlock_is_reported_when_nothing_else_failed(self):
        t = FakeTransport(fail_set_at=1)
        with self.assertRaises(IoFailure), MouseSession(t):
            pass

    def test_failure_to_unlock_does_not_hide_the_original_error(self):
        t = FakeTransport(fail_set_at=1)
        with self.assertRaises(RuntimeError), MouseSession(t):
            raise RuntimeError("original")

    def test_failed_lock_does_not_send_the_unlock(self):
        t = FakeTransport(fail_set_at=0)
        with self.assertRaises(IoFailure), MouseSession(t):
            pass
        self.assertEqual(t.sent, [LOCK0])

    def test_operations_outside_the_context_are_refused(self):
        t = FakeTransport()
        with self.assertRaises(SessionError):
            MouseSession(t).read_active_profile()
        self.assertEqual(t.sent, [])


class WriteTest(SessionCase):
    def open_with_block(self, extra_responses=()):
        t = FakeTransport([response(0x42, RAW), *extra_responses])
        return t, MouseSession(t)

    def test_rejected_plan_sends_no_write(self):
        t, session = self.open_with_block()
        with session:
            block = session.read_dpi_block(0)
            with self.assertRaises(ValidationError):
                dpi.plan_level_change(block, 1, 1650, TABLE)  # fora da tabela
            with self.assertRaises(ValidationError):
                dpi.plan_level_change(block, 1, 1600, TABLE)  # já é o código atual
        self.assertEqual(t.sent, [LOCK0, READ_BLOCK0, LOCK1])

    def test_successful_write_sends_one_four_byte_frame_after_the_backup(self):
        t, session = self.open_with_block()
        with session:
            block = session.read_dpi_block(0)
            plan = dpi.plan_level_change(block, 1, 1700, TABLE)
            backup = session.apply_plan(plan, self.dir)
            self.assertEqual(t.sent, [LOCK0, READ_BLOCK0, hx("02f34b00040000002600260000000000")])
            session.commit_dpi()
        self.assertEqual(t.sent[-2:], [APPLY_DPI, LOCK1])
        saved = json.loads(backup.read_text())
        self.assertEqual(saved["block_hex"], RAW.hex(" "))
        self.assertEqual(
            saved["planned"],
            {
                "level": 1,
                "address": "0x004b",
                "old": "24 00 24 00",
                "new": "26 00 26 00",
            },
        )
        self.assertEqual(saved["profile"], 0)

    def test_write_requires_a_block_read_in_the_same_session(self):
        t1, first = self.open_with_block()
        with first:
            plan = dpi.plan_level_change(first.read_dpi_block(0), 1, 1700, TABLE)
        t2 = FakeTransport()
        with MouseSession(t2) as second, self.assertRaises(SessionError):
            second.apply_plan(plan, self.dir)
        self.assertEqual(t2.sent, [LOCK0, LOCK1])
        self.assertEqual(list(self.dir.iterdir()), [])  # nem backup foi criado

    def test_backup_failure_prevents_the_write(self):
        t, session = self.open_with_block()
        blocker = self.dir / "arquivo"
        blocker.write_text("x")
        with session:
            plan = dpi.plan_level_change(session.read_dpi_block(0), 1, 1700, TABLE)
            with self.assertRaises(SessionError):
                session.apply_plan(plan, blocker / "sub")  # não dá para criar diretório
        self.assertEqual(t.sent, [LOCK0, READ_BLOCK0, LOCK1])

    def test_plan_outside_the_allowed_region_is_refused(self):
        t, session = self.open_with_block()
        with session:
            block = session.read_dpi_block(0)
            good = dpi.plan_level_change(block, 1, 1700, TABLE)
            for address in (0x002C, 0x044, 0x04A, 0x500):
                forged = dpi.WritePlan(**{**good.__dict__, "address": address})
                with self.subTest(address=address), self.assertRaises(SessionError):
                    session.apply_plan(forged, self.dir)
            multi = dpi.WritePlan(
                **{**good.__dict__, "new": b"\x26\x00"}
            )  # 2 bytes: tamanho errado
            with self.assertRaises(SessionError):
                session.apply_plan(multi, self.dir)
        self.assertEqual(t.sent, [LOCK0, READ_BLOCK0, LOCK1])

    def test_failed_write_is_not_retried_and_blocks_the_commit(self):
        t = FakeTransport([response(0x42, RAW)], fail_set_at=2)  # SETs: 0 lock, 1 leitura, 2 = o F3
        with MouseSession(t) as session:
            plan = dpi.plan_level_change(session.read_dpi_block(0), 1, 1700, TABLE)
            with self.assertRaises(IoFailure):
                session.apply_plan(plan, self.dir)
            with self.assertRaises(SessionError):
                session.commit_dpi()
        self.assertEqual(
            t.sent, [LOCK0, READ_BLOCK0, hx("02f34b00040000002600260000000000"), LOCK1]
        )


if __name__ == "__main__":
    unittest.main()
