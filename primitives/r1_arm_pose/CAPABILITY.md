---
description: 单个 R1 机械臂的腕部位姿反馈和完整位姿目标，参考坐标系 waist_yaw_link。
---

实例 `r1_left_arm` 对应 `left_wrist_roll_link`；实例 `r1_right_arm`
对应 `right_wrist_roll_link`。调用 `get_end_pose` 获取当前位姿。
`position_m` 为米，`quaternion_xyzw` 为 x,y,z,w 四元数。

`move_pose` 参数 `x,y,z` 为参考坐标系 `waist_yaw_link` 中的绝对位置，
`qx,qy,qz,qw` 必须为归一化四元数，`speed_rad_s` 为关节速度上限。
运动需要官方 FSM 811（走跑运控），并遵循官方 URDF 的角度及速度限制。
五自由度机械臂仅接受完整位姿求解成功的目标；失败时报告错误，
不得重复尝试运动或忽略目标姿态。没有工具安装变换及碰撞规划。

实际执行使用五次同步关节插值和速度前馈，末端路径不保证直线。
同一标准 `pos_command` 流统一接管与释放；独立 `move_pose` 调用各自
执行完整动作。成功返回模型关节目标和
IK 残差；这些残差描述模型求解结果。实际关节反馈由 `r1_arm` 检查，
运动完成后释放控制权，内置控制器可能恢复姿态。
