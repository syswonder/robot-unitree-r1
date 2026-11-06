import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path


TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}


class Store:
    def __init__(self, folder):
        Path(folder).mkdir(parents=True, exist_ok=True)
        self.path = str(Path(folder) / "tasks.sqlite3")
        self.lock = threading.RLock()
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("CREATE TABLE IF NOT EXISTS tasks (run_id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL, payload TEXT NOT NULL)")
            for run_id, payload in connection.execute("SELECT run_id,payload FROM tasks").fetchall():
                record = json.loads(payload)
                if record["state"] not in TERMINAL:
                    record.update(state="FAILED", error_code="PROCESS_INTERRUPTED", error_message="服务重新启动，任务已终止")
                    connection.execute("UPDATE tasks SET payload=? WHERE run_id=?", (json.dumps(record, ensure_ascii=False), run_id))

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def find_request(self, request_id):
        with self.lock, self.connect() as connection:
            row = connection.execute("SELECT fingerprint,payload FROM tasks WHERE request_id=?", (request_id,)).fetchone()
            return None if row is None else (row[0], json.loads(row[1]))

    def create(self, record, signature):
        with self.lock, self.connect() as connection:
            connection.execute("INSERT INTO tasks VALUES (?,?,?,?)", (record["run_id"], record["request_id"], signature,
                                                                         json.dumps(record, ensure_ascii=False, allow_nan=False)))

    def get(self, run_id):
        with self.lock, self.connect() as connection:
            row = connection.execute("SELECT payload FROM tasks WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise ValueError("未知 run_id")
            return json.loads(row[0])

    def update(self, run_id, **values):
        with self.lock, self.connect() as connection:
            record = self.get(run_id)
            record.update(values, updated_unix_ns=time.time_ns())
            connection.execute("UPDATE tasks SET payload=? WHERE run_id=?", (json.dumps(record, ensure_ascii=False, allow_nan=False), run_id))
            return record
