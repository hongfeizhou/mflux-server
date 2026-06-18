import queue as _queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from mflux_server.engines.base import GenerationRequest
from mflux_server.engines.registry import EngineRegistry


@dataclass
class Job:
    id: str
    request: GenerationRequest
    status: str = "queued"           # queued | running | done | error
    result: Optional[list] = None    # list[bytes]
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    done: threading.Event = field(default_factory=threading.Event)


class JobQueue:
    def __init__(self, registry: EngineRegistry):
        self._registry = registry
        self._q: "_queue.Queue[Job]" = _queue.Queue()
        self._jobs = {}
        self._lock = threading.Lock()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._started = False

    def start(self) -> None:
        if not self._started:
            self._started = True
            self._worker.start()

    def submit(self, req: GenerationRequest) -> Job:
        job = Job(id=uuid.uuid4().hex, request=req)
        with self._lock:
            self._jobs[job.id] = job
        self._q.put(job)
        return job

    def wait(self, job: Job, timeout: Optional[float] = None) -> Job:
        job.done.wait(timeout)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def _run(self) -> None:
        while True:
            job = self._q.get()
            job.status = "running"
            try:
                engine = self._registry.engine_for(job.request.model)
                job.result = engine.generate(job.request)
                job.status = "done"
            except Exception as exc:  # noqa: BLE001 - 队列 worker 必须吞掉异常
                job.error = str(exc) or exc.__class__.__name__
                job.status = "error"
            finally:
                job.done.set()
                self._q.task_done()
