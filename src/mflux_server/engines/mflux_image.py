import inspect
import os
import random
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from mflux_server.engines.base import BaseEngine, GenerationRequest, ModelInfo


@dataclass
class _ModelSpec:
    name: str
    repo_id: str
    family: str
    default_steps: int
    # loader(quantize) -> mflux 模型实例。懒加载：函数体内才 import mflux。
    loader: Callable
    capabilities: list = None  # 例如 ["text-to-image", "image-to-image"]


def _ctor_kwargs(quantize, model_path):
    kwargs = {}
    if quantize:
        kwargs["quantize"] = quantize
    if model_path:
        kwargs["model_path"] = model_path
    return kwargs


def _load_z_image_turbo(quantize, model_path):
    from mflux.models.z_image import ZImageTurbo  # 懒加载，仅 macOS 可用
    return ZImageTurbo(**_ctor_kwargs(quantize, model_path))


def _load_flux2_klein(quantize, model_path):
    from mflux.models.flux2.variants import Flux2Klein
    return Flux2Klein(**_ctor_kwargs(quantize, model_path))


def _load_qwen_image_edit(quantize, model_path):
    from mflux.models.qwen.variants.edit.qwen_image_edit import QwenImageEdit
    return QwenImageEdit(**_ctor_kwargs(quantize, model_path))


# 当前支持的模型表。新增模型 = 在此处加一行 _ModelSpec（机制已完整，无需改其他代码）。
# generate() 会按各模型 generate_image 的真实签名过滤参数，所以不同模型签名差异无需特判。
_SPECS = {
    "z-image-turbo": _ModelSpec(
        name="z-image-turbo", repo_id="Tongyi-MAI/Z-Image-Turbo",
        family="z-image", default_steps=9, loader=_load_z_image_turbo,
        capabilities=["text-to-image", "image-to-image"],
    ),
    "flux2-klein-4b": _ModelSpec(
        name="flux2-klein-4b", repo_id="black-forest-labs/FLUX.2-klein-4B",
        family="flux2", default_steps=4, loader=_load_flux2_klein,
        capabilities=["text-to-image", "image-to-image"],
    ),
    "qwen-image-edit": _ModelSpec(
        name="qwen-image-edit", repo_id="Qwen/Qwen-Image-Edit-2509",
        family="qwen", default_steps=20, loader=_load_qwen_image_edit,
        capabilities=["image-to-image"],
    ),
}


class MfluxImageEngine(BaseEngine):
    id = "mflux-image"

    def __init__(self, models_dir=None):
        self._loaded = {}   # (model_name, quantize, model_path) -> mflux 模型实例
        self._models_dir = Path(models_dir) if models_dir else None

    def models(self) -> list:
        return [
            ModelInfo(name=s.name, family=s.family, engine=self.id,
                      capabilities=(s.capabilities or ["text-to-image"]), repo_id=s.repo_id)
            for s in _SPECS.values()
        ]

    def _local_path(self, model_name: str):
        # models_dir/<repo_id> 存在则用本地权重，否则 None（回退到 mflux 默认下载）
        if not self._models_dir:
            return None
        p = self._models_dir / _SPECS[model_name].repo_id
        return str(p) if p.exists() else None

    def _get_model(self, model_name: str, quantize):
        model_path = self._local_path(model_name)
        key = (model_name, quantize, model_path)
        if key not in self._loaded:
            # 内存有限：加载新模型前清掉旧的
            self._loaded.clear()
            self._loaded[key] = _SPECS[model_name].loader(quantize, model_path)
        return self._loaded[key]

    def generate(self, req: GenerationRequest) -> list:
        spec = _SPECS[req.model]
        model = self._get_model(req.model, req.quantize)
        steps = req.steps if req.steps is not None else spec.default_steps
        params = inspect.signature(model.generate_image).parameters
        accepts_all = any(p.kind == p.VAR_KEYWORD for p in params.values())

        def supported(name):
            return accepts_all or name in params

        images = []
        for i in range(req.n):
            seed = req.seed + i if req.seed is not None else random.randint(0, 2**31 - 1)
            init_path = None
            try:
                kwargs = {"prompt": req.prompt, "seed": seed, "num_inference_steps": steps}
                # 仅传该模型 generate_image 真正接受、且有值的可选参数
                for name, value in (("width", req.width), ("height", req.height),
                                    ("guidance", req.guidance),
                                    ("negative_prompt", req.negative_prompt),
                                    ("image_strength", req.image_strength)):
                    if supported(name) and value is not None:
                        kwargs[name] = value
                if req.init_image is not None:
                    init_path = self._write_init_image(req.init_image)
                    # 编辑类模型用 image_paths(列表)，其余用 image_path
                    if "image_paths" in params:
                        kwargs["image_paths"] = [init_path]
                    elif accepts_all or "image_path" in params:
                        kwargs["image_path"] = init_path
                generated = model.generate_image(**kwargs)
                images.append(self._to_png_bytes(generated))
            finally:
                if init_path is not None:
                    os.unlink(init_path)
        return images

    @staticmethod
    def _write_init_image(data: bytes) -> str:
        fd, tmp = tempfile.mkstemp(suffix=".png")
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        return tmp

    @staticmethod
    def _to_png_bytes(generated) -> bytes:
        # mflux 的 GeneratedImage.save(path) 不会覆盖已存在的文件，所以必须存到一个
        # 尚不存在的路径。用临时目录 + 全新文件名，再读回 PNG 字节，避免耦合其内部类型。
        tmpdir = tempfile.mkdtemp()
        try:
            tmp = os.path.join(tmpdir, "image.png")
            generated.save(tmp)
            return Path(tmp).read_bytes()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
