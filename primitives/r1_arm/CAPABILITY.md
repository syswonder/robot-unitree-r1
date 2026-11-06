---
description: R1 双臂关节反馈、单关节及多关节同步运动，使用官方运控模式。
---

使用 `robonix/primitive/arm/move_joint` 执行单关节指令。
`joint_name` 必须使用以下完整 URDF 名称：

- 左臂：`left_shoulder_pitch_joint`、`left_shoulder_roll_joint`、
  `left_shoulder_yaw_joint`、`left_elbow_joint`、`left_wrist_roll_joint`。
- 右臂：`right_shoulder_pitch_joint`、`right_shoulder_roll_joint`、
  `right_shoulder_yaw_joint`、`right_elbow_joint`、`right_wrist_roll_joint`。

`target_rad` 是绝对关节角度，单位 rad。必须通过 `get_joint_states` 读取当前
位置，或使用操作者给出的明确绝对角度；不得猜测当前位置。`speed_rad_s`
必须显式提供，默认使用 0.05 rad/s。角度和速度必须满足官方 URDF 限制，
可通过 `get_joint_states` 读取。`move_joint` 一次接受一个关节；标准
`joint_command` 接受多个具名位置及同长度速度上限，拒绝 effort。

通过对话同时移动多个关节时，调用 `robonix/primitive/arm/move_joints`，
能力目录名称为 `r1_arm.arm_move_joints`。一次请求中同时提供
`joint_names`、`target_rad`、`speed_rad_s` 三个等长数组；名称非空且
不能重复。目标为绝对角度，速度为每个关节的正数上限，可在同一次
调用中包含左右双臂。使用 `get_joint_states` 读取当前位置和限位后
计算目标。全部目标共用五次轨迹的时间进度，并在同一 DDS 消息中发布，
统一接管和释放。返回的 `joint_name`、`start_rad`、`target_rad`、
`measured_rad`、`error_rad`、`actual_change_rad` 均为对应顺序的数组。
结果的 `duration_s` 为整组关节共同的轨迹和到位等待用时。

官方模式包括：0 零力矩、1 阻尼、4 锁定站立、811 走跑运控。
机械臂运动要求 FSM 811（走跑运控），由操作者通过官方遥控器或 App 切换。
锁定站立用于保持站立姿态。调试模式会退出内置运控，高层服务不可用。
`get_joint_states` 返回当前 FSM 和 `motion_fsm_ids`；模式不适用时报告当前模式。

每次动作包含控制权渐入、五次平滑插值、反馈验证和控制权渐出。
位置与速度前馈按 100 Hz 发布，起点和终点速度、加速度为零；轨迹
满足请求速度上限及部署的加速度、jerk 上限。
连续目标可通过同一 `joint_command` 流发送，整个流统一接管与释放。
独立 `move_joint` 调用各自完成接管、运动和释放。成功结果
包含运动期间的实测角度，动作完成后由 R1 内置控制器接管，姿态可能恢复。
执行失败时停止当前任务并向操作者报告错误，不重复尝试运动。
`measured_rad` 才是实测角度，`error_rad` 是实测角度减去目标角度，
`actual_change_rad` 是实测角度减去起点角度。必须按字段名称解释结果，
执行失败且没有足够实际变化时，不得宣称机械臂已经移动。
左右腕部位姿目标由 `r1_left_arm` 和 `r1_right_arm` 提供。
