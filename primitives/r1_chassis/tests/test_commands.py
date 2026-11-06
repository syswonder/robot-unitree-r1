import math
import unittest

import chassis_pb2
from r1_chassis.controller import plan_command, settings, validate_velocity


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.config = settings({})

    def test_distance_and_angle_priority(self):
        velocity, duration, mode = plan_command(
            chassis_pb2.MoveCommand(forward_m=-0.4, rotate_deg=90, linear_x=0.2), self.config)
        self.assertEqual((velocity, duration, mode), ((-0.4, 0.0, 0.0), 1.0, "forward_m"))
        self.assertEqual(plan_command(chassis_pb2.MoveCommand(forward_m=0.3), self.config),
                         ((0.3, 0.0, 0.0), 1.0, "forward_m"))
        velocity, duration, mode = plan_command(
            chassis_pb2.MoveCommand(rotate_deg=math.degrees(-0.3)), self.config)
        self.assertEqual(velocity, (0.0, 0.0, -0.3))
        self.assertAlmostEqual(duration, 1.0)
        self.assertEqual(mode, "rotate_deg")

    def test_velocity_duration_and_zero(self):
        self.assertEqual(plan_command(chassis_pb2.MoveCommand(), self.config),
                         ((0.0, 0.0, 0.0), 5.0, "velocity"))
        self.assertEqual(plan_command(chassis_pb2.MoveCommand(linear_y=-0.1, duration_sec=2), self.config),
                         ((0.0, -0.1, 0.0), 2.0, "velocity"))
        self.assertEqual(plan_command(chassis_pb2.MoveCommand(linear_x=-0.4, duration_sec=5), self.config),
                         ((-0.4, 0.0, 0.0), 5.0, "velocity"))

    def test_invalid_motion_inputs(self):
        for values in ({"linear_x": float("nan")}, {"angular_z": float("inf")},
                       {"duration_sec": -1}, {"duration_sec": 11}, {"forward_m": 100},
                       {"linear_z": 0.1}, {"angular_x": 0.1}, {"angular_y": 0.1},
                       {"linear_x": 0.3, "linear_y": 0.3}, {"angular_z": 0.6}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                plan_command(chassis_pb2.MoveCommand(**values), self.config)
        with self.assertRaises(ValueError):
            validate_velocity((0.3, 0.3, 0), self.config)

    def test_invalid_settings(self):
        for values in ({"command_timeout_s": 0}, {"command_timeout_s": 1.1},
                       {"max_duration_s": 0.1}, {"linear_speed_m_s": 1},
                       {"backward_speed_m_s": 1}, {"angular_speed_rad_s": 1},
                       {"default_duration_s": float("nan")}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                settings(values)


if __name__ == "__main__":
    unittest.main()
