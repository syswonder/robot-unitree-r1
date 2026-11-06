from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from watch_robot_reboot import RebootDetector


class RebootTests(unittest.TestCase):
    def test_regular_counter_and_small_reordering(self):
        detector = RebootDetector()
        self.assertIsNone(detector.observe(10000, 0))
        self.assertIsNone(detector.observe(10500, 0.5))
        self.assertIsNone(detector.observe(10498, 0.6))
        self.assertIsNone(detector.observe(11000, 1.0))

    def test_counter_reset(self):
        detector = RebootDetector()
        detector.observe(500000, 0)
        self.assertEqual(detector.observe(2000, 0.5), "robot_tick_reset")
        self.assertIsNone(detector.observe(2500, 1.0))

    def test_reconnection(self):
        detector = RebootDetector()
        detector.observe(500000, 0)
        self.assertEqual(detector.observe(501000, 5), "robot_reconnected")
        self.assertIsNone(detector.observe(501500, 5.5))

    def test_counter_wrap(self):
        detector = RebootDetector()
        detector.observe((1 << 32) - 200, 0)
        self.assertIsNone(detector.observe(300, 0.5))


if __name__ == "__main__":
    unittest.main()
