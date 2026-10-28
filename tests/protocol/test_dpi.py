"""Registro de DPI: decodificação e planejamento. Valores calculados à mão."""

import unittest

from hidctl.core.errors import ProtocolError, ValidationError
from hidctl.devices.fc30_mouse import dpi
from hidctl.devices.fc30_mouse.dpi import CodeEntry

# nível ativo 1; níveis (enabled, x_code, x_flag, y_code, y_flag, pad)
RAW = bytes(
    [1, 0]
    + [1, 0x12, 0, 0x12, 0, 0]  # 0x12 = 18  → 18 × 44,444 ≈ 800
    + [1, 0x24, 0, 0x24, 0, 0]  # 36 → 1600
    + [1, 0x48, 0, 0x48, 0, 0]  # 72 → 3200
    + [1, 0x48, 1, 0x48, 1, 0]  # 72, flag 1 → 6400
    + [0, 0x6C, 1, 0x6C, 1, 0]  # 108, flag 1, desabilitado → 9600
)
TABLE = {
    1700: CodeEntry(1700, 0x26, 0, "test"),
    1200: CodeEntry(1200, 0x1B, 0, "test"),
    1600: CodeEntry(1600, 0x24, 0, "test"),
    5200: CodeEntry(5200, 0x3B, 1, "test"),
    9400: CodeEntry(9400, 0x6A, 1, "test"),  # mesmo flag do nível 4 (desabilitado)
}


class DecodeTest(unittest.TestCase):
    def test_decodes_active_level_and_every_field(self):
        block = dpi.decode_block(0, RAW)
        self.assertEqual(block.address, 0x042)
        self.assertEqual(block.active_level, 1)
        self.assertEqual(block.raw, RAW)
        self.assertEqual(
            [
                (level.enabled, level.x_code, level.x_flag, level.y_code, level.y_flag)
                for level in block.levels
            ],
            [
                (1, 0x12, 0, 0x12, 0),
                (1, 0x24, 0, 0x24, 0),
                (1, 0x48, 0, 0x48, 0),
                (1, 0x48, 1, 0x48, 1),
                (0, 0x6C, 1, 0x6C, 1),
            ],
        )

    def test_estimates(self):
        block = dpi.decode_block(0, RAW)
        self.assertEqual(
            [level.estimate() for level in block.levels], [800, 1600, 3200, 6400, 9600]
        )

    def test_profile_bases(self):
        for profile, base in enumerate((0x042, 0x102, 0x1B2, 0x262, 0x312)):
            self.assertEqual(dpi.decode_block(profile, RAW).address, base)

    def test_inconsistent_blocks_are_rejected(self):
        def with_byte(index, value):
            data = bytearray(RAW)
            data[index] = value
            return bytes(data)

        cases = {
            "tamanho 31": RAW[:-1],
            "tamanho 33": RAW + b"\x00",
            "nível ativo 5": with_byte(0, 5),
            "enabled 2": with_byte(2, 2),
            "flag X 2": with_byte(4, 2),
            "código X 0": with_byte(3, 0),
            "código X 1": with_byte(3, 1),
            "código X 141": with_byte(3, 141),
        }
        for label, raw in cases.items():
            with self.subTest(label), self.assertRaises(ProtocolError):
                dpi.decode_block(0, raw)

    def test_invalid_profile(self):
        for profile in (-1, 5, True, None, "0"):
            with self.subTest(profile=profile), self.assertRaises(ValidationError):
                dpi.decode_block(profile, RAW)

    def test_code_boundaries_are_accepted(self):
        for code in (dpi.CODE_MIN, dpi.CODE_MAX):
            data = bytearray(RAW)
            data[3] = code
            self.assertEqual(dpi.decode_block(0, bytes(data)).levels[0].x_code, code)


