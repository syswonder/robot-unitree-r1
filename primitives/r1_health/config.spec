specVersion: 1
description: R1 电池、关节、IMU、深度相机及音频服务的只读健康数据配置。
properties:
  network_interface:
    type: string
    default: eth10
    description: 已存在并连接机器人网络的非空 DDS 接口；示例 eth10。不会修改接口或运控模式。
  interval_s:
    type: number
    default: 0.5
    description: 健康数据流输出周期，单位秒，必须为有限正数；示例 0.5 对应 2 Hz。
  stale_after_s:
    type: number
    default: 2.0
    description: 关节反馈、最后有效 BMS 数据及深度帧的新鲜度上限，单位秒，必须为有限正数；示例 2.0。BMS 全零包不刷新有效样本时间。
