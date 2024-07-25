import os
from sys import exit, stderr

from sqlalchemy import select

from .config import Config
from .exceptions import EleanorException
from .helmsman import Helmsman
from .kernel.interface import AbstractKernel
from .models import HufferResult, Order
from .navigator import UniformNavigator
from .sailor import sailor
from .typing import Self, cast
from .yeoman import Yeoman


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

    def run(self, num_samples: int, *args, **kwargs) -> Self:
        self.kernel.setup(self.config, **kwargs)
        navigator = UniformNavigator(self.config, self.kernel)

        huffer_problem, *_ = navigator.navigate(1, max_attempts=1)
        huffer_point = sailor(self.kernel, None, huffer_problem, *args, scratch=True, **kwargs)
        huffer_result = HufferResult.from_scratch(huffer_point.scratch)

        Yeoman.setup(**kwargs)
        with Yeoman() as yeoman:
            order = Order(self.config, huffer_result)
            result = yeoman.scalar(select(Order).where(Order.hash == order.hash))
            if result is None:
                yeoman.add(order)
                yeoman.commit()
                yeoman.refresh(order)
                order_id = order.id
            else:
                order_id = result.id

        if huffer_point.exit_code != 0:
            raise EleanorException(
                f'Error: the huffer failed',
                code=huffer_point.exit_code,
            )

        helmsman = Helmsman(self.kernel)
        vs_points = navigator.navigate(num_samples, order_id=order_id, max_attempts=1)
        helmsman.run(vs_points, **kwargs)

        return self
