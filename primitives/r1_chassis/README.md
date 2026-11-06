# R1 walking primitive

Calls the official high-level sport controller through Unitree SDK2 `LocoClient.SetVelocity(vx, vy, omega, duration)`. Non-zero speed requires FSM 811 (walk-run). The operator selects that mode with the official remote or app.

Official documentation: <https://support.unitree.com/home/zh/R1_developer/sport_services_interface>.

| Capability | Transport | Message and behavior |
| --- | --- | --- |
| `chassis/move` | MCP, gRPC RPC | `chassis/ExecuteMoveCommand`. Runs `forward_m`, `rotate_deg` or a timed velocity, in that priority, then zeros the command |
| `chassis/twist_in` | gRPC client stream | `geometry_msgs/Twist`. Accepts `linear.x`, `linear.y` and `angular.z`, then zeros the command when the stream ends or is cancelled |
| `robonix/lifecycle/driver` | gRPC | Init reads the official FSM. Shutdown sends zero velocity |

Capability paths use the `robonix/primitive/` prefix. The two motion entries are mutually exclusive. An all-zero `move` can stop the current motion. `linear.z`, `angular.x` and `angular.y` are not supported. Distance and angle become a duration at the deployment speed, so they are open-loop approximations. `done` means the timed command finished and a hip or knee moved at least `0.1 rad`. The result includes `motion_observed`, `joint_motion_rad` and `native_return_codes`. That check confirms a leg response. Position and heading accuracy need a separate measurement.

`move` sends one finite-duration command. During the command it checks the FSM, cancellation and joint feedback. Feedback is the latest sample at 20 Hz. It then sends zero velocity. The default duration is five seconds and the maximum is ten. If the process dies, the official controller stops the input when the command expires. Each `twist_in` sample is valid for 0.3 seconds by default, so a velocity stream must keep updating, preferably above 10 Hz. Cancel and shutdown send zero velocity. The robot stays in its current mode.

The package depends on SDK2, CycloneDDS 0.10.2, `robonix-api` and the robot DDS network. The build script installs existing offline dependencies from `RBNX_OFFLINE_WHEELS` with Python 3.10.

```bash
source ~/r1-robonix/env.sh
cd "$DEPLOY"
rbnx build -p primitives/r1_chassis --no-update-check
rbnx start -p primitives/r1_chassis --set network_interface=eth10
```

The full deployment starts this package from `robonix_manifest.yaml`. Public settings and units are in `config.spec`. Speed and time limits come from the deployment. The official controller also clips input to its own range. Dialogue arguments are in [CAPABILITY.md](CAPABILITY.md). The zero-velocity check uses real gRPC and official DDS, and stores every velocity argument in `rbnx-build/zero-velocity-result.json`:

```bash
cd "$DEPLOY/primitives/r1_chassis"
PYTHONPATH="$PWD:$PWD/rbnx-build/codegen/proto_gen" \
  .venv/bin/python tests/check_zero_velocity.py
```

Onboard ai_sport `1.0.2.154` passed a native forward test: `SetVelocity(0.3, 0, 0, duration=5)` produced steps, and both the motion and stop requests returned `127`. This package accepts `0` and `127`. Any other code is a failure. The raw code is kept, and a motion result still has to pass the joint-feedback check. The default forward speed is `0.3 m/s`. The default backward speed magnitude is `0.4 m/s`. A negative `forward_m` uses `backward_speed_m_s` to compute the duration. The planar speed limit is `0.4 m/s`. Backward `linear_x=-0.4` for five seconds produced steps, with a maximum leg-joint change of about `0.60 rad`. Lateral motion, rotation and measured displacement still need on-robot acceptance.
