# R1 腕部位姿接口

同一软件包通过 `side` 配置注册 `r1_left_arm` 和 `r1_right_arm`。
各实例提供标准 gRPC `arm/end_pose` 与 `arm/pos_command`，消息为
`geometry_msgs/Pose`。位置单位米，姿态为 x,y,z,w 归一化四元数。
两条接口均以 `waist_yaw_link` 为参考坐标系；末端分别是官方 URDF 的
`left_wrist_roll_link` 和 `right_wrist_roll_link`，对应腕部连接，不含工具安装变换。

`end_pose` 订阅 `r1_arm/joint_states`，通过 IKPy 计算正运动学。
`pos_command` 使用 IKPy 和官方 URDF 求解完整位姿，关节角度遵循
URDF 限位。R1 每臂五个自由度；求解后的位置残差必须不超过 0.0001 m、
姿态残差不超过 0.001 rad，否则拒绝发送运动指令。
这些数值是模型求解的收敛判据；实际关节到位判据由 `r1_arm` 检查，
每关节绝对误差不超过 0.02 rad，不能解释为末端实际定位精度。

目标关节角度通过标准 `r1_arm/joint_command` 发送，由 `r1_arm`
统一执行五次同步关节插值、速度前馈、FSM 检查和并发互斥。
同一 `pos_command` 流共用一条关节指令流和一次接管、释放过程；
后续 IK 目标使用前一个已求解目标作为求解起点。
运动要求操作者通过官方遥控器或 App 进入 FSM 811（走跑运控）。
末端路径不保证直线，也未提供碰撞规划。完成后释放控制权，内置控制器
可能恢复姿态。`pos_command` 的关节速度由 `speed_rad_s` 配置，默认
0.05 rad/s，URDF 速度限制仍由 `r1_arm` 检查。

提供 MCP 和 gRPC 便利调用：

- `get_end_pose`：返回 `frame_id`、`tip_link`、`position_m`、`quaternion_xyzw`。
- `move_pose`：参数 `x,y,z,qx,qy,qz,qw,speed_rad_s`；位置、姿态为绝对目标。

Client 指令示例：“调用 r1_right_arm 的 get_end_pose，报告右腕位姿。”
运动指令必须明确 provider、参考坐标系、目标位置、完整姿态和关节速度。
目标需要满足五自由度模型；不得根据文字猜测工具变换或当前位置。
启动和读取均不发送运动指令，shutdown 关闭上游 gRPC 调用。

在 R1 上构建：

```bash
source ~/r1-robonix/env.sh
cd ~/r1-robonix/robot-unitree-r1
rbnx build -p primitives/r1_arm_pose --no-update-check
```

依赖 IKPy 3.4.2、SciPy 1.15.3、NumPy 2.2.6 和 Robonix API。
官方关节控制依据：
[R1 ArmSdk 示例](https://github.com/unitreerobotics/unitree_sdk2/blob/main/example/r1/high_level/r1_arm_sdk_dds_example.cpp)。
末端运动学由此软件包基于官方 URDF 计算。
