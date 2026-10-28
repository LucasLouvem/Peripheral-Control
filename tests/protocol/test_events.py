"""Eventos de troca de DPI: interpretação dos bytes e laço de escuta (com pipes, sem hardware)."""

import errno
import os
import socket
import threading
import unittest

from hidctl.core.errors import NoDeviceFound
from hidctl.devices.fc30_mouse import events


def pair() -> tuple[int, int]:
    """Como o hidraw: cada ``write`` vira exatamente um ``read`` (um relatório por vez)."""
    reader, writer = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    os.set_blocking(reader.fileno(), False)
    return reader.detach(), writer.detach()


def report(*head: int) -> bytes:
    return bytes(head).ljust(8, b"\x00")


class ParseTest(unittest.TestCase):
    def test_valid_events_for_each_level(self):
        for level in range(5):
            with self.subTest(level=level):
                self.assertEqual(events.parse_level_event(report(0x08, 0x02, level)), level)

    def test_real_bytes_captured_from_the_device(self):
        # capturados em 2026-10-28 ao apertar o botão (docs/devices/cobra-m711.md)
        self.assertEqual(events.parse_level_event(bytes.fromhex("08 02 02 00 00 00 00 00")), 2)
        self.assertEqual(events.parse_level_event(bytes.fromhex("08 02 04 00 00 00 00 00")), 4)

    def test_everything_else_is_ignored(self):
        ignored = [
            report(0x08, 0x02, 5),
            report(0x08, 0x02, 255),
            report(0x08, 0x01, 1),
            report(0x08, 0x06, 2),
            report(0x01, 0x02, 2),
            report(0x07, 0x02, 2),
            b"",
            b"\x08\x02\x01",
            report(0x08, 0x02, 1) + b"\x00",
        ]
        for data in ignored:
            with self.subTest(data=data.hex()):
                self.assertIsNone(events.parse_level_event(data))


class ListenTest(unittest.TestCase):
    def run_listener(self, opener, feed, expect: int):
        stop, seen = threading.Event(), []
        done = threading.Event()

        def on_level(level):
            seen.append(level)
            if len(seen) >= expect:
                done.set()

        thread = threading.Thread(
            target=events.listen,
            args=(stop, on_level, opener, lambda _s: stop.wait(0.01)),
        )
        thread.start()
        feed()
        done.wait(5)
        stop.set()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        return seen

    def test_delivers_valid_events_in_order_and_skips_invalid_ones(self):
        read_end, write_end = pair()

        def feed():
            for data in (
                report(8, 2, 3),
                report(8, 2, 9),
                report(8, 1, 0),
                report(8, 2, 4),
                report(8, 2, 4),
                report(8, 2, 0),
            ):
                os.write(write_end, data)

        try:
            self.assertEqual(self.run_listener(lambda: read_end, feed, 4), [3, 4, 4, 0])
        finally:
            os.close(write_end)

    def test_missing_device_is_retried_until_it_appears(self):
        read_end, write_end = pair()
        attempts = []

        def opener():
            attempts.append(1)
            if len(attempts) < 3:
                raise NoDeviceFound("ainda não")
            return read_end

        try:
            seen = self.run_listener(opener, lambda: os.write(write_end, report(8, 2, 1)), 1)
        finally:
            os.close(write_end)
        self.assertEqual((seen, len(attempts) >= 3), ([1], True))

    def test_disconnect_reopens_and_keeps_listening(self):
        first_r, first_w = pair()
        second_r, second_w = pair()
        pipes = iter([first_r, second_r])

        def feed():
            os.write(first_w, report(8, 2, 1))
            os.close(first_w)  # EOF: simula o mouse que sumiu
            os.write(second_w, report(8, 2, 2))

        try:
            seen = self.run_listener(lambda: next(pipes), feed, 2)
        finally:
            os.close(second_w)
        self.assertEqual(seen, [1, 2])

    def test_stop_ends_the_loop_without_events(self):
        read_end, write_end = pair()
        stop = threading.Event()
        thread = threading.Thread(
            target=events.listen, args=(stop, lambda _l: None, lambda: read_end)
        )
        thread.start()
        stop.set()
        thread.join(5)
        os.close(write_end)
        self.assertFalse(thread.is_alive())

    def test_unexpected_os_error_is_not_swallowed(self):
        def opener():
            raise OSError(errno.EACCES, "sem acesso")

        stop, calls = threading.Event(), []

        def sleeper(_s):
            calls.append(1)
            if len(calls) >= 2:
                stop.set()

        events.listen(
            stop, lambda _l: None, opener, sleeper
        )  # acesso negado: tenta de novo, sem estourar
        self.assertGreaterEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
