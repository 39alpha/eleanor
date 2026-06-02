from eleanor.kernel.interface import AbstractKernel
from eleanor.kernel.registry import registry
from eleanor.kernel.settings import KernelSettings
from eleanor.plugin import load_plugin, load_plugin_settings


def load_kernel_settings(kind: str, raw: dict[str, object]) -> KernelSettings:
    return load_plugin_settings(registry, KernelSettings, kind, raw) or KernelSettings()


def load_kernel(kind: str, settings: object) -> AbstractKernel:
    return load_plugin(registry, AbstractKernel, kind, settings)


__all__ = [
    "AbstractKernel",
    "load_kernel",
    "load_kernel_settings",
]
