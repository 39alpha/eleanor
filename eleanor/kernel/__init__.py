from eleanor.kernel.interface import AbstractKernel
from eleanor.kernel.registry import registry
from eleanor.kernel.settings import Settings
from eleanor.plugin import load_plugin, load_plugin_settings


def load_kernel_settings(kind: str, raw: dict[str, object]) -> Settings:
    return load_plugin_settings(registry, Settings, kind, raw) or Settings()


def load_kernel(kind: str, settings: object) -> AbstractKernel:
    return load_plugin(registry, AbstractKernel, kind, settings)


__all__ = [
    "AbstractKernel",
    "load_kernel",
    "load_kernel_settings",
]
