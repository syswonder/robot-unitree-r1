# R1 视觉动作决策服务

通过 Atlas 获取 R1 的 RGB、CameraInfo、深度和状态，将同一观察提交给
PC Decider-4B。`direct_image` 使用原生图片，`visual_text` 使用 BLIP/RAM
描述。模型返回左转、前进、右转、停止四项候选的概率。

## 部署

R1 需要 Python 3.10、现有 Robonix API、相机和状态原语。板端不安装
PyTorch 或模型权重。构建入口支持 `RBNX_OFFLINE_WHEELS` 指向现有
离线 wheel 目录。公开配置见 `config.spec`，调用说明见 `CAPABILITY.md`。

```bash
source ~/r1-robonix/scripts/env.sh
rbnx build -p "$DEPLOY/services/visual_action_decider"
bash ~/r1-robonix/scripts/02_start.sh
```

主清单已注册该服务。当前模型 revision 为
`585473dec4fa93f0325c2bf02dda7273b61f44c1`，PC 端口 18080/18081
通过反向隧道供 R1 访问。原始样本和决策记录保存在
`~/r1-robonix/.work/jev-mvp-4b/`。

## 能力

| 能力 | 行为 |
|---|---|
| `evaluate` | 获取实时观察或读取本服务归档样本，返回决策 |
| `run_step` | 运动配置启用时，获取新观察并执行至多一个动作 |
| `status` | 查询指定任务 |
| `cancel` | 取消指定任务并清理已有运动输出 |

四项能力均提供 MCP/gRPC；共享 Driver 负责生命周期。
当前正式配置为 `motion_enabled=false`，允许通过 Client 对话进行
实时 `evaluate`。运动关闭检查已通过，Jev 现场运动仍待验收。

PC 顺序 GPU 调度在视觉描述期间暂存 4B 权重，所有推理仍使用 CUDA。
当前只读配置的完整请求期限为六十秒，五秒性能目标单独记录。
图像与深度尚未配准，模型概率不作为可通行距离或到达目标的证明。

PC 启动、同样本对比、标签和报告方法见项目
`experiments/jev_mvp/README.md` 和 `docs/Jev_MVP实现计划.md`。
