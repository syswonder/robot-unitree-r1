# R1 visual action decider

Reads R1 RGB, CameraInfo, depth and state through Atlas, and submits the same observation to the PC Decider-4B. `direct_image` uses the raw image. `visual_text` uses the BLIP/RAM description. The model returns probabilities for turn left, forward, turn right and stop.

## Deployment

The R1 needs Python 3.10, the existing Robonix API, and the camera and state primitives. The robot does not install PyTorch or the model weights. The build accepts `RBNX_OFFLINE_WHEELS` pointing at the existing offline wheel directory. Public settings are in `config.spec`. Call instructions are in `CAPABILITY.md`.

```bash
source ~/r1-robonix/scripts/env.sh
rbnx build -p "$DEPLOY/services/visual_action_decider"
bash ~/r1-robonix/scripts/02_start.sh
```

The root manifest registers this service. The current model revision is `585473dec4fa93f0325c2bf02dda7273b61f44c1`. PC ports 18080 and 18081 are reached from the R1 through a reverse tunnel. Raw samples and decision records are stored under the configured `data_dir`.

## Capabilities

| Capability | Behavior |
| --- | --- |
| `evaluate` | Take a live observation or read an archived sample from this service, and return a decision |
| `run_step` | When motion is enabled, take a new observation and run at most one action |
| `status` | Read one task |
| `cancel` | Cancel one task and clear motion output already sent |

All four capabilities are available over MCP and gRPC. The shared Driver owns the lifecycle. The current production setting is `motion_enabled=false`, so a client dialogue can call live `evaluate`. The motion-disabled check has passed. On-robot Jev motion still needs acceptance.

The PC GPU scheduler parks the 4B weights while a visual description runs. Inference still uses CUDA. The current read-only configuration allows sixty seconds for a full request. The five-second performance target is recorded separately. Image and depth are not registered. Model probabilities are not evidence of a free distance or of reaching a goal.

PC startup, same-sample comparison, labels and the report method are in the project notes `experiments/jev_mvp/README.md` and `docs/Jev_MVP implementation plan`.
