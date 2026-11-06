from pathlib import Path

from ikpy.chain import Chain
import numpy as np
from scipy.spatial.transform import Rotation


ROOT = Path(__file__).resolve().parents[3]


class ArmKinematics:
    def __init__(self, side):
        if side not in ("left", "right"):
            raise ValueError("side 必须为 left 或 right")
        self.frame_id = "waist_yaw_link"
        self.tip_link = f"{side}_wrist_roll_link"
        self.names = [f"{side}_{joint}_joint" for joint in
                      ("shoulder_pitch", "shoulder_roll", "shoulder_yaw", "elbow", "wrist_roll")]
        self.chain = Chain.from_urdf_file(
            str(ROOT / "urdf/R1.urdf"),
            base_elements=[self.frame_id, self.names[0]],
            last_link_vector=[0, 0, 0],
            active_links_mask=[False, True, True, True, True, True, False], symbolic=False)
        if [link.name for link in self.chain.links[1:-1]] != self.names:
            raise ValueError("URDF 机械臂关节链与五自由度 R1 模型不一致")

    def joints(self, positions):
        values = np.array([positions[name] for name in self.names], dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("机械臂关节反馈包含非有限数值")
        return np.concatenate(([0.0], values, [0.0]))

    def forward(self, positions):
        return self.chain.forward_kinematics(self.joints(positions))

    def solve(self, position, quaternion, positions):
        position = np.asarray(position, dtype=float)
        quaternion = np.asarray(quaternion, dtype=float)
        if position.shape != (3,) or quaternion.shape != (4,):
            raise ValueError("目标必须包含三个位置分量和四个四元数分量")
        if not np.isfinite(position).all() or not np.isfinite(quaternion).all():
            raise ValueError("目标位姿包含非有限数值")
        if abs(np.linalg.norm(quaternion) - 1.0) > 1e-3:
            raise ValueError("目标四元数必须归一化，分量顺序为 x,y,z,w")
        target = np.eye(4)
        target[:3, 3] = position
        target[:3, :3] = Rotation.from_quat(quaternion).as_matrix()
        solution = self.chain.inverse_kinematics_frame(
            target, initial_position=self.joints(positions), orientation_mode="all")
        if not np.isfinite(solution).all():
            raise ValueError("IK 未得到有限关节角度")
        actual = self.chain.forward_kinematics(solution)
        position_error = float(np.linalg.norm(actual[:3, 3] - position))
        orientation_error = float(Rotation.from_matrix(target[:3, :3].T @ actual[:3, :3]).magnitude())
        if position_error > 1e-4 or orientation_error > 1e-3:
            raise ValueError(f"五自由度机械臂无法满足目标位姿：位置残差 {position_error:.6f} m，"
                             f"姿态残差 {orientation_error:.6f} rad")
        values = solution[1:-1]
        for link, value in zip(self.chain.links[1:-1], values):
            if not link.bounds[0] <= value <= link.bounds[1]:
                raise ValueError(f"IK 结果超过 URDF 限位：{link.name}")
        return values.tolist(), position_error, orientation_error
