# 参数由 Settings 校验；JSON/YAML 直接作为 Driver CMD_INIT 配置。
model_revision: 必填，Decider Hugging Face snapshot 的 40 位 commit。
data_dir: 必填，本服务样本、决策及 SQLite 任务记录的可写目录。
decider_url: string，默认 http://127.0.0.1:18080，固定模型服务地址。
encoder_url: string，默认 http://127.0.0.1:18081，须与 PC 的 JEV_ENCODER_URL 一致；描述请求经 Decider /mvp/encode 调度。
camera_provider_id: string，默认 r1_camera。
depth_provider_id: string，默认 r1_depth。
state_provider_id: string，默认 r1_state。
chassis_provider_id: string，默认 r1_chassis。
capture_depth: bool，默认 true；启用时深度缺失直接报告采集失败。
pipeline_timeout_s: float，默认 5，范围 (0,120]，完整 PC 请求共同期限，单位秒。
capture_timeout_s: float，默认 3，范围 (0,30]，每个传感器等待上限，单位秒。
decision_age_limit_s: float，默认 8，范围 (0,30]，运动前图片年龄上限，单位秒。
control_rate_hz: float，默认 20，范围 [10,50]，本地速度输出频率。
motion_enabled: bool，默认 false；true 允许 run_step，须符合现场测试范围。
turning_verified: bool，默认 false；true 将已经验收的左右转向加入现场候选。
forward_speed: float，默认 0.3，范围 (0,0.4]，前向速度，单位 m/s。
forward_duration_s: float，默认 5，范围 (0,5]，前进持续时间，单位秒。
turn_speed: float，默认 0.2，范围 (0,0.5]，转向角速度模长，单位 rad/s。
turn_duration_s: float，默认 2，范围 (0,5]，转向持续时间，单位秒。
