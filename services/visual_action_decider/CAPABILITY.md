# R1 视觉动作决策

`evaluate` 获取真实画面或读取归档样本，返回动作选择，不执行运动。
`run_step` 获取新画面，完成一次决策并执行至多一个动作，快速返回 `run_id`。
使用 `status` 查询同一任务，使用 `cancel` 取消；任务完成后停止查询。

`pipeline` 为 `direct_image` 或 `visual_text`；未指定时使用 `direct_image`。
调用方为每个请求生成 UUID `request_id`，重发时保留相同 ID，独立任务使用新 ID。
实时调用的 `sample_path` 为空，`scene_id` 可填写场景名称；归档样本使用本服务数据目录内的 `sample.json` 路径。

固定动作是左转、前进、右转和停止。现场候选受当前部署和验收配置限制。
运动要求官方 FSM 811，服务不自动切换模式。`motion_enabled` 默认为 false，
转向通过验收后才能配置 `turning_verified=true`。

用户要求判断时使用 `evaluate`；用户明确要求执行一步时使用 `run_step`。
动作参数由部署配置提供，不根据模型输出生成任意速度。任务失败后报告原因，
不自动重复运动；取消后迟到的模型响应不触发动作。

回复说明实际 pipeline、选中动作、耗时、执行结果和停止确认。
概率只表示候选选择分布；接口成功和关节响应不能证明已经到达某个位置。
