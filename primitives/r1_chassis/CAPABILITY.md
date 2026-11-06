# R1 身体移动

`robonix/primitive/chassis/move` 提供 MCP 和 gRPC 接口，直接调用
官方 `SetVelocity()`。运动需要 FSM 811，可通过 `r1_state` 查询。

请求包含标准 `command`：

- `linear_x`、`linear_y`：身体前向、侧向速度，单位 m/s。
- `angular_z`：旋转速度，单位 rad/s。
- `duration_sec`：持续秒数，零值使用五秒默认值。
- `forward_m`：有符号前进距离，单位米。
- `rotate_deg`：有符号旋转角度，单位度，正值表示逆时针。
- `linear_z`、`angular_x`、`angular_y`：填写零值。

前进已验证的参数为 `linear_x=0.3`、`duration_sec=5`，其余字段为零。
后退已验证的参数为 `linear_x=-0.4`、`duration_sec=5`，其余字段为零。
平移速度上限为 `0.4 m/s`，角速度上限为 `0.5 rad/s`，单次最多十秒。
全零速度请求发送停止指令。侧向和旋转等待现场运动验收。

参数优先级为 `forward_m`、`rotate_deg`、速度。距离和角度通过
部署速度计算时间，属于开环近似量；不能承诺精确位移。
`forward_m` 为正使用 `0.3 m/s`，为负使用 `-0.4 m/s`。

`done` 表示指令结束并检测到腿部响应；`joint_motion_rad` 是实际
髋部或膝部最大角度变化，`native_return_codes` 保留官方原始返回码。
本机 ai_sport 1.0.2.154 的原生运动和停止请求返回 `127`，已通过
实际迈步测试。关节反馈超时、模式改变或运动反馈不足均报告失败。
