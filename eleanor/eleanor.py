import os
import queue
import time
from datetime import datetime
from multiprocessing import Manager, Pool, Process, Queue
from sys import exit, stderr

from sqlalchemy import and_, select
from tqdm import tqdm

import eleanor.sailor as sailor
from eleanor.version import __version__

from .config import Config, DatabaseConfig, load_config
from .exceptions import EleanorException
from .kernel.discover import import_kernel_module
from .kernel.interface import AbstractKernel
from .navigator import AbstractNavigator, UniformNavigator
from .order import HufferResult, Order, load_order
from .typing import Any, Optional, Self, cast
from .util import chunks
from .yeoman import Yeoman


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
    no_huffer: bool = False,
    **kwargs,
) -> int:
    if not no_huffer:
        huffer_problem = navigator.select(max_attempts=1)
        huffer_point = sailor.__run(kernel, huffer_problem, *args, scratch=True, **kwargs)
        order.huffer_result = HufferResult.from_scratch(huffer_point.scratch, huffer_point.exit_code)
    else:
        huffer_point = None
        order.huffer_result = None

    with Yeoman(config.database, verbose=verbose) as yeoman:
        yeoman.setup()

        if yeoman.scalar(select(Order).where(Order.eleanor_version != __version__)):  # type: ignore
            raise EleanorException('cannot add order to a database created with a different version of Eleanor')

        result = yeoman.scalar(
            select(Order).where(
                and_(
                    Order.hash == order.hash,  # type: ignore
                    Order.eleanor_version == __version__,  # type: ignore
                )))

        if result is not None:
            order_id = order.id = result.id
            order.eleanor_version = result.eleanor_version

            if order.huffer_result is not None:
                if result.huffer_result is None:
                    result.huffer_result = order.huffer_result
                else:
                    result.huffer_result.exit_code = order.huffer_result.exit_code  # type: ignore
                    result.huffer_result.zip = order.huffer_result.zip  # type: ignore

            yeoman.merge(result)
            yeoman.commit()
        else:
            order.eleanor_version = __version__
            yeoman.add(order)
            yeoman.commit()
            yeoman.refresh(order)
            order_id = order.id

    if huffer_point is not None and not kernel.is_soft_exit(huffer_point.exit_code):
        raise EleanorException(
            f'Error: the huffer failed',
            code=huffer_point.exit_code,
        ) from huffer_point.exception
    elif order_id is None:
        raise EleanorException(f'Error: failed to create the order')

    return order_id


def display_progress(queue: queue.Queue[bool], samples: int):
    progress = tqdm(total=samples, unit=' systems', colour='#ec5c29')
    while samples > 0:
        queue.get()
        progress.update()
        samples -= 1
    progress.close()


def Eleanor(
    config: str | Config,
    order: str | Order,
    kernel_args: list[Any],
    num_samples: int,
    *args,
    num_procs: int | None = None,
    show_progress: bool = False,
    scratch: bool = False,
    **kwargs,
):
    config = load_config(config)
    order = load_order(order)
    kernel = load_kernel(order, kernel_args, **kwargs)

    navigator = UniformNavigator(order, kernel)

    order_id = ignite(config, order, kernel, navigator, *args, **kwargs)

    vs_points = navigator.navigate(num_samples, order_id=order_id, max_attempts=1)

    manager = Manager()

    progress: Optional[queue.Queue[bool]] = None
    progress_proc: Optional[Process] = None
    if show_progress:
        progress = manager.Queue()
        progress_proc = Process(target=display_progress, args=(progress, len(vs_points)))
        progress_proc.start()

    if num_procs is not None and num_procs <= 0:
        num_procs = 1

    with Pool(processes=num_procs) as pool:
        futures = []

        for batch_num, batch in enumerate(chunks(vs_points, pool._processes)):  # type: ignore
            future = pool.apply_async(sailor.sailor, (config.database, kernel, batch, *args), {
                **kwargs,
                'scratch': scratch,
                'progress': progress,
            })
            futures.append(future)

        while futures:
            future = futures.pop()
            future.get()

    if progress_proc is not None:
        progress_proc.join()
