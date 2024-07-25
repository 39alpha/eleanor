import os
from sys import exit, stderr

from sqlalchemy import select

from .exceptions import EleanorException
from .helmsman import Helmsman
from .kernel.interface import AbstractKernel
from .navigator import UniformNavigator
from .order import HufferResult, Order
from .sailor import sailor
from .typing import Self, cast
from .yeoman import Yeoman


class Eleanor(object):
    order: Order
    kernel: AbstractKernel

    def __init__(self, order: str | Order, *args, **kwargs):
        if isinstance(order, str):
            self.order = Order.from_file(order)
        else:
            self.order = order

        if self.order.kernel.type == 'eq36':
            from .kernel.eq36 import Config as KernelConfig
            from .kernel.eq36 import Kernel

            self.kernel = Kernel(cast(KernelConfig, self.order.kernel), *args, **kwargs)
        else:
            raise EleanorException(f'unsupported kernel type: "{self.order.kernel.type}"')

    def run(self, num_samples: int, *args, **kwargs) -> Self:
        self.kernel.setup(self.order, **kwargs)
        navigator = UniformNavigator(self.order, self.kernel)

        huffer_problem, *_ = navigator.navigate(1, max_attempts=1)
        huffer_point = sailor(self.kernel, None, huffer_problem, *args, scratch=True, **kwargs)
        self.order.huffer_result = HufferResult.from_scratch(huffer_point.scratch)

        Yeoman.setup(**kwargs)
        with Yeoman() as yeoman:
            result = yeoman.scalar(select(Order).where(Order.hash == self.order.hash))
            if result is None:
                yeoman.add(self.order)
                yeoman.commit()
                yeoman.refresh(self.order)
                order_id = self.order.id
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
