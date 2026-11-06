import argparse

import grpc
from robonix_api import ATLAS

from .controller import JOINTS

import r1_arm_pb2
import robonix_contracts_pb2_grpc as services


def main():
    parser = argparse.ArgumentParser(description="R1 双臂反馈和单关节指令")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    move = commands.add_parser("move")
    move.add_argument("joint_name", choices=JOINTS)
    move.add_argument("target_rad", type=float)
    move.add_argument("--speed", type=float, default=0.05)
    args = parser.parse_args()
    contract = "robonix/primitive/arm/" + ("get_joint_states" if args.command == "status" else "move_joint")
    with ATLAS.connect_capability(consumer_id="r1-arm-terminal", provider_id="r1_arm",
                                  contract_id=contract, transport="grpc") as connection:
        endpoint = connection.endpoint.removeprefix("http://")
        with grpc.insecure_channel(endpoint) as channel:
            if args.command == "status":
                response = services.RobonixPrimitiveArmGetJointStatesStub(channel).GetJointStates(
                    r1_arm_pb2.GetJointStates_Request(), timeout=5)
                print(response.json)
            else:
                response = services.RobonixPrimitiveArmMoveJointStub(channel).MoveJoint(
                    r1_arm_pb2.MoveJoint_Request(joint_name=args.joint_name,
                                                target_rad=args.target_rad, speed_rad_s=args.speed))
                print(response.json)


if __name__ == "__main__":
    main()
