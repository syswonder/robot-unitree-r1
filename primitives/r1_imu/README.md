# R1 IMU 标准接口

订阅官方 `rt/lowstate` 的 `unitree_hg/LowState_`，将 `imu_state` 映射为
`robonix/primitive/imu/imu` 的 gRPC `sensor_msgs/Imu` 流。
`quaternion` 按 w,x,y,z 转换，角速度为 rad/s，加速度为 m/s²，保留设备重力分量。
设备没有提供协方差，三个协方差数组按 ROS 约定填零表示未知。

消息时间戳为 R1 主机接收 DDS 样本的时间，frame 为官方 URDF 的
`imu_in_pelvis_link`。每个订阅者只接收新样本，慢消费者使用最新样本；
缺少数据或超时返回 `UNAVAILABLE`，关闭时停止订阅。接口只读取设备。

从部署目录执行 `rbnx build -p primitives/r1_imu`；整机清单配置
`network_interface: eth10`，由构建和启动脚本统一管理。
公开配置见 `config.spec`。

来源：[宇树 R1 开发指南](https://support.unitree.com/home/zh/R1_developer)、
[官方 IMU 消息定义](https://github.com/unitreerobotics/unitree_ros2/blob/master/cyclonedds_ws/src/unitree/unitree_hg/msg/IMUState.msg)。
