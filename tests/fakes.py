import base64
from mflux_server.engines.base import BaseEngine, ModelInfo, GenerationRequest

# 最小合法的 1x1 PNG，用于在不跑真实模型的情况下测试
ONE_PX_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M8AAAMBAQDJ/aPjAAAAAElFTkSuQmCC"
)


class FakeEngine(BaseEngine):
    id = "fake"

    def __init__(self, model_name="fake-model"):
        self.model_name = model_name
        self.calls = []

    def models(self):
        return [ModelInfo(name=self.model_name, family="fake",
                          engine=self.id, capabilities=["text-to-image"])]

    def generate(self, req: GenerationRequest):
        self.calls.append(req)
        return [ONE_PX_PNG for _ in range(req.n)]
