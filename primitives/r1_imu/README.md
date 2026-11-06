# R1 IMU interface

Subscribes to official `rt/lowstate` `unitree_hg/LowState_` and maps `imu_state` to a gRPC `sensor_msgs/Imu` stream on `robonix/primitive/imu/imu`. `quaternion` is converted from w,x,y,z. Angular velocity is rad/s and linear acceleration is m/s^2, including the device gravity component. The device does not provide covariance, so the three covariance arrays are zero, which is the ROS convention for unknown.

The stamp is the time the R1 host received the DDS sample. The frame is the official URDF frame `imu_in_pelvis_link`. Each subscriber receives only new samples. A slow consumer gets the latest sample. Missing or timed-out data returns `UNAVAILABLE`. Shutdown stops the subscription. The interface only reads the device.

Build from the deployment directory with `rbnx build -p primitives/r1_imu`. The full manifest sets `network_interface: eth10`. The build and start scripts manage the process. Public settings are in `config.spec`.

Sources: [Unitree R1 developer guide](https://support.unitree.com/home/zh/R1_developer), [official IMU message](https://github.com/unitreerobotics/unitree_ros2/blob/master/cyclonedds_ws/src/unitree/unitree_hg/msg/IMUState.msg).
