import unittest

from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowCmd_
from r1_arm.motion import apply_trajectory, smooth_step, trajectory_duration


class MotionTests(unittest.TestCase):
    def test_endpoint_position_velocity_and_acceleration(self):
        self.assertEqual(smooth_step(-1), (0, 0))
        self.assertEqual(smooth_step(2), (1, 0))
        self.assertEqual(smooth_step(0), (0, 0))
        self.assertEqual(smooth_step(1), (1, 0))
        epsilon = 1e-6
        self.assertLess(smooth_step(epsilon)[1] / epsilon, 0.001)
        self.assertLess(smooth_step(1 - epsilon)[1] / epsilon, 0.001)

    def test_velocity_feedforward_matches_position(self):
        command = unitree_hg_msg_dds__LowCmd_()
        duration = 2.0
        elapsed = 0.7
        epsilon = 1e-5
        apply_trajectory(command, [15], [0.1], [-0.3], elapsed - epsilon, duration)
        before = command.motor_cmd[15].q
        apply_trajectory(command, [15], [0.1], [-0.3], elapsed + epsilon, duration)
        after = command.motor_cmd[15].q
        apply_trajectory(command, [15], [0.1], [-0.3], elapsed, duration)
        self.assertAlmostEqual(command.motor_cmd[15].dq, (after - before) / (2 * epsilon), places=8)

    def test_synchronized_trajectory_limits(self):
        starts = [0.1, -0.2, 0.3]
        targets = [-0.2, 0.0, 0.3]
        speeds = [0.12, 0.08, 0.05]
        acceleration = 0.5
        jerk = 2.0
        duration = trajectory_duration(starts, targets, speeds, acceleration, jerk)
        step = duration / 2000
        command = unitree_hg_msg_dds__LowCmd_()
        positions = []
        for tick in range(2001):
            apply_trajectory(command, [15, 16, 17], starts, targets, tick * step, duration)
            positions.append([command.motor_cmd[index].q for index in (15, 16, 17)])
        for joint in range(3):
            values = [value[joint] for value in positions]
            velocities = [(b - a) / step for a, b in zip(values, values[1:])]
            accelerations = [(b - a) / step for a, b in zip(velocities, velocities[1:])]
            jerks = [(b - a) / step for a, b in zip(accelerations, accelerations[1:])]
            self.assertLessEqual(max(map(abs, velocities)), speeds[joint] + 1e-8)
            self.assertLessEqual(max(map(abs, accelerations)), acceleration + 1e-6)
            self.assertLessEqual(max(map(abs, jerks)), jerk + 1e-4)
            self.assertAlmostEqual(values[0], starts[joint])
            self.assertAlmostEqual(values[-1], targets[joint])
            self.assertEqual(command.motor_cmd[(15, 16, 17)[joint]].dq, 0)

    def test_stationary_target(self):
        command = unitree_hg_msg_dds__LowCmd_()
        duration = trajectory_duration([0.2], [0.2], [0.05], 0.5, 2.0)
        apply_trajectory(command, [26], [0.2], [0.2], duration / 2, duration)
        self.assertEqual((command.motor_cmd[26].q, command.motor_cmd[26].dq), (0.2, 0))


if __name__ == "__main__":
    unittest.main()
