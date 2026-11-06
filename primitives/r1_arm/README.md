# R1 双臂原语

使用 R1 官方 `rt/arm_sdk` 通道控制双臂。以标准
`robonix/primitive/arm/joint_states` 输出十个具名关节的角度、角速度和
估计力矩；标准 `joint_command` 接受一条消息中多个具名关节的绝对位置，
名称不能重复，`position` 长度必须与 `name` 相同。
`velocity` 可为空或与 `name` 相同长度的正速度上限，单位 rad/s；
为空时各关节使用 0.05 rad/s；`effort` 必须为空。
`move_joint` 提供 MCP 和 gRPC 单关节调用；`move_joints` 提供 MCP 和
gRPC 多关节同步调用，对话目录中的名称为 `r1_arm.arm_move_joints`。
`move_joints` 接收 `joint_names`、`target_rad`、`speed_rad_s` 三个等长
数组，分别为 URDF 名称、绝对角度和正速度上限。名称非空且不能重复，
所有目标统一校验后执行，可在同一次调用中包含左右双臂。

关节反馈使用 DDS 接收时间，`header.frame_id` 为 `waist_yaw_link`。
多关节指令采用统一运动时间，各关节同步到达目标。左右腕部标准位姿
接口由 [r1_arm_pose](../r1_arm_pose/README.md) 提供，关节输出统一经过此包。

R1 ArmSdk 接管双臂、waist yaw 和头部共十三个关节；未选中的关节目标
保持接管前的位置。全身其他关节继续由内置控制器管理。每次指令使用
独立线程按绝对时间周期以 100 Hz 发布，接管和释放各一秒，采用五次
平滑插值。反馈超时、取消后释放控制权。消息使用 SDK 的 `LowCmd_` 和 CRC 计算，
发布话题固定为 `rt/arm_sdk`。

指令的 `mode_machine` 使用本次运动起始反馈值；十三个受管关节的
`motor_cmd[].mode` 为 1，`tau` 为零；轨迹同时生成位置 `q` 和速度
前馈 `dq`，起点、终点的速度与加速度均为零。
其他关节的电机指令保持默认值，不通过此通道控制。

轨迹同时满足请求速度上限、部署加速度上限 `0.5 rad/s²` 和 jerk
上限 `2.0 rad/s³`。参数见 `config.spec`，属于部署设置。
关节反馈按约 100 Hz 读取最新数据。到位后立即推进下一目标，
到位误差上限为 0.02 rad，最长额外等待 0.5 秒。

同一 `joint_command` 流统一接管和释放，等待下一目标期间持续发布
当前目标。连续腕部 `pos_command` 流经同一关节流执行。独立的
`move_joint`、`move_joints` 和 `move_pose` 调用各自执行完整的接管、运动和释放。
`duration_s` 记录该段轨迹及到位等待用时。

`move_joints` 直接使用 `ArmController.move_joints()`。整组关节共用
轨迹时长，同一帧 `LowCmd_` 包含整组位置及速度前馈，逐关节返回实际
变化和到位误差。Client 中可以请求：“读取当前关节位置，然后同时将
左右手腕增加 0.05 rad，速度上限均为 0.05 rad/s，只执行一次。”

## 构建和启动

在 R1 上执行：

```bash
source ~/r1-robonix/env.sh
cd ~/r1-robonix/robot-unitree-r1
rbnx validate primitives/r1_arm
rbnx build -p primitives/r1_arm --no-update-check
```

此包依赖现有 Unitree SDK2 Python、CycloneDDS 0.10.2 和 Robonix API。
构建脚本使用部署提供的离线 wheels。整机清单负责启动原语；启动时只
订阅反馈，不发送运动指令。

## 模式和指令

官方模式为 0 零力矩、1 阻尼、4 锁定站立、811 走跑运控。
机械臂运动使用已完成真机到位检查的 FSM 811，由操作者通过官方遥控器
或 App 切换。调试模式会退出内置运控，高层服务不可用。
锁定站立模式没有平衡控制。

