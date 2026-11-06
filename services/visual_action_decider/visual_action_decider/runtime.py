import threading
import time
from pathlib import Path
from uuid import UUID, uuid4

import grpc
import httpx

from .client import DecisionClient
from .dataset import load_sample, save_json
from .models import Action, Pipeline, fingerprint
from .store import Store, TERMINAL


class Runtime:
    def __init__(self, settings, robot):
        self.settings = settings
        self.robot = robot
        self.client = DecisionClient(settings)
        self.store = Store(settings.data_dir)
        self.lock = threading.RLock()
        self.active_run = None
        self.cancelled = None
        self.worker = None
        self.closed = False

    def evaluate(self, request):
        began = time.monotonic()
        request_id = UUID(request.request_id)
        pipeline = Pipeline(request.pipeline or Pipeline.DIRECT_IMAGE)
        if request.sample_path:
            path = Path(request.sample_path).resolve()
            if not path.is_relative_to(Path(self.settings.data_dir).resolve()):
                raise ValueError("an archived sample must stay inside this service data_dir")
            sample = load_sample(path)
            if request.instruction and request.instruction != sample.instruction:
                raise ValueError("the archived sample instruction does not match the request")
        else:
            if not request.instruction.strip():
                raise ValueError("instruction must not be empty")
            path = self.robot.capture(request.instruction, request.scene_id or "live")
        prepared = time.monotonic()
        decision = self.client.evaluate(path, pipeline, list(Action), request_id)
        decision.timings_ms.update(observation_prepare=(prepared - began) * 1000, service_total=(time.monotonic() - began) * 1000)
        save_json(Path(self.settings.data_dir) / "decisions" / str(request_id) / "service-decision.json", decision.model_dump(mode="json"))
        return decision

    def start(self, request):
        request_id = str(UUID(request.request_id))
        pipeline = Pipeline(request.pipeline or Pipeline.DIRECT_IMAGE)
        instruction = request.instruction.strip()
        if not instruction or len(instruction) > 2000:
            raise ValueError("instruction length is invalid")
        signature = fingerprint({"pipeline": pipeline.value, "instruction": instruction, "scene_id": request.scene_id})
        with self.lock:
            if self.closed:
                raise RuntimeError("the service is shut down")
            existing = self.store.find_request(request_id)
            if existing is not None:
                if existing[0] != signature:
                    raise ValueError("REQUEST_ID_CONFLICT")
                return existing[1]
            actions = self.settings.live_actions()
            if self.active_run is not None:
                raise RuntimeError(f"BUSY: {self.active_run}")
            run_id = str(uuid4())
            record = {"run_id": run_id, "request_id": request_id, "state": "ACCEPTED",
                      "error_code": "", "error_message": "", "stop_requested": False, "stop_confirmed": False,
                      "execution_started": False, "execution_finished": False, "physical_motion_confirmed": None,
                      "created_unix_ns": time.time_ns()}
            self.store.create(record, signature)
            self.active_run = run_id
            self.cancelled = threading.Event()
            self.worker = threading.Thread(target=self._run, args=(record, instruction, request.scene_id or "live", pipeline, actions, self.cancelled),
                                           name="jev-step", daemon=True)
            self.worker.start()
            return record

    def transition(self, run_id, state, cancelled):
        with self.lock:
            if cancelled.is_set():
                raise RuntimeError("the task was cancelled")
            self.store.update(run_id, state=state)

    def _run(self, record, instruction, scene_id, pipeline, actions, cancelled):
        run_id = record["run_id"]
        motion = False
        try:
            self.transition(run_id, "OBSERVING", cancelled)
            path = self.robot.capture(instruction, scene_id)
            sample = load_sample(path)
            if sample.source_kind != "r1_live":
                raise ValueError("run_step requires a live R1 observation")
            if (time.monotonic_ns() - sample.received_monotonic_ns) / 1e9 > 2:
                raise RuntimeError("OBSERVATION_STALE: the image expired before it was sent to the model")
            self.store.update(run_id, sample_path=str(path))
            self.transition(run_id, "DECIDING", cancelled)
            decision = self.client.evaluate(path, pipeline, actions, UUID(record["request_id"]), cancelled)
            self.store.update(run_id, decision=decision.model_dump(mode="json"))
            self.transition(run_id, "VALIDATING", cancelled)
            if (time.monotonic_ns() - sample.received_monotonic_ns) / 1e9 > self.settings.decision_age_limit_s:
                raise RuntimeError("OBSERVATION_STALE: the decision expired before execution")
            self.robot.validate_state(self.robot.state())
            if decision.selected_action == Action.STOP:
                with self.lock:
                    if cancelled.is_set():
                        raise RuntimeError("the task was cancelled")
                    self.store.update(run_id, state="SUCCEEDED", termination_reason="selected_stop")
                return
            with self.lock:
                self.transition(run_id, "EXECUTING", cancelled)
                self.store.update(run_id, execution_started=True)
                motion = True
            result = self.robot.execute(decision.selected_action, cancelled)
            with self.lock:
                self.store.update(run_id, state="STOPPING", execution=result, stop_requested=result["stop_requested"],
                                  stop_confirmed=result["stop_confirmed"], execution_finished=not cancelled.is_set())
                if not result["stop_confirmed"]:
                    raise RuntimeError("STOP_UNCONFIRMED")
                self.store.update(run_id, state="CANCELLED" if cancelled.is_set() else "SUCCEEDED")
        except (ValueError, RuntimeError, TimeoutError, httpx.HTTPError, grpc.RpcError, grpc.FutureCancelledError) as error:
            with self.lock:
                values = {"error_code": self.error_code(error), "error_message": str(error), "state": "FAILED"}
                if motion:
                    result = self.robot.last_execution
                    values.update(execution=result, stop_requested=result["stop_requested"], stop_confirmed=result["stop_confirmed"])
                if cancelled.is_set() and (not motion or values.get("stop_confirmed")):
                    values.update(state="CANCELLED", error_code="", error_message="")
                self.store.update(run_id, **values)
        except BaseException as error:
            self.store.update(run_id, state="FAILED", error_code="INTERNAL_ERROR", error_message=str(error))
            raise
        finally:
            with self.lock:
                if self.active_run == run_id:
                    self.active_run = None

    @staticmethod
    def error_code(error):
        text = str(error)
        for code in ("OBSERVATION_STALE", "FEEDBACK_STALE", "MODE_NOT_READY", "STOP_UNCONFIRMED", "INVALID_MODEL_RESPONSE"):
            if code in text:
                return code
        if isinstance(error, (TimeoutError, httpx.TimeoutException)):
            return "PIPELINE_TIMEOUT"
        if isinstance(error, httpx.HTTPError):
            return "MODEL_UNAVAILABLE"
        return "EXECUTION_FAILED"

    def status(self, run_id):
        return self.store.get(str(UUID(run_id)))

    def cancel(self, run_id):
        run_id = str(UUID(run_id))
        with self.lock:
            record = self.store.get(run_id)
            if record["state"] in TERMINAL:
                return record
            if run_id != self.active_run:
                raise RuntimeError("this process does not have that task")
            self.cancelled.set()
            self.store.update(run_id, state="CANCELLING")
            moving = record["execution_started"]
            if moving:
                self.store.update(run_id, stop_requested=True)
                try:
                    result = self.robot.stop()
                except (grpc.RpcError, RuntimeError) as error:
                    self.store.update(run_id, error_code="STOP_UNCONFIRMED", error_message=str(error))
                    raise
                self.store.update(run_id, stop_confirmed=True, cancel_stop_response=result)
            return self.store.get(run_id)

    def close(self):
        with self.lock:
            self.closed = True
            active = self.active_run
            worker = self.worker
        if active is not None:
            self.cancel(active)
        if worker is not None:
            worker.join(timeout=self.settings.pipeline_timeout_s + self.settings.capture_timeout_s * 3 + 5)
            if worker.is_alive():
                raise RuntimeError("the task thread did not finish within the shutdown deadline")
