# R1 dual-arm primitive

Controls both arms on the official `rt/arm_sdk` channel. The standard `robonix/primitive/arm/joint_states` stream reports angle, angular velocity and estimated torque for ten named joints. The standard `joint_command` accepts absolute positions for several named joints in one message. Names must be unique, and `position` must have the same length as `name`. `velocity` may be empty or a same-length list of positive speed limits in rad/s. An empty list uses 0.05 rad/s per joint. `effort` must be empty. `move_joint` is the MCP and gRPC call for one joint. `move_joints` is the synchronized multi-joint call. Its dialogue name is `r1_arm.arm_move_joints`. It takes three equal-length arrays, `joint_names`, `target_rad` and `speed_rad_s`: URDF names, absolute angles and positive speed limits. Names are non-empty and unique. Every target is validated before motion starts. One call may include both arms.

Joint feedback uses the DDS receive time. `header.frame_id` is `waist_yaw_link`. A multi-joint command uses one shared duration so the joints arrive together. The standard wrist pose interfaces are in [r1_arm_pose](../r1_arm_pose/README.md). Joint output always goes through this package.

R1 ArmSdk takes over both arms, waist yaw and the head: thirteen joints. Joints not named in the command hold the position they had when control was taken. The rest of the body stays with the built-in controller. Each command publishes at 100 Hz on its own thread against absolute time. Take-over and release each last one second and use a quintic blend. Feedback timeout or cancel releases control. Messages use the SDK `LowCmd_` layout and CRC, on the fixed topic `rt/arm_sdk`.

`mode_machine` is the feedback value from the start of the motion. The thirteen managed joints use `motor_cmd[].mode` 1 and `tau` zero. The trajectory writes both position `q` and velocity feedforward `dq`. Velocity and acceleration are zero at both ends. Other motor commands stay at their defaults and are not driven on this channel.

The trajectory respects the requested speed limit and the deployment limits of `0.5 rad/s^2` acceleration and `2.0 rad/s^3` jerk. See `config.spec`. Feedback is read at about 100 Hz. The next target starts as soon as the joint is within 0.02 rad, with at most 0.5 s of extra wait.

One `joint_command` stream takes and releases control once, and keeps publishing the current target while waiting for the next one. A continuous wrist `pos_command` stream uses that same joint stream. Standalone `move_joint`, `move_joints` and `move_pose` calls each take, move and release. `duration_s` is the trajectory plus the settle wait.

`move_joints` calls `ArmController.move_joints()` directly. The group shares one trajectory duration. One `LowCmd_` frame carries the whole group's position and velocity feedforward. Each joint returns its measured change and settle error. A client may ask: "Read the current joint positions, then move both wrists by +0.05 rad once, with a 0.05 rad/s speed limit."

## Build and start

On the R1:

```bash
source ~/r1-robonix/env.sh
cd ~/r1-robonix/robot-unitree-r1
rbnx validate primitives/r1_arm
rbnx build -p primitives/r1_arm --no-update-check
```

The package uses the vendored Unitree SDK2 Python, CycloneDDS 0.10.2 and the Robonix API. The build script uses the offline wheels from the deployment. The full manifest starts the primitive. At start it only subscribes to feedback and sends no motion command.

## Modes and commands

Official modes are 0 zero torque, 1 damping, 4 locked stand and 811 walk-run. Arm motion uses FSM 811, which has been checked on the robot. The operator selects it with the official remote or app. Debug mode leaves the built-in controller, and the high-level services are then unavailable. Locked stand has no balance control.

On the R1:

```bash
~/r1-robonix/scripts/r1_arm.sh status
~/r1-robonix/scripts/r1_arm.sh move right_wrist_roll_joint 0.05 --speed 0.05
```

The `0.05` in the example is an absolute angle. Read `status` before choosing a target. `status` returns the current FSM, `motion_fsm_ids: [811]`, both arm angles, and the official URDF angle and speed limits. A client may say: "Read the right wrist angle, then add 0.05 rad once at 0.05 rad/s." Angle and speed are checked against the official URDF.

Cancel and Driver shutdown interrupt the motion and release control. SIGKILL or a power loss cannot run that cleanup, so the hardware e-stop must stay available.

`tests/test_motion.py` checks the trajectory numbers. On 2026-10-23 a real DDS check on domain 77 sent and received 451 messages, all with a valid CRC. The mean receive interval was about 10.00 ms, the 95th percentile about 10.27 ms, and the maximum about 12.06 ms. That check kept the weight at zero. It only checked the software trajectory and the transport timing.

On 2026-10-26, in FSM 811, a single left-wrist MCP move and three consecutive targets on one `joint_command` stream were checked. The single move changed `0.117138 rad` with error `-0.003862 rad`. The largest settle error of the consecutive targets was about `0.01037 rad`. During motion the 95th percentile command interval was about `10.79 ms` and `10.89 ms`, and the maxima about `16.44 ms` and `22.67 ms`. Every CRC was valid. The continuous stream kept one control session, and the weight was zero afterwards. The record is `.tools/arm-smoothing/live-motion-result.json` on the robot.

The same day one `move_joints` MCP call moved both wrists together: left `+0.06 rad`, right `+0.08 rad`, both limited to `0.05 rad/s`. Measured changes were `+0.046988 rad` and `+0.073782 rad`, with settle errors `-0.013905 rad` and `-0.007292 rad`. Both commands shared one time base. The maximum command interval was about `18.80 ms`. Every CRC was valid, and the weight was zero afterwards. The client dialogue selected the new tool and its three array arguments. The record is `.tools/arm-multi-joint/live-sync-result.json` on the robot.

Motion and settle-failure messages list `joint_name`, `start_rad`, `target_rad`, `measured_rad`, `error_rad` and `actual_change_rad` per joint. `measured_rad` is the measured angle, `error_rad = measured_rad - target_rad`, and `actual_change_rad = measured_rad - start_rad`. Use the measured change to decide whether the arm moved. Do not read the target error as the measured angle.

On 2026-10-23, in FSM 811, the main deployment gRPC path commanded the right wrist by +0.12 rad at 0.05 rad/s. The target was 0.118426 rad, the measurement 0.116789 rad, and the error -0.001636 rad. Settle feedback was taken before control ramped out. The built-in controller then took over. Standard multi-joint and wrist-pose commands share the same FSM check and actuator.

Official references:
[R1 high-level sport services](https://support.unitree.com/home/zh/R1_developer/sport_services_interface),
[R1 ArmSdk example](https://github.com/unitreerobotics/unitree_sdk2/blob/main/example/r1/high_level/r1_arm_sdk_dds_example.cpp),
[R1 Python teleoperation](https://github.com/unitreerobotics/xr_teleoperate/blob/main/teleop/robot_control/robot_arm.py),
[R1 joint indices](https://github.com/unitreerobotics/unitree_sdk2/blob/main/include/unitree/dds_wrapper/robots/r1/defines.h).