class AddressTest(unittest.TestCase):
    def test_record_and_code_addresses(self):
        # base + 2 + 6·nível; o byte do código X é o segundo do registro
        self.assertEqual(dpi.record_address(0, 0), 0x044)
        self.assertEqual(dpi.code_address(0, 1), 0x04B)
        self.assertEqual(dpi.code_address(2, 0), 0x1B5)
        self.assertEqual(dpi.code_address(4, 4), 0x312 + 2 + 24 + 1)

    def test_writable_set_has_exactly_25_code_bytes(self):
        addresses = dpi.writable_addresses()
        self.assertEqual(len(addresses), 25)
        self.assertNotIn(0x002C, addresses)
        self.assertNotIn(dpi.record_address(0, 0), addresses)  # byte "enabled" não é gravável


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.block = dpi.decode_block(1, RAW, token="s")

    def test_plan_changes_only_the_four_bytes_of_one_level(self):
        plan = dpi.plan_level_change(self.block, 1, 1700, TABLE)
        self.assertEqual(plan.address, 0x102 + 2 + 6 + 1)
        self.assertEqual(
            (plan.old, plan.new),
            (bytes.fromhex("24 00 24 00"), bytes.fromhex("26 00 26 00")),
        )
        self.assertEqual((plan.profile, plan.level, plan.nominal), (1, 1, 1700))
        self.assertEqual(plan.block_raw, RAW)
        self.assertEqual(plan.token, "s")

    def test_rejections(self):
        cases = {
            "DPI fora da tabela": (1, 1650),
            "DPI zero": (1, 0),
            "DPI 12000": (1, 12000),
            "DPI float": (1, 1700.0),
            "DPI bool": (1, True),
            "nível -1": (-1, 1700),
            "nível 5": (5, 1700),
            "nível bool": (True, 1700),
            "mesmo código": (1, 1600),
            "nível desabilitado (flag igual, só a regra de habilitado barra)": (
                4,
                9400,
            ),
            "mudaria o flag": (0, 5200),
        }
        for label, (level, target) in cases.items():
            with self.subTest(label), self.assertRaises(ValidationError):
                dpi.plan_level_change(self.block, level, target, TABLE)

    def test_asymmetric_level_is_not_touched(self):
        data = bytearray(RAW)
        data[2 + 6 + 3] = 0x30  # y_code do nível 1 diferente do x_code
        block = dpi.decode_block(1, bytes(data), token="s")
        with self.assertRaises(ValidationError):
            dpi.plan_level_change(block, 1, 1700, TABLE)
        with self.assertRaises(ValidationError):
            dpi.plan_code_restore(block, 1, 0x1B)

    def test_flags_are_preserved_in_the_written_run(self):
        plan = dpi.plan_level_change(self.block, 3, 5200, {5200: CodeEntry(5200, 0x3B, 1, "test")})
        self.assertEqual(
            (plan.old, plan.new),
            (bytes.fromhex("48 01 48 01"), bytes.fromhex("3b 01 3b 01")),
        )

    def test_empty_table_rejects_everything(self):
        with self.assertRaises(ValidationError):
            dpi.plan_level_change(self.block, 1, 1700, {})


if __name__ == "__main__":
    unittest.main()


class RestorePlanTest(unittest.TestCase):
    def setUp(self):
        self.block = dpi.decode_block(0, RAW, token="s")

    def test_restore_plan_writes_the_original_code_to_the_same_byte(self):
        plan = dpi.plan_code_restore(self.block, 1, 0x1B)
        self.assertEqual(
            (plan.address, plan.old, plan.new),
            (0x04B, bytes.fromhex("24 00 24 00"), bytes.fromhex("1b 00 1b 00")),
        )
        self.assertEqual(plan.nominal, 1200)  # estimativa de 0x1B: 27 × 44,444

    def test_restore_rejections(self):
        for level, code in (
            (5, 0x1B),
            (-1, 0x1B),
            (4, 0x1B),
            (1, 0x24),
            (1, 1),
            (1, 141),
            (1, True),
            (1, None),
        ):
            with (
                self.subTest(level=level, code=code),
                self.assertRaises(ValidationError),
            ):
                dpi.plan_code_restore(self.block, level, code)
