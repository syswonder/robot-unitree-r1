# R1 行走原语

通过 Unitree SDK2 的 `LocoClient.SetVelocity(vx, vy, omega, duration)`
调用 R1 官方高层运控。依赖机器人内置运控，非零速度需要 FSM 811
（走跑运控）；操作者使用官方遥控器或 App 切换模式。

官方文档：<https://support.unitree.com/home/zh/R1_developer/sport_services_interface>。

| 能力 | 传输 | 消息和行为 |
|---|---|---|
| `chassis/move` | MCP、gRPC RPC | `chassis/ExecuteMoveCommand`；按优先级执行 `forward_m`、`rotate_deg` 或限时速度，完成后归零 |
| `chassis/twist_in` | gRPC client stream | `geometry_msgs/Twist`；接收 `linear.x`、`linear.y`、`angular.z`，输入结束或取消后归零 |
| `robonix/lifecycle/driver` | gRPC | 初始化查询官方 FSM；关闭时发送零速度 |

能力路径前缀为 `robonix/primitive/`。两个运动入口互斥；全零
`move` 可以停止当前运动。`linear.z`、`angular.x`、`angular.y`
不受支持。距离和角度根据部署速度计算持续时间，属于开环近似量；
返回 `done` 代表限时指令结束且实际髋部或膝部变化达到 `0.1 rad`，
结果包含 `motion_observed`、`joint_motion_rad` 和 `native_return_codes`。
该检查确认腿部响应，位置和角度精度需要独立测量。

`move` 发送单条有限时长指令，执行期间检查 FSM、取消状态及关节
反馈，关节反馈按 20 Hz 读取最新数据，结束发送零速度；默认持续
五秒，最多十秒。进程异常时由官方
控制器在指令到期后结束输入。`twist_in` 每条指令默认有效 0.3 秒，
速度流需要持续更新，建议 10 Hz 以上；取消和关闭时主动发送零速度。
机器人保持原有模式。

本包依赖 SDK2、CycloneDDS 0.10.2、`robonix-api` 和机器人 DDS 网络。
构建脚本读取 `RBNX_OFFLINE_WHEELS` 安装已有离线依赖，使用 Python 3.10。

```bash
source ~/r1-robonix/env.sh
cd "$DEPLOY"
rbnx build -p primitives/r1_chassis --no-update-check
rbnx start -p primitives/r1_chassis --set network_interface=eth10
```

完整部署通过 `robonix_manifest.yaml` 启动本包。所有公开配置
及单位见 `config.spec`，速度和时间上限由部署配置定义；官方控制器
还会按自身允许范围处理输入。对话参数见 [CAPABILITY.md](CAPABILITY.md)。
零速度检查使用真实 gRPC 和官方 DDS，并将每条速度参数保存在
`rbnx-build/zero-velocity-result.json`：

```bash
cd "$DEPLOY/primitives/r1_chassis"
PYTHONPATH="$PWD:$PWD/rbnx-build/codegen/proto_gen" \
  .venv/bin/python tests/check_zero_velocity.py
```

本机 ai_sport `1.0.2.154` 已通过原生前进测试：
`SetVelocity(0.3, 0, 0, duration=5)` 能够迈步，运动和停止请求均
返回 `127`。本包对该接口接受 `0` 和 `127`，其他返回码报告失败；
结果保留原始返回码，运动结果还需通过关节反馈检查。前进默认速度
为 `0.3 m/s`，后退默认速度幅度为 `0.4 m/s`；负值 `forward_m`
通过 `backward_speed_m_s` 计算时间。平移速度模长上限为 `0.4 m/s`。
后退 `linear_x=-0.4`、五秒已确认迈步，最大腿部关节变化约
`0.60 rad`。侧向、旋转和实际位移精度仍需现场验收。
