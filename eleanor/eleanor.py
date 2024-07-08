import os

from .config import Config
from .exceptions import EleanorException
from .helmsman import Helmsman
from .kernel.interface import AbstractKernel
from .navigator import UniformNavigator
from .problem import Problem
from .typing import Self, cast
from .yeoman import Yeoman


class Eleanor(object):
    config: Config
    kernel: AbstractKernel
    yeoman: Yeoman
    navigator: UniformNavigator
    helmsman: Helmsman

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

    def setup(self, dbpath: str | None = None, *args, **kwargs) -> Self:
        problem = Problem.from_config(self.config)

        self.kernel.setup(problem, *args, **kwargs)
        self.navigator = UniformNavigator(self.kernel)

        huffer_problem, *_ = self.navigator.navigate(problem, 1)
        self.kernel.run(huffer_problem, *args, **kwargs)

        self.yeoman = Yeoman(dbpath)
        self.helmsman = Helmsman(self.kernel, self.yeoman)

        return self

    def run(self, num_samples: int, *args, **kwargs):
        base_problem = Problem.from_config(self.config)
        problems = self.navigator.navigate(base_problem, num_samples)
        self.helmsman.run(problems, *args, **kwargs)
