import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time
import xml.etree.ElementTree as ET

from cyclonedds.domain import Domain, DomainParticipant
from cyclonedds.internal import InvalidSample
from cyclonedds.qos import Policy, Qos
from cyclonedds.sub import DataReader
from cyclonedds.topic import Topic
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_


CLIENT = Path("/unitree/module/system_patch_pc4/depth_client/client")
CLIENT_ARGS = [str(CLIENT), "192.168.123.161", "5000", "/dev/video-dep"]


def report(event, **values):
    print(json.dumps({"event": event, "timestamp_ns": time.time_ns(), **values}), flush=True)


class RebootDetector:
    def __init__(self):
        self.tick = None
        self.received = None

    def observe(self, tick, now):
        reason = None
        if self.tick is not None:
            gap = now - self.received
            forward = (tick - self.tick) % (1 << 32)
            if gap >= 3.0:
                reason = "robot_reconnected"
            elif self.tick - tick > 1000 and forward > 5000:
                reason = "robot_tick_reset"
        self.tick, self.received = tick, now
        return reason


class DepthReceiver:
    def __init__(self, run_dir, log_dir, stopped):
        self.run_dir = run_dir
        self.log_dir = log_dir
        self.stopped = stopped
        self.child = None

    def running(self):
        result = subprocess.run(["pgrep", "-fx", re.escape(" ".join(CLIENT_ARGS))],
                                capture_output=True, text=True)
        if result.returncode == 1:
            return []
        result.check_returncode()
        return [int(value) for value in result.stdout.split()]

    def restart(self, reason):
        previous = self.running()
        for pid in previous:
            os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 3.0
        while self.running():
            if time.monotonic() >= deadline:
                raise RuntimeError("the official depth receiver process did not exit")
            if self.stopped.wait(0.1):
                return
        if self.child is not None:
            self.child.wait(timeout=1)
        if self.stopped.is_set():
            return
        with (self.log_dir / "depth-client.log").open("ab") as log:
            self.child = subprocess.Popen(CLIENT_ARGS, cwd=CLIENT.parent,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        (self.run_dir / "depth-client.pid").write_text(str(self.child.pid) + "\n")
        report("depth_receiver_restarted", reason=reason, previous_pids=previous, pid=self.child.pid)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interface", default="eth10")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--log-dir", type=Path, required=True)
    args = parser.parse_args()
    stopped = threading.Event()
    requested = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_args: stopped.set())
    signal.signal(signal.SIGINT, lambda *_args: stopped.set())
    signal.signal(signal.SIGUSR1, lambda *_args: requested.set())
    with (args.run_dir / "robot-reboot-watch.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        config = ET.Element("CycloneDDS")
        domain_config = ET.SubElement(config, "Domain", Id="0")
        interfaces = ET.SubElement(ET.SubElement(domain_config, "General"), "Interfaces")
        ET.SubElement(interfaces, "NetworkInterface", name=args.interface)
        domain = Domain(0, ET.tostring(config, encoding="unicode"))
        participant = DomainParticipant(0)
        reader = DataReader(participant, Topic(participant, "rt/lowstate", LowState_),
                            Qos(Policy.History.KeepLast(1), Policy.Reliability.BestEffort))
        receiver = DepthReceiver(args.run_dir, args.log_dir, stopped)
        if not receiver.running():
            receiver.restart("receiver_start")
        detector = RebootDetector()
        ready = False
        while not stopped.is_set():
            for message in reader.take(1):
                if isinstance(message, InvalidSample):
                    continue
                reason = detector.observe(int(message.tick), time.monotonic())
                if not ready:
                    report("robot_reboot_watch_ready", tick=detector.tick)
                    ready = True
                if reason:
                    report("robot_restart_detected", reason=reason, tick=detector.tick)
                    receiver.restart(reason)
                    detector = RebootDetector()
            if requested.is_set():
                requested.clear()
                receiver.restart("operator_request")
                detector = RebootDetector()
            stopped.wait(0.5)


if __name__ == "__main__":
    main()
