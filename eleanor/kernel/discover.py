from importlib import import_module
from pkgutil import iter_modules

import eleanor.kernel
from eleanor.exceptions import EleanorException
from eleanor.typing import ModuleType

kernels = set(name for _, name, ispkg in iter_modules(eleanor.kernel.__path__, eleanor.kernel.__name__ + '.') if ispkg)


def import_kernel_module(kernel_type: str) -> ModuleType:
    kernel_type = kernel_type.lower()
    if not kernel_type.startswith('eleanor.kernel.'):
        kernel_type = 'eleanor.kernel.' + kernel_type

    if kernel_type not in kernels:
        msg = f'unsupported kernel type "{kernel_type}". Installed kernels: {kernels}'
        raise EleanorException(msg)

    return import_module(kernel_type)


def import_all_kernels() -> dict[str, ModuleType]:
    return {kernel_type: import_kernel_module(kernel_type) for kernel_type in kernels}
