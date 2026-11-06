---
description: R1 dual-arm joint feedback, plus single-joint and synchronized multi-joint motion, using the official sport mode.
---

Use `robonix/primitive/arm/move_joint` for one joint.
`joint_name` must be one of these URDF names:

- Left arm: `left_shoulder_pitch_joint`, `left_shoulder_roll_joint`, `left_shoulder_yaw_joint`, `left_elbow_joint`, `left_wrist_roll_joint`.
- Right arm: `right_shoulder_pitch_joint`, `right_shoulder_roll_joint`, `right_shoulder_yaw_joint`, `right_elbow_joint`, `right_wrist_roll_joint`.

`target_rad` is an absolute joint angle in radians. Read the current position with `get_joint_states`, or use an absolute angle the operator stated. Do not guess the current position. `speed_rad_s` must be set explicitly; 0.05 rad/s is the usual value. Angle and speed must stay inside the official URDF limits, which `get_joint_states` also returns. `move_joint` accepts one joint. The standard `joint_command` accepts several named positions and a velocity limit of the same length, and rejects effort.

To move several joints from one dialogue turn, call `robonix/primitive/arm/move_joints`. Its catalog name is `r1_arm.arm_move_joints`. One request supplies three equal-length arrays: `joint_names`, `target_rad` and `speed_rad_s`. Names are non-empty and unique. Targets are absolute angles. Speeds are positive per-joint limits. One call may include both arms. Read the current pose and limits with `get_joint_states` before computing targets. Every target shares one quintic time base and is published in the same DDS message, with one take-over and one release. The result arrays `joint_name`, `start_rad`, `target_rad`, `measured_rad`, `error_rad` and `actual_change_rad` keep that order. `duration_s` is the shared trajectory and settle time.

Official modes: 0 zero torque, 1 damping, 4 locked stand, 811 walk-run. Arm motion requires FSM 811, selected by the operator with the official remote or app. Locked stand holds a standing pose. Debug mode leaves the built-in controller, and the high-level services are then unavailable. `get_joint_states` returns the current FSM and `motion_fsm_ids`. A wrong mode is reported as the current mode.

Each motion ramps control in, runs a quintic interpolation, checks feedback, and ramps control out. Position and velocity feedforward are published at 100 Hz. Start and end velocity and acceleration are zero. The trajectory respects the requested speed and the deployment acceleration and jerk limits. Consecutive targets may share one `joint_command` stream, which takes and releases control once. A standalone `move_joint` call takes, moves and releases on its own. A success result includes the measured angle during the motion. After the call, the built-in controller owns the arms again and the pose may return. On failure, stop and report the error. Do not retry the motion. `measured_rad` is the measured angle, `error_rad` is measured minus target, and `actual_change_rad` is measured minus start. Interpret the fields by name. Do not claim the arm moved when execution failed and the measured change is too small. Wrist pose goals are provided by `r1_left_arm` and `r1_right_arm`.
