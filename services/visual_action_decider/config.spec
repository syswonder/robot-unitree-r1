# Settings are checked by Settings. JSON or YAML is sent as Driver CMD_INIT config.
model_revision: required, 40-character commit of the Decider Hugging Face snapshot.
data_dir: required writable directory for samples, decisions and the SQLite task record.
decider_url: string, default http://127.0.0.1:18080, fixed model service address.
encoder_url: string, default http://127.0.0.1:18081. It must match JEV_ENCODER_URL on the PC. Description requests are scheduled through Decider /mvp/encode.
camera_provider_id: string, default r1_camera.
depth_provider_id: string, default r1_depth.
state_provider_id: string, default r1_state.
chassis_provider_id: string, default r1_chassis.
capture_depth: bool, default true. When enabled, a missing depth frame is a capture failure.
pipeline_timeout_s: float, default 5, range (0,120], shared deadline in seconds for one full PC request.
capture_timeout_s: float, default 3, range (0,30], per-sensor wait limit in seconds.
decision_age_limit_s: float, default 8, range (0,30], maximum image age in seconds before motion.
control_rate_hz: float, default 20, range [10,50], local velocity output rate.
motion_enabled: bool, default false. true allows run_step and must stay inside the on-robot test range.
turning_verified: bool, default false. true adds accepted left and right turns to the live candidates.
forward_speed: float, default 0.3, range (0,0.4], forward speed in m/s.
forward_duration_s: float, default 5, range (0,5], forward duration in seconds.
turn_speed: float, default 0.2, range (0,0.5], turn-rate magnitude in rad/s.
turn_duration_s: float, default 2, range (0,5], turn duration in seconds.
