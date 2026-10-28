"""Parser de report descriptor. Valores esperados vêm do hardware real (descritores lidos do aparelho)."""

import unittest

from hidctl.core.errors import DescriptorError
from hidctl.core.hid_descriptor import parse

from .fixtures import CONFIG_IFACE, KEYBOARD_BOOT, MOUSE_BOOT


class RealDescriptorsTest(unittest.TestCase):
    def test_config_interface_feature_sizes_match_the_device(self):
        """Falha se o parser errar tamanhos de relatório (ex.: bits do prefixo trocados)."""
        parsed = parse(CONFIG_IFACE)
        self.assertEqual(
            {rid: parsed.wire_size("feature", rid) for rid in range(2, 7)},
            {2: 16, 3: 64, 4: 256, 5: 1024, 6: 2048},
        )
        self.assertIsNone(parsed.wire_size("feature", 1))
        self.assertIsNone(parsed.wire_size("feature", 7))

    def test_config_interface_input_reports_and_pages(self):
        parsed = parse(CONFIG_IFACE)
        self.assertEqual(
            {rid: parsed.wire_size("input", rid) for rid in (1, 7, 8)},
            {1: 8, 7: 8, 8: 8},
        )
        self.assertEqual(parsed.collection_pages, (0x0C, 0xFFA0))
        self.assertEqual(parsed.pages_of("feature", 2), {0xFFA0})
        self.assertEqual(parsed.pages_of("input", 1), {0x0C})

    def test_boot_interfaces_have_no_feature_reports(self):
        for name, data in (("mouse", MOUSE_BOOT), ("keyboard", KEYBOARD_BOOT)):
            with self.subTest(name):
                self.assertEqual(parse(data).payload_sizes("feature"), {})

    def test_boot_report_sizes(self):
        # mouse: 16 botões + X/Y de 16 bits + roda + AC Pan = 64 bits; teclado: 8 + 8 + 48 = 64 bits
        self.assertEqual(parse(MOUSE_BOOT).payload_sizes("input"), {0: 8})
        self.assertEqual(parse(KEYBOARD_BOOT).payload_sizes("input"), {0: 8})
        self.assertEqual(parse(KEYBOARD_BOOT).payload_sizes("output"), {})


class MalformedDescriptorTest(unittest.TestCase):
    def test_truncated_item(self):
        with self.assertRaises(DescriptorError):
            parse(bytes.fromhex("05 0c 09 01 a1 01 96 ff"))  # Report Count com 2 bytes, só 1

    def test_unbalanced_collections(self):
        with self.assertRaises(DescriptorError):
            parse(bytes.fromhex("05 0c 09 01 a1 01"))  # sem End Collection
        with self.assertRaises(DescriptorError):
            parse(bytes.fromhex("c0"))  # End Collection solto

    def test_reserved_item_type(self):
        with self.assertRaises(DescriptorError):
            parse(bytes([0x0C]))  # bType = 3

    def test_long_item_is_skipped_and_truncated_long_item_fails(self):
        with_long = bytes([0xFE, 0x02, 0x10, 0xAA, 0xBB]) + CONFIG_IFACE
        self.assertEqual(parse(with_long).wire_size("feature", 3), 64)
        with self.assertRaises(DescriptorError):
            parse(bytes([0xFE, 0x05, 0x10, 0xAA]))

    def test_empty_descriptor_is_valid_and_empty(self):
        parsed = parse(b"")
        self.assertEqual(parsed.fields, ())
        self.assertEqual(parsed.collection_pages, ())


if __name__ == "__main__":
    unittest.main()
