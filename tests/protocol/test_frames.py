"""Quadros do protocolo. Os bytes esperados foram montados à mão a partir do layout documentado."""

import unittest

from hidctl.core.errors import ProtocolError, ValidationError
from hidctl.devices.fc30_mouse import frames

PAD = "00 " * 8


def hx(text: str) -> bytes:
    return bytes.fromhex(text.replace("\n", " "))


class BuilderTest(unittest.TestCase):
    def test_lock_frames(self):
        self.assertEqual(frames.lock_frame(False), hx("02 f5 00 00 00 00 00 00 " + PAD))
        self.assertEqual(frames.lock_frame(True), hx("02 f5 01 00 00 00 00 00 " + PAD))

    def test_read_frame_is_little_endian(self):
        self.assertEqual(frames.read_frame(0x002C, 1), hx("02 f2 2c 00 01 00 00 00 " + PAD))
        self.assertEqual(frames.read_frame(0x0102, 32), hx("02 f2 02 01 20 00 00 00 " + PAD))

    def test_write_frame_carries_data_and_pads_to_16(self):
        self.assertEqual(
            frames.write_frame(0x004B, b"\x26"),
            hx("02 f3 4b 00 01 00 00 00 26 00 00 00 00 00 00 00"),
        )
        self.assertEqual(
            frames.write_frame(0x01B5, bytes(range(1, 9))),
            hx("02 f3 b5 01 08 00 00 00 01 02 03 04 05 06 07 08"),
        )

    def test_apply_frame(self):
        self.assertEqual(frames.apply_frame(frames.AREA_DPI), hx("02 f1 02 02 00 00 00 00 " + PAD))
        self.assertEqual(frames.apply_frame(0x10), hx("02 f1 02 10 00 00 00 00 " + PAD))

    def test_every_frame_is_16_bytes(self):
        for built in (
            frames.lock_frame(True),
            frames.read_frame(0, 50),
            frames.write_frame(0, b"a"),
            frames.apply_frame(1),
        ):
            self.assertEqual(len(built), 16)


class RejectedInputTest(unittest.TestCase):
    def test_invalid_reads(self):
        for address, count in (
            (-1, 1),
            (0x10000, 1),
            (0, 0),
            (0, -3),
            (0, frames.MAX_READ + 1),
            (0xFFFF, 2),
            (True, 1),
            (0, True),
            ("1", 1),
        ):
            with (
                self.subTest(address=address, count=count),
                self.assertRaises(ValidationError),
            ):
                frames.read_frame(address, count)

    def test_invalid_writes(self):
        for address, data in (
            (0, b""),
            (0, b"x" * 9),
            (-1, b"a"),
            (0x10000, b"a"),
            (0xFFFF, b"ab"),
            (0, "a"),
            (0, None),
        ):
            with (
                self.subTest(address=address, data=data),
                self.assertRaises(ValidationError),
            ):
                frames.write_frame(address, data)

    def test_invalid_apply_areas(self):
        for area in (0, 256, -1, True, None):
            with self.subTest(area=area), self.assertRaises(ValidationError):
                frames.apply_frame(area)

    def test_boundaries_are_accepted(self):
        self.assertEqual(len(frames.read_frame(0, frames.MAX_READ)), 16)
        self.assertEqual(len(frames.write_frame(0xFFFF, b"z")), 16)
        self.assertEqual(len(frames.write_frame(0, b"x" * 8)), 16)


class ResponseTest(unittest.TestCase):
    def good(self, address=0x0102, data=bytes(range(32))):
        header = bytes(
            [
                0x02,
                0x08,
                address & 0xFF,
                0x60 | (address >> 8),
                len(data),
                0x00,
                0xFA,
                0xFA,
            ]
        )
        return header + data

    def test_valid_response_returns_exact_data(self):
        data = bytes(range(32))
        self.assertEqual(frames.parse_read_response(self.good(0x0102, data), 0x0102, 32), data)
        self.assertEqual(frames.parse_read_response(self.good(0x002C, b"\x03"), 0x002C, 1), b"\x03")

    def test_odd_address_echo_rounds_down_but_data_starts_at_requested_address(self):
        # captura real (2026-10-28): pedido 0x0449 len 8 → cabeçalho com 0x48
        raw = bytes.fromhex("02 08 48 64 08 00 fa fa ff 00 00 01 02 04 03 80".replace(" ", ""))
        self.assertEqual(
            frames.parse_read_response(raw, 0x0449, 8),
            bytes.fromhex("ff00000102040380"),
        )
        wrong = bytes.fromhex("02 08 4a 64 08 00 fa fa ff 00 00 01 02 04 03 80".replace(" ", ""))
        with self.assertRaises(ProtocolError):
            frames.parse_read_response(wrong, 0x0449, 8)

    def test_extra_trailing_bytes_are_ignored(self):
        self.assertEqual(
            frames.parse_read_response(self.good(0x2C, b"\x03") + b"\xff\xff", 0x2C, 1),
            b"\x03",
        )

    def test_invalid_responses_raise_protocol_error(self):
        ok = self.good(0x0102, bytes(32))
        cases = {
            "id errado": b"\x03" + ok[1:],
            "marca 0x08 ausente": ok[:1] + b"\x07" + ok[2:],
            "endereço baixo trocado": ok[:2] + b"\x03" + ok[3:],
            "endereço alto sem 0x60": ok[:3] + b"\x01" + ok[4:],
            "count divergente": ok[:4] + b"\x1f" + ok[5:],
            "byte 5 não nulo": ok[:5] + b"\x01" + ok[6:],
            "sem FA FA": ok[:6] + b"\x00\x00" + ok[8:],
            "curta": ok[:-1],
            "vazia": b"",
        }
        for label, raw in cases.items():
            with self.subTest(label), self.assertRaises(ProtocolError):
                frames.parse_read_response(raw, 0x0102, 32)


if __name__ == "__main__":
    unittest.main()
