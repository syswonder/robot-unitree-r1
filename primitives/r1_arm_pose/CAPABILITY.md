---
description: Wrist pose feedback and full pose goals for one R1 arm, in the waist_yaw_link frame.
---

Instance `r1_left_arm` uses `left_wrist_roll_link`. Instance `r1_right_arm` uses `right_wrist_roll_link`. Call `get_end_pose` for the current pose. `position_m` is in metres. `quaternion_xyzw` is an x,y,z,w quaternion.

`move_pose` arguments `x,y,z` are an absolute position in `waist_yaw_link`. `qx,qy,qz,qw` must be a normalized quaternion. `speed_rad_s` is the joint speed limit. Motion requires official FSM 811 (walk-run) and stays inside the official URDF angle and speed limits. The five-degree-of-freedom arm accepts only targets whose full pose solves. A failed solve is reported as an error. Do not retry the motion or drop the target orientation. There is no tool mount and no collision planner.

Execution uses a synchronized quintic joint interpolation and velocity feedforward. The tip path is not promised to be straight. One standard `pos_command` stream takes and releases control once. A standalone `move_pose` call runs the full motion itself. Success returns the model joint targets and the IK residuals. Those residuals describe the solver, not the measured tip. `r1_arm` checks the joint feedback. Control is released after the motion, and the built-in controller may restore the pose.
