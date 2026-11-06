# R1 body motion

`robonix/primitive/chassis/move` is available over MCP and gRPC and calls the official `SetVelocity()`. Motion requires FSM 811, which `r1_state` can read.

The request uses the standard `command`:

- `linear_x`, `linear_y`: forward and lateral body speed, in m/s.
- `angular_z`: yaw rate, in rad/s.
- `duration_sec`: duration in seconds. Zero uses the five-second default.
- `forward_m`: signed forward distance, in metres.
- `rotate_deg`: signed yaw, in degrees. Positive is counter-clockwise.
- `linear_z`, `angular_x`, `angular_y`: set these to zero.

The checked forward command is `linear_x=0.3`, `duration_sec=5`, with the other fields zero. The checked backward command is `linear_x=-0.4`, `duration_sec=5`, with the other fields zero. The planar speed limit is `0.4 m/s`, the yaw-rate limit is `0.5 rad/s`, and one call lasts at most ten seconds. An all-zero velocity request sends a stop. Lateral motion and rotation still need on-robot acceptance.

Argument priority is `forward_m`, then `rotate_deg`, then velocity. Distance and angle become time at the deployment speed, so they are open-loop approximations and are not a promise of exact displacement. Positive `forward_m` uses `0.3 m/s`. Negative `forward_m` uses `-0.4 m/s`.

`done` means the command finished and a leg response was detected. `joint_motion_rad` is the largest hip or knee angle change. `native_return_codes` keeps the official raw codes. Onboard ai_sport 1.0.2.154 returned `127` for native motion and stop, and that return was checked against real steps. Joint-feedback timeout, a mode change, or too little motion feedback is a failure.
