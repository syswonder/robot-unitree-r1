# Unitree R1 URDF

## Source

- Repository: `https://github.com/unitreerobotics/unitree_ros`
- Package: `robots/r1_description`
- Pinned commit: `5994d4faef0a9cadd3287f8de0199a67eeb2a259` (2026-09-30)
- License: BSD-3-Clause; the upstream license is copied as
  `LICENSE.unitree`.

## Contents

```text
urdf/
├── R1.urdf
├── meshes/                 # 43 official STL/STL files
├── meshes.sha256           # all 43 mesh checksums
├── LICENSE.unitree
└── README.md
```

The URDF uses Soma-compatible relative mesh paths (`meshes/<file>.STL`). The
mesh filenames and their case are preserved exactly.

## Modification from upstream

Only one frame was added, immediately before `pelvis_link`:

```xml
<link name="base_link"/>
<joint name="base_link_to_pelvis" type="fixed">
  <origin xyz="0 0 0" rpy="0 0 0"/>
  <parent link="base_link"/>
  <child link="pelvis_link"/>
</joint>
```

The official model uses `pelvis_link` as its root. The zero-offset wrapper
gives Robonix, Nav2 and the generic robot-description primitive the
conventional `base_link` frame. No geometry, inertia, joint origin, limit or
mesh was changed.

The upstream `<mujoco>` element is retained; it is not used by Soma or by a
standard `robot_state_publisher`.

## Model facts

- Robot name in URDF: `R1`
- Official tree: 40 links / 39 joints (26 revolute + 13 fixed)
- After wrapper: 41 links / 40 joints (26 revolute + 14 fixed)
- 26 revolute joints = R1 EDU body DOF
- Total link mass: 28.8356 kg
- Zero-pose visual bounding box: 0.3691 × 0.3625 × 1.2302 m
- IMU frame: `imu_in_pelvis_link`
- Camera frame: none in the official URDF

`torso_collision.stl` is present upstream but is not referenced by this URDF;
it is retained in `meshes/` and covered by `meshes.sha256`.

## Validation

```bash
python3 -I ../scripts/validate_soma_urdf.py
# optional, if liburdfdom-tools is installed:
check_urdf R1.urdf
```

The offline validator checks the root, all joint parent/child links, every
Soma `urdf_link`/`urdf_joint` reference, all relative mesh paths and the
footprint. It does not start Soma, ROS, DDS, any provider or the robot.

## Notes

- R1 Air uses `r1_air_description` (20 DOF) and is not this model.
- The official R1 URDF has no camera frame. Do not invent one; measure the
  extrinsic and add a documented frame only when the camera primitive is
  implemented.
- The URDF is geometry/TF data. It does not provide safety limits; motion
  limits must come from the controller and an operator-approved profile.