在 R1 终端执行：

```bash
~/r1-robonix/scripts/r1_arm.sh status
~/r1-robonix/scripts/r1_arm.sh move right_wrist_roll_joint 0.05 --speed 0.05
```

示例中的 0.05 是绝对角度，执行前必须根据 status 反馈确定目标。
`status` 返回当前 FSM、`motion_fsm_ids: [811]`、双臂角度和官方
URDF 的角度、速度限制。
Client 可直接接受：“读取右手腕当前角度，然后增加 0.05 rad，速度
0.05 rad/s，只执行一次。”角度和速度按官方 URDF 校验。

取消和 Driver shutdown 会中断动作并释放控制权；进程被 SIGKILL 或
计算机断电时无法执行软件清理，现场硬件急停必须保持可用。

轨迹数值检查见 `tests/test_motion.py`。2026-10-23 板端独立 DDS
domain 77 的真实传输检查发送和接收均为 451 条，全部 CRC 有效；
平均接收间隔约 10.00 ms，95% 分位约 10.27 ms，最大约 12.06 ms。
该检查权重始终为零，用于验证软件轨迹和传输时序。

2026-10-26 在 FSM 811 完成左腕 MCP 单次及同一 `joint_command` 流的
三个连续目标检查。单次实际变化 `0.117138 rad`，误差
`-0.003862 rad`；连续目标的最大到位误差约 `0.01037 rad`。
运动期间指令间隔 95% 分位分别约 `10.79 ms`、`10.89 ms`，
最大分别约 `16.44 ms`、`22.67 ms`；全部 CRC 有效，连续流保持
同一控制会话，完成后均确认权重为零。完整记录在板端
`.tools/arm-smoothing/live-motion-result.json`。

同日通过 `move_joints` 的一次 MCP 调用执行双腕同步目标，左腕相对
`+0.06 rad`、右腕相对 `+0.08 rad`，速度上限均为 `0.05 rad/s`。
实测变化分别为 `+0.046988 rad`、`+0.073782 rad`，到位误差分别为
`-0.013905 rad`、`-0.007292 rad`。两路指令共用同一时间进度，
最大指令间隔约 `18.80 ms`，全部 CRC 有效，完成后确认权重为零。
Client 对话已正确识别新工具及三个数组参数。完整记录在板端
`.tools/arm-multi-joint/live-sync-result.json`。

运动结果和到位失败的信息逐个列出 `joint_name`、`start_rad`、`target_rad`、
`measured_rad`、`error_rad` 和 `actual_change_rad`。其中 `measured_rad`
为实测角度，`error_rad = measured_rad - target_rad`，
`actual_change_rad = measured_rad - start_rad`；判断是否运动需要使用
实测变化，不能把目标误差解释为实测角度。

2026-10-23 在 FSM 811 通过主部署 gRPC 执行右腕 +0.12 rad 指令，
速度 0.05 rad/s；目标 0.118426 rad，实测 0.116789 rad，误差
-0.001636 rad。到位反馈在控制权渐出前采集；指令结束后由内置
控制器接管。标准多关节及腕部位姿指令共用相同的 FSM 检查和执行器。

官方依据：
[R1 高层运动服务接口](https://support.unitree.com/home/zh/R1_developer/sport_services_interface)、
[R1 ArmSdk 示例](https://github.com/unitreerobotics/unitree_sdk2/blob/main/example/r1/high_level/r1_arm_sdk_dds_example.cpp)、
[R1 Python 遥操作实现](https://github.com/unitreerobotics/xr_teleoperate/blob/main/teleop/robot_control/robot_arm.py)、
[R1 关节编号](https://github.com/unitreerobotics/unitree_sdk2/blob/main/include/unitree/dds_wrapper/robots/r1/defines.h)。
