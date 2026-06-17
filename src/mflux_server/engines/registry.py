from typing import Optional
from mflux_server.engines.base import BaseEngine, ModelInfo


class EngineRegistry:
    def __init__(self):
        self._engines = {}          # engine_id -> BaseEngine
        self._model_index = {}      # model_name -> engine_id

    def register(self, engine: BaseEngine) -> None:
        self._engines[engine.id] = engine
        for info in engine.models():
            self._model_index[info.name] = engine.id

    def models(self) -> list:
        out = []
        for engine in self._engines.values():
            out.extend(engine.models())
        return out

    def find_model(self, name: str) -> Optional[ModelInfo]:
        for info in self.models():
            if info.name == name:
                return info
        return None

    def engine_for(self, model_name: str) -> BaseEngine:
        return self._engines[self._model_index[model_name]]
