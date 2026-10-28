"""Descoberta por sysfs falso. Prova que nada depende do número do hidraw."""

import tempfile
import unittest
from pathlib import Path

from hidctl.core import discovery
from hidctl.core.errors import (
    AmbiguousDevice,
    DescriptorMismatch,
    NoDeviceFound,
    RevisionMismatch,
)
from hidctl.devices.fc30_mouse.spec import SPEC

from .fixtures import (
    CONFIG_IFACE,
    KEYBOARD_BOOT,
    MOUSE_BOOT,
    make_mouse,
    make_usb_device,
)


class FindMouseTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def find(self):
        return discovery.find(SPEC, self.root, Path("/devnodes"))

    def test_finds_interface_two_with_its_identity(self):
        make_mouse(self.root)
        found = self.find()
        self.assertEqual(found.name, "hidraw5")
        self.assertEqual(found.node, Path("/devnodes/hidraw5"))
        self.assertEqual(
            (
                found.vendor_id,
                found.product_id,
                found.bcd_device,
                found.interface_number,
            ),
            (0x04D9, 0xFC30, 0x0112, 2),
        )
        self.assertEqual(found.descriptor, CONFIG_IFACE)

    def test_hidraw_numbers_are_not_assumed(self):
        make_mouse(self.root, hidraw_names=("hidraw11", "hidraw12", "hidraw17"))
        self.assertEqual(self.find().name, "hidraw17")

    def test_ignores_other_hid_devices_including_a_keyboard(self):
        make_usb_device(
            self.root,
            "7-2",
            0x258A,
            0x019D,
            0x0100,
            [(0, KEYBOARD_BOOT, "hidraw0"), (1, CONFIG_IFACE, "hidraw1")],
        )
        make_mouse(self.root)
        self.assertEqual(self.find().name, "hidraw5")

    def test_no_device(self):
        make_usb_device(self.root, "7-2", 0x258A, 0x019D, 0x0100, [(0, KEYBOARD_BOOT, "hidraw0")])
        with self.assertRaises(NoDeviceFound):
            self.find()

    def test_empty_or_missing_sysfs(self):
        with self.assertRaises(NoDeviceFound):
            self.find()

    def test_other_revision_is_refused_and_reported(self):
        make_mouse(self.root, bcd=0x0300)
        with self.assertRaises(RevisionMismatch) as raised:
            self.find()
        self.assertIn("0x0300", str(raised.exception))
        self.assertIn("0x0112", str(raised.exception))

    def test_descriptor_without_expected_feature_reports(self):
        make_usb_device(
            self.root,
            "5-3",
            0x04D9,
            0xFC30,
            0x0112,
            [(0, MOUSE_BOOT, "hidraw3"), (1, KEYBOARD_BOOT, "hidraw4")],
        )
        with self.assertRaises(DescriptorMismatch):
            self.find()

    def test_descriptor_with_wrong_report_size_is_rejected(self):
        altered = CONFIG_IFACE.replace(bytes.fromhex("95 0f b1 02"), bytes.fromhex("95 0e b1 02"))
        self.assertNotEqual(altered, CONFIG_IFACE)
        make_usb_device(self.root, "5-3", 0x04D9, 0xFC30, 0x0112, [(2, altered, "hidraw5")])
        with self.assertRaises(DescriptorMismatch):
            self.find()

    def test_two_identical_mice_are_ambiguous(self):
        make_mouse(self.root)
        make_mouse(self.root, hidraw_names=("hidraw8", "hidraw9", "hidraw10"), usb_name="5-4")
        with self.assertRaises(AmbiguousDevice):
            self.find()

    def test_incomplete_entries_are_skipped(self):
        make_mouse(self.root)
        (self.root / "class" / "hidraw" / "hidraw99").mkdir()  # sem link "device"
        self.assertEqual(self.find().name, "hidraw5")


if __name__ == "__main__":
    unittest.main()
