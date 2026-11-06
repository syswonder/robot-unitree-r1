#!/usr/bin/env python3
"""Validate the R1 Soma YAML and the URDF it references.

This is an offline, read-only check. It does not start Soma, ROS, DDS, any
provider, or the robot. It catches the mistakes that are easy to make while
onboarding a vendor model: wrong root link, missing meshes, absolute/package
mesh paths, unknown links/joints in the component tree, duplicate component
ids, a footprint that does not enclose the origin, and unrepresented actuated
joints.
"""

from __future__ import annotations

import argparse
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml


def _point_in_polygon(x: float, y: float, points: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xin = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < xin:
                inside = not inside
    return inside


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--deploy",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Deployment directory containing soma.yaml (default: parent of scripts/)",
    )
    args = parser.parse_args()
    deploy = args.deploy.resolve()
    soma_path = deploy / "soma.yaml"
    errors: list[str] = []
    warnings: list[str] = []

    if not soma_path.is_file():
        print(f"ERROR: missing {soma_path}", file=sys.stderr)
        return 1

    try:
        soma = yaml.safe_load(soma_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"ERROR: cannot parse {soma_path}: {exc}", file=sys.stderr)
        return 1
    if not isinstance(soma, dict):
        print("ERROR: soma.yaml must be a mapping", file=sys.stderr)
        return 1

    urdf_section = soma.get("urdf")
    robot_section = soma.get("robot")
    if not isinstance(urdf_section, dict):
        errors.append("soma.yaml: missing or invalid 'urdf' mapping")
        urdf_section = {}
    if not isinstance(robot_section, dict):
        errors.append("soma.yaml: missing or invalid 'robot' mapping")
        robot_section = {}

    urdf_value = urdf_section.get("path")
    if not isinstance(urdf_value, str) or not urdf_value.strip():
        errors.append("soma.yaml: urdf.path must be a non-empty string")
        urdf_path = None
    else:
        urdf_path = (soma_path.parent / urdf_value).resolve()
        if not urdf_path.is_file():
            errors.append(f"soma.yaml: urdf.path does not exist: {urdf_path}")

    robot_id = robot_section.get("id")
    if not isinstance(robot_id, str) or not robot_id.strip():
        errors.append("soma.yaml: robot.id must be a non-empty string")

    if urdf_path is None or not urdf_path.is_file():
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    try:
        root = ET.parse(urdf_path).getroot()
    except Exception as exc:
        print(f"ERROR: cannot parse URDF {urdf_path}: {exc}", file=sys.stderr)
        return 1
    if root.tag != "robot":
        errors.append(f"URDF: root element is <{root.tag}>, expected <robot>")
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    links = {link.attrib.get("name", ""): link for link in root.findall("link")}
    joints = {joint.attrib.get("name", ""): joint for joint in root.findall("joint")}
    if "" in links or "" in joints:
        errors.append("URDF: every link and joint must have a non-empty name")

    children = set()
    for name, joint in joints.items():
        parent = joint.find("parent")
        child = joint.find("child")
        if parent is None or child is None:
            errors.append(f"URDF: joint {name!r} is missing parent or child")
            continue
        parent_link = parent.attrib.get("link", "")
        child_link = child.attrib.get("link", "")
        if parent_link not in links:
            errors.append(f"URDF: joint {name!r} references unknown parent link {parent_link!r}")
        if child_link not in links:
            errors.append(f"URDF: joint {name!r} references unknown child link {child_link!r}")
        children.add(child_link)

    roots = sorted(set(links) - children)
    declared_root = urdf_section.get("root_link")
    actual_root = roots[0] if len(roots) == 1 else None
    if len(roots) != 1:
        errors.append(f"URDF: expected exactly one root link, found {roots}")
    if declared_root != actual_root:
        errors.append(
            f"soma.yaml: urdf.root_link={declared_root!r}, "
            f"URDF actual root={actual_root!r}"
        )

    revolute = {name for name, joint in joints.items() if joint.attrib.get("type") == "revolute"}
    fixed = {name for name, joint in joints.items() if joint.attrib.get("type") == "fixed"}
    if not fixed:
        errors.append("URDF: expected at least one fixed joint for a static TF tree")

    urdf_dir = urdf_path.parent
    mesh_refs = 0
    for mesh in root.iter("mesh"):
        filename = mesh.attrib.get("filename", "")
        if not filename:
            errors.append("URDF: <mesh> without filename")
            continue
        mesh_refs += 1
        if filename.startswith(("package://", "file://", "http://", "https://", "data:")):
            errors.append(f"URDF: non-portable mesh path {filename!r}")
            continue
        rel = Path(filename)
        if rel.is_absolute():
            errors.append(f"URDF: absolute mesh path {filename!r}")
            continue
        resolved = (urdf_dir / rel).resolve()
        try:
            resolved.relative_to(urdf_dir)
        except ValueError:
            errors.append(f"URDF: mesh path escapes URDF directory: {filename!r}")
            continue
        if not resolved.is_file():
            errors.append(f"URDF: mesh file not found: {filename!r}")

    footprint = robot_section.get("footprint")
    if footprint is not None:
        if not isinstance(footprint, dict):
            errors.append("soma.yaml: robot.footprint must be a mapping")
        else:
            base_frame = footprint.get("base_frame")
            if not isinstance(base_frame, str) or base_frame not in links:
                errors.append(f"soma.yaml: footprint.base_frame {base_frame!r} is not a URDF link")
            points = footprint.get("points")
            if not isinstance(points, list) or len(points) < 3:
                errors.append("soma.yaml: footprint.points must contain at least 3 points")
            else:
                parsed: list[tuple[float, float]] = []
                for point in points:
                    if (
                        not isinstance(point, list)
                        or len(point) != 2
                        or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in point)
                    ):
                        errors.append(f"soma.yaml: invalid footprint point {point!r}")
                        continue
                    parsed.append((float(point[0]), float(point[1])))
                if len(parsed) == len(points):
                    if not _point_in_polygon(0.0, 0.0, parsed):
                        errors.append("soma.yaml: footprint does not enclose the origin")

    components = robot_section.get("components", [])
    if components is None:
        components = []
    if not isinstance(components, list):
        errors.append("soma.yaml: robot.components must be a list")
        components = []

    seen_ids: set[str] = set()
    represented_joints: set[str] = set()

    def validate_exports(exports: object, where: str) -> None:
        if exports is None:
            errors.append(f"{where}: missing exports (use [] when none)")
            return
        if not isinstance(exports, list):
            errors.append(f"{where}: exports must be a list")
            return
        for export in exports:
            if not isinstance(export, dict):
                errors.append(f"{where}: export entry must be a mapping")
                continue
            provider_id = export.get("provider_id")
            if not isinstance(provider_id, str) or not provider_id.strip():
                errors.append(f"{where}: export.provider_id must be non-empty")
            capabilities = export.get("capabilities")
            if not isinstance(capabilities, list):
                errors.append(f"{where}: export.capabilities must be a list")
                continue
            for capability in capabilities:
                if not isinstance(capability, dict):
                    errors.append(f"{where}: capability entry must be a mapping")
                    continue
                path = capability.get("path")
                if not isinstance(path, str) or not path.startswith("robonix/"):
                    errors.append(f"{where}: capability path must start with 'robonix/': {path!r}")

    def walk(nodes: list[object], prefix: str) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                errors.append(f"{prefix}: component must be a mapping")
                continue
            component_id = node.get("id")
            if not isinstance(component_id, str) or not component_id.strip():
                errors.append(f"{prefix}: component missing non-empty id")
                continue
            where = f"{prefix}/{component_id}"
            if component_id in seen_ids:
                errors.append(f"{where}: duplicate component id")
            seen_ids.add(component_id)
            urdf_link = node.get("urdf_link")
            if urdf_link is not None and urdf_link not in links:
                errors.append(f"{where}: unknown urdf_link {urdf_link!r}")
            urdf_joint = node.get("urdf_joint")
            if urdf_joint is not None:
                if urdf_joint not in joints:
                    errors.append(f"{where}: unknown urdf_joint {urdf_joint!r}")
                else:
                    represented_joints.add(urdf_joint)
            validate_exports(node.get("exports", []), where)
            child_nodes = node.get("components", [])
            if child_nodes is None:
                child_nodes = []
            if not isinstance(child_nodes, list):
                errors.append(f"{where}: components must be a list")
                continue
            walk(child_nodes, where)

    validate_exports(robot_section.get("exports", []), "robot")
    walk(components, "robot")

    missing_joints = sorted(revolute - represented_joints)
    if missing_joints:
        warnings.append(
            "actuated joints not represented in robot.components: "
            + ", ".join(missing_joints)
        )

    masses = []
    for name, link in links.items():
        mass = link.find("inertial/mass")
        if mass is not None:
            try:
                masses.append(float(mass.attrib["value"]))
            except (KeyError, ValueError):
                errors.append(f"URDF: link {name!r} has invalid inertial/mass")

    dimensions = robot_section.get("dimensions")
    if dimensions is not None:
        if not isinstance(dimensions, dict):
            errors.append("soma.yaml: robot.dimensions must be a mapping")
        else:
            for key in ("length_m", "width_m", "height_m"):
                value = dimensions.get(key)
                if value is not None and (not isinstance(value, (int, float)) or value <= 0):
                    errors.append(f"soma.yaml: robot.dimensions.{key} must be positive")
    mass_kg = robot_section.get("mass_kg")
    if mass_kg is not None and (not isinstance(mass_kg, (int, float)) or mass_kg <= 0):
        errors.append("soma.yaml: robot.mass_kg must be positive")

    print(f"deployment: {deploy}")
    print(f"urdf:       {urdf_path}")
    print(f"robot id:   {robot_id}")
    print(f"links:      {len(links)}")
    print(f"joints:     {len(joints)} (revolute={len(revolute)}, fixed={len(fixed)})")
    print(f"meshes:     {mesh_refs} references, all local"
          if not any("mesh" in e for e in errors) else f"meshes:     {mesh_refs} references")
    print(f"mass:       {sum(masses):.4f} kg (sum of URDF link masses)")
    if warnings:
        for warning in warnings:
            print(f"WARNING: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"\nFAILED: {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("\nOK: soma.yaml and URDF are internally consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
