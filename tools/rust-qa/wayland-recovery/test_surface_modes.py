"""Regression checks for source-bound validation of native presentation records."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "graphics"))
from probe import FIRST_SURFACE_SOURCE, verify_surface_modes

CURRENT = "1" * 64
ATTEMPT = "GRAPHICS_ATTEMPT generation=1 policy=preferred"
OFFER = "GRAPHICS_SURFACE generation=1 driver=example offered=[Fifo, Mailbox]"
READY = "GRAPHICS_READY generation=1"
CHOOSE = "GRAPHICS_PRESENT generation=1 mode=Mailbox driver=example desktop=Wayland"


class SurfaceModes(unittest.TestCase):
    def test_selection_follows_the_window_system_and_supported_modes(self):
        cases = [("wayland", OFFER, [CHOOSE], "Mailbox"), ("x11", OFFER, [], None),
                 ("wayland", OFFER.replace("Fifo, Mailbox", "Fifo"), [], None)]
        for backend, offer, choice, expected in cases:
            with self.subTest(backend=backend, offer=offer):
                value = verify_surface_modes([ATTEMPT, offer, READY, *choice], backend, ["IntegratedGpu"], CURRENT)
                self.assertEqual(value["generations"][0]["requested"], expected)

    def test_wrong_driver_generation_order_or_unoffered_mode_is_rejected(self):
        cases = [([ATTEMPT, OFFER, READY, CHOOSE.replace("example", "other")], "wayland"),
                 ([ATTEMPT, OFFER, READY, CHOOSE.replace("generation=1", "generation=2")], "wayland"),
                 ([ATTEMPT, READY, OFFER, CHOOSE], "wayland"),
                 ([ATTEMPT, OFFER.replace("Fifo, Mailbox", "Fifo"), READY, CHOOSE], "wayland"),
                 ([ATTEMPT, OFFER, READY, CHOOSE], "x11"),
                 ([ATTEMPT, OFFER, OFFER, READY, CHOOSE], "wayland")]
        for lines, backend in cases:
            with self.subTest(lines=lines, backend=backend), self.assertRaises(RuntimeError):
                verify_surface_modes(lines, backend, ["IntegratedGpu"], CURRENT)

    def test_missing_offer_cannot_select_the_historical_checker(self):
        lines = [ATTEMPT, READY, CHOOSE.replace("example", "llvmpipe")]
        self.assertEqual(verify_surface_modes(lines, "wayland", ["Cpu"], FIRST_SURFACE_SOURCE)
                         ["legacy_llvmpipe_requests"], 1)
        with self.assertRaises(RuntimeError):
            verify_surface_modes(lines, "wayland", ["Cpu"], CURRENT)


if __name__ == "__main__":
    unittest.main()
