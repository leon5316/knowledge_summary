"""知识总结与拓扑内核。"""
__version__ = "0.1.0"

from .pipeline import PipelineResult, run  # noqa: F401

__all__ = ["run", "PipelineResult", "__version__"]
