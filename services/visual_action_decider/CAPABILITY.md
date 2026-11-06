# R1 visual action decisions

`evaluate` takes a live image or reads an archived sample and returns an action choice. It does not move the robot. `run_step` takes a new image, makes one decision and runs at most one action, then returns `run_id` quickly. Use `status` to read that task and `cancel` to cancel it. Stop polling after the task finishes.

`pipeline` is `direct_image` or `visual_text`. The default is `direct_image`. The caller generates a UUID `request_id` for each request, keeps that ID on a retry, and uses a new ID for a new task. A live call leaves `sample_path` empty. `scene_id` may name the scene. An archived sample uses a `sample.json` path inside this service's data directory.

The fixed actions are turn left, forward, turn right and stop. The live candidate set is limited by the current deployment and acceptance settings. Motion requires official FSM 811. The service does not change the mode. `motion_enabled` defaults to false. `turning_verified=true` is allowed only after turning has been accepted.

Use `evaluate` when the user asks for a judgement. Use `run_step` only when the user explicitly asks to execute one step. Action parameters come from the deployment, not from arbitrary speeds in the model output. After a failure, report the reason and do not repeat the motion. A late model response after cancel does not start an action.

The reply states the pipeline actually used, the selected action, the duration, the execution result and the stop confirmation. Probabilities are only the choice distribution. A successful call and a joint response do not prove that the robot reached a place.
