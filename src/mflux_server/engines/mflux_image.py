import os
import random
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from mflux_server.engines.base import BaseEngine, GenerationRequest, ModelInfo


@dataclass
class _ModelSpec:
    name: str
    family: str
    default_steps: int
    # loader(quantize) -> mflux 模型实例。懒加载：函数体内才 import mflux。
    loader: Callable


def _load_z_image_turbo(quantize):
    from mflux.models.z_image import ZImageTurbo  # 懒加载，仅 macOS 可用
    return ZImageTurbo(quantize=quantize) if quantize else ZImageTurbo()


# 当前支持的模型表。新增模型 = 在此处加一行 _ModelSpec（机制已完整，无需改其他代码）。
_SPECS = {
    "z-image-turbo": _ModelSpec(
        name="z-image-turbo", family="z-image", default_steps=9,
        loader=_load_z_image_turbo,
    ),
}


class MfluxImageEngine(BaseEngine):
    id = "mflux-image"

    def __init__(self):
        self._loaded = {}   # (model_name, quantize) -> mflux 模型实例

    def models(self) -> list:
        return [
            ModelInfo(name=s.name, family=s.family, engine=self.id,
                      capabilities=["text-to-image"])
            for s in _SPECS.values()
        ]

    def _get_model(self, model_name: str, quantize):
        key = (model_name, quantize)
        if key not in self._loaded:
            # 内存有限：加载新模型前清掉旧的
            self._loaded.clear()
            self._loaded[key] = _SPECS[model_name].loader(quantize)
        return self._loaded[key]

    def generate(self, req: GenerationRequest) -> list:
        spec = _SPECS[req.model]
        model = self._get_model(req.model, req.quantize)
        steps = req.steps if req.steps is not None else spec.default_steps
        images = []
        for i in range(req.n):
            seed = req.seed + i if req.seed is not None else random.randint(0, 2**31 - 1)
            generated = model.generate_image(
                prompt=req.prompt,
                seed=seed,
                num_inference_steps=steps,
                width=req.width,
                height=req.height,
            )
            images.append(self._to_png_bytes(generated))
        return images

    @staticmethod
    def _to_png_bytes(generated) -> bytes:
        # mflux 返回对象保证有 .save(path)；用临时文件取 PNG 字节，避免耦合其内部类型
        fd, tmp = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            generated.save(tmp)
            return Path(tmp).read_bytes()
        finally:
            os.unlink(tmp)
