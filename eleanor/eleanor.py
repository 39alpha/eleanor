import os
import time
from datetime import datetime
from sys import exit, stderr

import ray
from sqlalchemy import and_, select

import eleanor.sailor as sailor
from eleanor.version import __version__

from .config import Config, DatabaseConfig, load_config
from .exceptions import EleanorException
from .kernel.discover import import_kernel_module
from .kernel.interface import AbstractKernel
from .navigator import AbstractNavigator, UniformNavigator
from .order import HufferResult, Order, load_order
from .typing import Any, Optional, Self, cast
from .yeoman import Yeoman
from .yeoman_actor import YeomanActor


def load_kernel(order: Order, kernel_args: list[Any], **kwargs) -> AbstractKernel:
    kernel_module = import_kernel_module(order.kernel.type)
    kernel = kernel_module.Kernel(order.kernel, *kernel_args)
    kernel.setup(order, **kwargs)

    return kernel


def ignite(
    config: Config,
    order: Order,
    kernel: AbstractKernel,
    navigator: AbstractNavigator,
    *args,
    verbose: bool = False,
    new_order: bool = False,
    **kwargs,
) -> int:
    huffer_problem = navigator.select(max_attempts=1)
    huffer_point = sailor.__run(kernel, huffer_problem, *args, scratch=True, **kwargs)
    order.huffer_result = HufferResult.from_scratch(huffer_point.scratch)

    with Yeoman(config.database, verbose=verbose) as yeoman:
        yeoman.setup()

        result = yeoman.scalar(
            select(Order).where(
                and_(
                    Order.hash == order.hash,  # type: ignore
                    Order.eleanor_version == __version__,  # type: ignore
                    Order.kernel_version == kernel.version(),  # type: ignore
                )))

        if result is not None:
            order_id = order.id = result.id
            order.eleanor_version = result.eleanor_version
            order.kernel_version = result.kernel_version
        else:
            result = yeoman.scalar(select(Order).where(Order.hash == order.hash))  # type: ignore
            if result is not None and not new_order:
                raise EleanorException(
                    f'cannot extend order {result.id} with eleanor {__version__} and kernel {kernel.version()}')
            else:
                order.eleanor_version = __version__
                order.kernel_version = kernel.version()
                yeoman.add(order)
                yeoman.commit()
                yeoman.refresh(order)
                order_id = order.id

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


def Eleanor(
    config: str | Config,
    order: str | Order,
    kernel_args: list[Any],
    num_samples: int,
    *args,
    new_order: bool = False,
    **kwargs,
):
    config = load_config(config)
    order = load_order(order)
    kernel = load_kernel(order, kernel_args, **kwargs)

    kernel_ref = ray.put(kernel)

    navigator = UniformNavigator(order, kernel)

    order_id = ignite(config, order, kernel, navigator, *args, new_order=new_order, **kwargs)

    if config.database.dialect == 'sqlite':
        yeoman_or_config: ray.actor.ActorHandle | DatabaseConfig = YeomanActor.remote(  # type: ignore
            config.database,
            num_samples,
            **kwargs,
        )
    else:
        yeoman_or_config = config.database

    vs_points = navigator.navigate(num_samples, order_id=order_id, max_attempts=1)
    results = [sailor.sailor.remote(yeoman_or_config, kernel_ref, point, *args, **kwargs) for point in vs_points]
    while results:
        _, results = ray.wait(results)

    if not isinstance(yeoman_or_config, DatabaseConfig):
        wait_duration = num_samples / 50
        started_waiting = datetime.now()
        lock = [yeoman_or_config.is_done.remote()]
        while lock:
            is_done, lock = ray.wait(lock)
            if is_done and is_done[0]:
                break

            elapsed = (datetime.now() - started_waiting).total_seconds()
            if elapsed < wait_duration:
                print(f'WARNING: exited after waiting {elapsed}s for the yeoman to complete', file=stderr)
                break

            time.sleep(1)
            lock = [yeoman_or_config.is_done.remote()]
