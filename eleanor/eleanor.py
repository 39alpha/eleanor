import os

from sqlalchemy import select

from .config import Config
from .exceptions import EleanorException
from .helmsman import Helmsman
from .kernel.interface import AbstractKernel
from .models import Order
from .navigator import UniformNavigator
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

        # TODO: Replace this with a call to the sailor and gracefully handle failures
        es3_result, es6_result = self.kernel.run(huffer_problem, *args, **kwargs)

        Yeoman.setup(**kwargs)
        helmsman = Helmsman(self.kernel)

        with Yeoman() as yeoman:
            order = Order(self.config)
            result = yeoman.scalar(select(Order).where(Order.hash == order.hash))
            if result is None:
                yeoman.add(order)
                yeoman.commit()
                yeoman.refresh(order)
                order_id = order.id
            else:
                order_id = result.id

        vs_points = navigator.navigate(num_samples, order_id=order_id, max_attempts=1)
        helmsman.run(vs_points, **kwargs)

        return self
