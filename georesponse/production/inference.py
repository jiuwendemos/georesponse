"""Real ONNX inference with NPU-aware provider selection.

The model is the damage-likelihood head exported from the trained logistic
classifier.  It runs on whatever provider the runtime exposes: CANN/Ascend,
OpenVINO NPU, QNN, CoreML, CUDA or CPU.  If no model or runtime exists, it
fails loudly instead of returning simulated scores.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np

from ..detection import change_map, cloud_cover, load_rgb
from ..models import FEATURES
from .config import InferenceSettings, get_settings

try:
    import onnxruntime as ort
except Exception:  # pragma: no cover - optional dependency
    ort = None  # type: ignore


class InferenceUnavailable(RuntimeError):
    pass


PREFERRED = [
    "CANNExecutionProvider",
    "OpenVINOExecutionProvider",
    "QNNExecutionProvider",
    "VitisAIExecutionProvider",
    "CoreMLExecutionProvider",
    "CUDAExecutionProvider",
    "CPUExecutionProvider",
]
NPU_PROVIDERS = {"CANNExecutionProvider", "OpenVINOExecutionProvider", "QNNExecutionProvider", "VitisAIExecutionProvider"}


class OnnxDamageModel:
    def __init__(self, settings: InferenceSettings | None = None) -> None:
        self.settings = settings or get_settings().inference
        if ort is None:
            raise InferenceUnavailable("onnxruntime is not installed")
        if not Path(self.settings.model_path).exists():
            raise InferenceUnavailable(f"ONNX model not found: {self.settings.model_path}")
        available = ort.get_available_providers()
        if self.settings.providers == "auto":
            providers = [name for name in PREFERRED if name in available] or ["CPUExecutionProvider"]
        else:
            requested = [item.strip() for item in self.settings.providers.split(",") if item.strip()]
            providers = [name for name in requested if name in available]
            if not providers:
                raise InferenceUnavailable(f"requested providers unavailable: {requested}; available: {available}")
        self.available = available
        self.providers = providers
        self.session = ort.InferenceSession(self.settings.model_path, providers=providers)
        self.input_name = self.session.get_inputs()[0].name

    @property
    def device(self) -> str:
        return "npu" if any(provider in NPU_PROVIDERS for provider in self.providers) else "cpu" if self.providers == ["CPUExecutionProvider"] else "accelerator"

    def predict(self, rows: Iterable[dict]) -> list[float]:
        matrix = np.array([[float(row.get(name, 0.0)) for name in FEATURES] for row in rows], dtype=np.float32)
        output = self.session.run(None, {self.input_name: matrix})[0]
        return [float(value[0] if hasattr(value, "__len__") else value) for value in output]

    def health(self) -> dict:
        return {
            "runtime": "onnxruntime",
            "providers": self.providers,
            "available": self.available,
            "device": self.device,
            "model": self.settings.model_path,
            "npu": self.device == "npu",
        }


def infer_tile_pair(
    before_path: str | Path,
    after_path: str | Path,
    *,
    value_eur: float = 0.0,
    population: float = 0.0,
    access: str = "clear",
    sar: float = 0.0,
    model: OnnxDamageModel | None = None,
) -> dict:
    model = model or OnnxDamageModel()
    before = load_rgb(before_path)
    after = load_rgb(after_path)
    mask = change_map(before, after)
    extent = float(mask.mean())
    cloud = cloud_cover(after)
    signal = min(1.0, extent * 4 + (1 - cloud) * 0.25)
    row = {
        "extent": min(1.0, extent * 2),
        "confidence": signal,
        "cloud": cloud,
        "sar": sar,
        "value": min(1.0, value_eur / 10_000_000),
        "population": min(1.0, population / 2500),
        "access": {"blocked": 1.0, "flooded": 0.9, "restricted": 0.7, "debris": 0.8, "slow": 0.55, "clear": 0.15}.get(access, 0.5),
    }
    probability = model.predict([row])[0]
    return {
        "probability": round(probability, 4),
        "features": row,
        "changeFraction": round(extent, 4),
        "cloud": round(cloud, 4),
        "device": model.device,
        "providers": model.providers,
        "note": "Damage-likelihood head over observable change features; imagery CNN is a production swap.",
    }


def service_health() -> dict:
    settings = get_settings().inference
    try:
        model = OnnxDamageModel(settings)
        return {"ok": True, **model.health()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "model": settings.model_path, "availableProviders": ort.get_available_providers() if ort else []}
