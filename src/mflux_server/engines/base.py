from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GenerationRequest:
    model: str
    prompt: str
    n: int = 1
    width: int = 1024
    height: int = 1024
    steps: Optional[int] = None
    guidance: Optional[float] = None
    seed: Optional[int] = None
    lora: list = field(default_factory=list)
    quantize: Optional[int] = None
    init_image: Optional[bytes] = None
    image_strength: Optional[float] = None
    negative_prompt: Optional[str] = None


@dataclass
class ModelInfo:
    name: str
    family: str
    engine: str
    capabilities: list
    repo_id: Optional[str] = None


class BaseEngine(ABC):
    id: str = "base"

    @abstractmethod
    def models(self) -> list:
        """返回该引擎支持的 ModelInfo 列表。"""

    @abstractmethod
    def generate(self, req: GenerationRequest) -> list:
        """同步执行生成，返回 PNG 字节列表（长度 == req.n）。"""
