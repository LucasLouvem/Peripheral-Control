"""Transporte hidraw: números de ioctl e mapeamento de erros, sem tocar em nenhum dispositivo."""

import errno
import os
import unittest

from hidctl.core.errors import DeviceGone, IoFailure, PermissionDenied
from hidctl.core.transport import (
    HidrawTransport,
    LoggingTransport,
    hidiocgfeature,
    hidiocsfeature,
)


class IoctlNumbersTest(unittest.TestCase):
    def test_numbers_match_the_kernel_header(self):
        """Valores montados à mão de ``_IOC(_IOC_WRITE|_IOC_READ, 'H', nr, len)``.

        dir=3 (bits 30-31), len (bits 16-29), 'H'=0x48 (bits 8-15), nr (0x06 SET, 0x07 GET).
        Falha se alguém usar 0x01 (HIDIOCGRDESCSIZE) como GET, como fez uma ferramenta externa.
        """
        self.assertEqual(hidiocsfeature(16), 0xC0104806)
        self.assertEqual(hidiocgfeature(16), 0xC0104807)
        self.assertEqual(hidiocsfeature(64), 0xC0404806)
        self.assertEqual(hidiocgfeature(41), 0xC0294807)

    def test_invalid_length(self):
        for length in (0, -1, 1 << 14):
            with self.subTest(length=length), self.assertRaises(ValueError):
                hidiocgfeature(length)


class Recorder:
    def __init__(self, result=None, error=None):
        self.calls = []
        self.result, self.error = result, error

    def __call__(self, fd, request, buffer, mutate=True):
        self.calls.append((fd, request, bytes(buffer)))
        if self.error:
            raise self.error
        result = self.result(buffer) if callable(self.result) else self.result
        return result


def make(ioctl, opener=lambda path, flags: 7):
    closed = []
    transport = HidrawTransport("/dev/hidrawX", opener=opener, ioctl=ioctl, closer=closed.append)
    return transport, closed


class SetGetTest(unittest.TestCase):
    def test_set_feature_sends_the_exact_buffer_with_the_right_request(self):
        rec = Recorder(result=16)
        transport, _ = make(rec)
        transport.set_feature(bytes([2] + [0xAA] * 15))
        self.assertEqual(rec.calls, [(7, 0xC0104806, bytes([2] + [0xAA] * 15))])

    def test_set_feature_detects_short_write(self):
        transport, _ = make(Recorder(result=9))
        with self.assertRaises(IoFailure):
            transport.set_feature(bytes(16))

    def test_get_feature_puts_the_report_id_first_and_returns_only_received_bytes(self):
        def fill(buffer):
            buffer[1:4] = b"\x08\x2c\x60"
            return 4

        rec = Recorder(result=fill)
        transport, _ = make(rec)
        self.assertEqual(transport.get_feature(2, 9), bytes([2, 8, 0x2C, 0x60]))
        self.assertEqual(rec.calls[0][1:], (0xC0094807, bytes([2] + [0] * 8)))

    def test_empty_get_response_is_an_error(self):
        for value in (0, -1):
            transport, _ = make(Recorder(result=value))
            with self.subTest(value=value), self.assertRaises(IoFailure):
                transport.get_feature(2, 16)


class ErrorMappingTest(unittest.TestCase):
    def test_open_errors(self):
        cases = {
            errno.EACCES: PermissionDenied,
            errno.EPERM: PermissionDenied,
            errno.ENOENT: DeviceGone,
            errno.ENODEV: DeviceGone,
            errno.EBUSY: IoFailure,
        }
        for code, expected in cases.items():

            def opener(path, flags, code=code):
                raise OSError(code, os.strerror(code))

            with self.subTest(errno=code), self.assertRaises(expected):
                HidrawTransport("/dev/hidrawX", opener=opener)

    def test_ioctl_errors(self):
        cases = {
            errno.EACCES: PermissionDenied,
            errno.ENODEV: DeviceGone,
            errno.EIO: IoFailure,
            errno.EPIPE: IoFailure,
        }
        for code, expected in cases.items():
            transport, _ = make(Recorder(error=OSError(code, os.strerror(code))))
            with self.subTest(errno=code):
                with self.assertRaises(expected):
                    transport.set_feature(bytes(16))
                with self.assertRaises(expected):
                    transport.get_feature(2, 16)

    def test_opens_read_write(self):
        seen = []
        make(
            Recorder(result=1),
            opener=lambda path, flags: seen.append((path, flags)) or 3,
        )
        self.assertEqual(seen, [("/dev/hidrawX", os.O_RDWR)])


class CloseTest(unittest.TestCase):
    def test_close_is_idempotent_and_closes_the_descriptor_once(self):
        transport, closed = make(Recorder(result=1))
        transport.close()
        transport.close()
        self.assertEqual(closed, [7])

    def test_use_after_close_fails_without_calling_ioctl(self):
        rec = Recorder(result=16)
        transport, _ = make(rec)
        transport.close()
        with self.assertRaises(IoFailure):
            transport.set_feature(bytes(16))
        self.assertEqual(rec.calls, [])


class LoggingTest(unittest.TestCase):
    def test_logs_requests_and_responses_in_hex(self):
        class Inner:
            def set_feature(self, data):
                pass

            def get_feature(self, report_id, length):
                return bytes([2, 8, 0x2C])

            def close(self):
                pass

        lines = []
        logged = LoggingTransport(Inner(), lines.append)
        logged.set_feature(bytes([2, 0xF5, 0]))
        logged.get_feature(2, 9)
        self.assertEqual(lines, ["SET 02 f5 00", "GET id=0x02 len=9", "RSP 02 08 2c"])

    def test_logs_failures_and_reraises(self):
        class Inner:
            def set_feature(self, data):
                raise IoFailure("x")

            def get_feature(self, report_id, length):
                raise IoFailure("y")

            def close(self):
                pass

        lines = []
        logged = LoggingTransport(Inner(), lines.append)
        with self.assertRaises(IoFailure):
            logged.set_feature(b"\x02")
        with self.assertRaises(IoFailure):
            logged.get_feature(2, 9)
        self.assertEqual(lines[1], "SET falhou: x")
        self.assertEqual(lines[-1], "GET falhou: y")


if __name__ == "__main__":
    unittest.main()
