# R1 wrist pose interface

One package registers `r1_left_arm` and `r1_right_arm` through the `side` setting. Each instance serves standard gRPC `arm/end_pose` and `arm/pos_command` with `geometry_msgs/Pose`. Position is in metres. Orientation is a normalized x,y,z,w quaternion. Both interfaces use `waist_yaw_link` as the reference frame. The tips are the official URDF links `left_wrist_roll_link` and `right_wrist_roll_link`, the wrist joints, with no tool mount.

`end_pose` subscribes to `r1_arm/joint_states` and computes forward kinematics with IKPy. `pos_command` solves a full pose with IKPy and the official URDF, inside the URDF joint limits. Each R1 arm has five degrees of freedom. The solved position residual must be at most 0.0001 m and the orientation residual at most 0.001 rad, or no motion command is sent. Those numbers are solver convergence limits. The joint settle check is in `r1_arm`: 0.02 rad absolute error per joint. They are not a measured end-effector accuracy.

Target joint angles are sent on the standard `r1_arm/joint_command`. `r1_arm` runs the synchronized quintic interpolation, velocity feedforward, FSM check and mutual exclusion. One `pos_command` stream shares one joint-command stream and one take-over and release. Later IK targets start from the previous solved target. Motion requires the operator to select FSM 811 (walk-run) with the official remote or app. The tip path is not promised to be a straight line, and there is no collision planner. Control is released when the call finishes, and the built-in controller may restore the pose. The `pos_command` joint speed comes from `speed_rad_s`, default 0.05 rad/s. `r1_arm` still enforces the URDF speed limits.

Convenience calls over MCP and gRPC:

- `get_end_pose`: returns `frame_id`, `tip_link`, `position_m` and `quaternion_xyzw`.
- `move_pose`: arguments `x,y,z,qx,qy,qz,qw,speed_rad_s`. Position and orientation are absolute targets.

A client example: "Call get_end_pose on r1_right_arm and report the right wrist pose." A motion request must name the provider, reference frame, target position, full orientation and joint speed. The target must be solvable by the five-degree-of-freedom model. Do not guess a tool transform or the current pose from the wording. Startup and reads send no motion command. Shutdown closes the upstream gRPC calls.

Build on the R1:

```bash
source ~/r1-robonix/env.sh
cd ~/r1-robonix/robot-unitree-r1
rbnx build -p primitives/r1_arm_pose --no-update-check
```

Depends on IKPy 3.4.2, SciPy 1.15.3, NumPy 2.2.6 and the Robonix API. Official joint-control reference: [R1 ArmSdk example](https://github.com/unitreerobotics/unitree_sdk2/blob/main/example/r1/high_level/r1_arm_sdk_dds_example.cpp). This package computes the tip kinematics from the official URDF.
