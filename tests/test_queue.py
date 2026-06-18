import threading
import time
from mflux_server.queue import JobQueue
from mflux_server.engines.base import GenerationRequest
from mflux_server.engines.registry import EngineRegistry
from tests.fakes import FakeEngine, ONE_PX_PNG


def _registry():
    reg = EngineRegistry()
    reg.register(FakeEngine(model_name="fake-model"))
    return reg


def test_submit_and_wait_returns_result():
    q = JobQueue(_registry())
    q.start()
    job = q.submit(GenerationRequest(model="fake-model", prompt="hi", n=2))
    q.wait(job, timeout=5)
    assert job.status == "done"
    assert job.result == [ONE_PX_PNG, ONE_PX_PNG]


def test_unknown_model_marks_job_error():
    q = JobQueue(_registry())
    q.start()
    job = q.submit(GenerationRequest(model="nope", prompt="hi"))
    q.wait(job, timeout=5)
    assert job.status == "error"
    assert job.error


def test_jobs_run_serially_in_submit_order():
    order = []

    class SlowEngine(FakeEngine):
        def generate(self, req):
            order.append(req.prompt)
            time.sleep(0.05)
            return super().generate(req)

    reg = EngineRegistry()
    reg.register(SlowEngine(model_name="fake-model"))
    q = JobQueue(reg)
    q.start()
    jobs = [q.submit(GenerationRequest(model="fake-model", prompt=str(i))) for i in range(3)]
    for j in jobs:
        q.wait(j, timeout=5)
    assert order == ["0", "1", "2"]


def test_get_and_list():
    q = JobQueue(_registry())
    q.start()
    job = q.submit(GenerationRequest(model="fake-model", prompt="hi"))
    q.wait(job, timeout=5)
    assert q.get(job.id) is job
    assert job in q.list()
