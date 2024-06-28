from typing import cast

from .config import Config
from .exceptions import EleanorException
from .kernel.interface import AbstractKernel


class Eleanor(object):
    config: Config
    kernel: AbstractKernel

    def __init__(self, config: str | Config, *args, **kwargs):
        if isinstance(config, str):
            self.config = Config.from_file(config)
        else:
            self.config = config

        if self.config.kernel.type == 'eq36':
            from .kernel.eq36 import Config as KernelConfig
            from .kernel.eq36 import Kernel

            self.kernel = Kernel(cast(KernelConfig, self.config.kernel), *args, **kwargs)
        else:
            raise EleanorException(f'unsupported kernel type: "{self.config.kernel.type}"')

    def setup(self, *args, **kwargs):
        self.kernel.setup(*args, **kwargs)
