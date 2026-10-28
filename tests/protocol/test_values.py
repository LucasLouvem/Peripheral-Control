"""Tabela de valores liberados e das evidências. Protege contra liberar valor sem prova."""

import unittest

from hidctl.devices.fc30_mouse import values
from hidctl.devices.fc30_mouse.values import Evidence

# códigos lidos no aparelho em 2026-10-28 (25 registros: docs/devices/cobra-m711.md)
OBSERVED_CODES = {0x0B, 0x12, 0x16, 0x1B, 0x2E, 0x37, 0x45, 0x53, 0x73}


class ValuesTest(unittest.TestCase):
    def test_exact_value_list_and_codes(self):
        self.assertEqual(
            [(v.nominal, v.code, v.flag) for v in values.VALUES],
            [
                (500, 0x0B, 0),
                (800, 0x12, 0),
                (1000, 0x16, 0),
                (1200, 0x1B, 0),
                (2000, 0x2E, 0),
                (2400, 0x37, 0),
                (3000, 0x45, 0),
                (3600, 0x53, 0),
                (5000, 0x73, 0),
            ],
        )

    def test_tested_values_are_the_three_written_and_perceived_ones(self):
        tested = [v.nominal for v in values.VALUES if v.evidence is Evidence.TESTED_PERCEIVED]
        self.assertEqual(tested, [800, 1000, 5000])

    def test_the_other_six_were_written_and_read_back_but_not_perceived(self):
        readback = [v.nominal for v in values.VALUES if v.evidence is Evidence.WRITTEN_READBACK]
        self.assertEqual(readback, [500, 1200, 2000, 2400, 3000, 3600])

    def test_only_written_values_are_offered(self):
        for entry in values.VALUES:
            with self.subTest(nominal=entry.nominal):
                self.assertEqual(
                    entry.writable,
                    entry.evidence in (Evidence.TESTED_PERCEIVED, Evidence.WRITTEN_READBACK),
                )
        for entry in values.writable_values():
            self.assertIn(entry.evidence, (Evidence.TESTED_PERCEIVED, Evidence.WRITTEN_READBACK))
        self.assertEqual(set(values.code_table()), {v.nominal for v in values.writable_values()})

    def test_values_not_proven_are_never_offered(self):
        offered = {v.nominal for v in values.writable_values()}
        for forbidden in (10000, 12000, 6400, 1600, 3200, 100, 400, 0, -1):
            self.assertNotIn(forbidden, offered)

    def test_all_codes_are_distinct_and_were_observed_on_the_device(self):
        codes = [(v.code, v.flag) for v in values.VALUES]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual({c for c, _ in codes}, OBSERVED_CODES)
        self.assertTrue(all(flag == 0 for _, flag in codes))  # flag 1 nunca foi gravado

    def test_lookups(self):
        self.assertEqual(values.by_code(0x16, 0).nominal, 1000)
        self.assertIsNone(values.by_code(0x16, 1))
        self.assertIsNone(values.by_code(0x99, 0))
        self.assertEqual(values.by_nominal(5000).code, 0x73)
        self.assertIsNone(values.by_nominal(12000))

    def test_estimates_follow_the_documented_formula(self):
        # 0x12 = 18 -> 18 × 44,444 = 800;  0x73 = 115 -> 5111
        self.assertEqual(
            (values.by_nominal(800).estimate, values.by_nominal(5000).estimate),
            (800, 5111),
        )


if __name__ == "__main__":
    unittest.main()
