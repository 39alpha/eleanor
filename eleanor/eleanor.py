import os
from sys import exit, stderr

import ray
from sqlalchemy import select

from .config import Config
from .exceptions import EleanorException
from .kernel.discover import import_kernel_module
from .kernel.interface import AbstractKernel
from .navigator import AbstractNavigator, UniformNavigator
from .order import HufferResult, Order
from .sailor import sailor
from .typing import Any, Optional, Self, cast
from .yeoman import Yeoman


def load_config(config: Optional[str | Config]) -> Config:
    if config is None:
        config = Config()
    elif isinstance(config, str):
        config = Config.from_file(config)

    return cast(Config, config)


def load_order(order: str | Order) -> Order:
    if isinstance(order, str):
        order = Order.from_file(order)

    return cast(Order, order)


def load_kernel(order: Order, kernel_args: list[Any], **kwargs) -> tuple[AbstractKernel, ray.ObjectRef]:
    kernel_module = import_kernel_module(order.kernel.type)
    kernel = kernel_module.Kernel(order.kernel, *kernel_args)
    kernel.setup(order, **kwargs)

    return kernel, ray.put(kernel)


def ignite(config: Config, order: Order, kernel_ref: ray.ObjectRef, navigator: AbstractNavigator, *args,
           **kwargs) -> int:
    huffer_problem = navigator.select(max_attempts=1)
    huffer_point = ray.get(sailor.remote(kernel_ref, None, huffer_problem, *args, scratch=True, **kwargs))
    order.huffer_result = HufferResult.from_scratch(huffer_point.scratch)

    Yeoman.setup(config.database, **kwargs)
    with Yeoman() as yeoman:
        result = yeoman.scalar(select(Order).where(Order.hash == order.hash))
        if result is None:
            yeoman.add(order)
            yeoman.commit()
            yeoman.refresh(order)
            order_id = order.id
        else:
            order_id = result.id

    if order_id is None:
        raise EleanorException(
            f'Error: the huffer failed',
            code=huffer_point.exit_code,
        )

    if huffer_point.exit_code != 0:
        raise EleanorException(
            f'Error: the huffer failed',
            code=huffer_point.exit_code,
        )

    return order_id


@ray.remote
def Eleanor(config: str | Config, order: str | Order, kernel_args: list[Any], num_samples: int, *args, **kwargs):
    config = load_config(config)
    order = load_order(order)
    kernel, kernel_ref = load_kernel(order, kernel_args, **kwargs)

    navigator = UniformNavigator(order, kernel)

    order_id = ignite(config, order, kernel_ref, navigator, *args, **kwargs)

    vs_points = navigator.navigate(num_samples, order_id=order_id, max_attempts=1)
    results = [sailor.remote(kernel_ref, None, point, *args, **kwargs) for point in vs_points]
    while results:
        _, results = ray.wait(results)
