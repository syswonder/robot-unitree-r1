import json
from pathlib import Path
import sys
import threading
import time

package = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(package), str(package / 'rbnx-build/codegen/proto_gen')]

import grpc
from robonix_api import ATLAS
import chassis_pb2
import geometry_msgs_pb2
import robonix_contracts_pb2_grpc as services
from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.unitree_api.msg.dds_ import Request_
from unitree_sdk2py.r1.loco.r1_loco_client import LocoClient

requests = []
lock = threading.Lock()
report = {'provider_id': 'r1_chassis', 'rpc': {}}


def observe(message):
    if message.header.identity.api_id == 7105:
        with lock:
            requests.append({'time_ns': time.time_ns(), 'parameter': json.loads(message.parameter)})


def fsm(client):
    code, data = client._Call(7001, '{}')
    if code != 0:
        raise RuntimeError(f'GetFsmId 查询失败：{code}')
    return json.loads(data)['data']


ChannelFactoryInitialize(0, 'eth10')
subscriber = ChannelSubscriber('rt/api/sport/request', Request_)
subscriber.Init(observe, 100)
client = LocoClient()
client.Init()
client.SetTimeout(2)
try:
    report['fsm_before'] = fsm(client)
    time.sleep(0.3)
    for leaf in ('move', 'twist_in'):
        with ATLAS.connect_capability(consumer_id='r1-chassis-zero-validation',
                                      provider_id=report['provider_id'],
                                      contract_id='robonix/primitive/chassis/' + leaf,
                                      transport='grpc') as connection:
            with grpc.insecure_channel(connection.endpoint.removeprefix('http://')) as channel:
                try:
                    if leaf == 'move':
                        response = services.RobonixPrimitiveChassisMoveStub(channel).ExecuteMoveCommand(
                            chassis_pb2.ExecuteMoveCommand_Request(command=chassis_pb2.MoveCommand()), timeout=5)
                        result = json.loads(response.status.data)
                    else:
                        services.RobonixPrimitiveChassisTwistInStub(channel).TwistIn(
                            iter([geometry_msgs_pb2.Twist() for _ in range(3)]), timeout=5)
                        result = {'status': 'completed'}
                except grpc.RpcError as error:
                    report['rpc'][leaf] = {'accepted': False, 'code': error.code().name,
                                           'details': error.details()}
                else:
                    report['rpc'][leaf] = {'accepted': True, 'result': result}
    report['fsm_after'] = fsm(client)
    assert report['fsm_after'] == report['fsm_before'], report
    time.sleep(0.3)
finally:
    subscriber.Close()
    with lock:
        report['sdk_requests'] = list(requests)
    report['sdk_request_count'] = len(requests)
    report['all_sdk_velocities_zero'] = bool(requests) and all(
        item['parameter']['velocity'] == [0, 0, 0] for item in requests)
    report['acceptance_passed'] = (len(report['rpc']) == 2
        and all(item['accepted'] for item in report['rpc'].values()))
    output = package / 'rbnx-build/zero-velocity-result.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False), flush=True)
assert report['all_sdk_velocities_zero'], report
assert all(0 < item['parameter']['duration'] <= 0.3 for item in requests)
if not report['acceptance_passed']:
    raise SystemExit(2)
