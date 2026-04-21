from eleanor.exceptions import EleanorException

from ..registry import KernelSpec, register_kernel
from .kernel import Kernel
from .settings import Settings

__all__ = ['Kernel', 'Settings']


def _settings_from_dict(raw: dict[str, object]) -> Settings:
    return Settings.from_dict(raw)


def _build(settings: object, *args: object) -> Kernel:
    if not isinstance(settings, Settings):
        raise EleanorException(
            f'eq36 kernel requires eq36 Settings, got {type(settings).__name__}',
        )
    if not args:
        raise EleanorException('eq36 kernel requires a data1_dir argument')
    data1_dir, *rest = args
    if not isinstance(data1_dir, str):
        raise EleanorException(
            f'eq36 kernel requires a string data1_dir, got {type(data1_dir).__name__}',
        )
    # ``rest`` contains any additional positional arguments supplied by the
    # caller (e.g. extra CLI arguments passed via ``Eleanor.kernel_args``).
    # They are forwarded to ``Kernel.__init__`` unvalidated; ``Kernel`` is
    # responsible for rejecting unexpected arguments.
    return Kernel(settings, data1_dir, *rest)


register_kernel('eq36', KernelSpec(settings_from_dict=_settings_from_dict, build=_build))
