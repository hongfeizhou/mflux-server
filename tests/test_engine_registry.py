import pytest
from mflux_server.engines.registry import EngineRegistry
from tests.fakes import FakeEngine


def test_models_aggregates_across_engines():
    reg = EngineRegistry()
    reg.register(FakeEngine(model_name="m1"))
    names = [m.name for m in reg.models()]
    assert "m1" in names


def test_find_model_and_engine_for():
    reg = EngineRegistry()
    engine = FakeEngine(model_name="m1")
    reg.register(engine)
    assert reg.find_model("m1").name == "m1"
    assert reg.find_model("missing") is None
    assert reg.engine_for("m1") is engine


def test_engine_for_unknown_raises():
    reg = EngineRegistry()
    with pytest.raises(KeyError):
        reg.engine_for("missing")
