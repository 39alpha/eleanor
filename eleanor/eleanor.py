import os
import time
from datetime import datetime
from multiprocessing import Manager, Pool, Process
from queue import Queue
from sys import exit, stderr
from traceback import print_exception

from sqlalchemy import and_, select

import eleanor.sailor as sailor
import eleanor.variable_space as vs

from .config import Config, DatabaseConfig, load_config
from .exceptions import EleanorException
from .kernel.discover import import_kernel_module
from .kernel.interface import AbstractKernel
from .navigator import AbstractNavigator
from .order import HufferResult, Order, load_order
from .typing import Any, Optional, Self, cast
from .util import Progress, chunks
from .version import __version__
from .yeoman import Yeoman


def load_kernel(order: Order, kernel_args: list[Any], **kwargs) -> AbstractKernel:
    kernel_module = import_kernel_module(order.kernel.type)
    kernel = kernel_module.Kernel(order.kernel.settings, *kernel_args)
    kernel.setup(order, **kwargs)

    return kernel


def ignite(
    config: Config,
    order: Order,
    *args,
    huffer_with: Optional[tuple[AbstractKernel, AbstractNavigator]] = None,
    verbose: bool = False,
    **kwargs,
) -> int:
    if huffer_with is not None:
        kernel, navigator = huffer_with
        huffer_problem = navigator.huffer_problem()
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


def count_successes(config: DatabaseConfig, order_id: int) -> int:
    with Yeoman(config) as yeoman:
        successes = yeoman.query(vs.Point).filter(
            and_(
                vs.Point.exit_code == 0,  # type: ignore
                vs.Point.order_id == order_id,  # type: ignore
            )).count()
        return successes


def process_batch(pool,
                  config: DatabaseConfig,
                  kernel: AbstractKernel,
                  navigator: AbstractNavigator,
                  simulation_size: int,
                  order_id: int,
                  *args,
                  scratch: bool = False,
                  success_sampling: bool = False,
                  progress: Optional[Queue[bool]] = None,
                  **kwargs):
    vs_points = navigator.navigate(simulation_size, order_id=order_id, max_attempts=1)

    futures = []
    for batch_num, batch in enumerate(chunks(vs_points, pool._processes)):  # type: ignore
        future = pool.apply_async(sailor.sailor, (config, kernel, batch, *args), {
            **kwargs,
            'scratch': scratch,
            'progress': progress,
            'success_only_progress': success_sampling,
        })
        futures.append(future)

    while futures:
        future = futures.pop()
        future.get()


def prepare(config, order, kernel_args, **kwargs):
    config = load_config(config)
    order = load_order(order)
    kernel = load_kernel(order, kernel_args, **kwargs)
    navigator = order.navigator.load()(order, kernel)

    return config, order, kernel, navigator


def _run(
    config: Config,
    order: Order,
    kernel: AbstractKernel,
    navigator: AbstractNavigator,
    simulation_size: int,
    *args,
    no_huffer: bool = False,
    num_procs: int | None = None,
    show_progress: bool = False,
    scratch: bool = False,
    success_sampling: bool = False,
    verbose: bool = False,
    order_id: Optional[int] = None,
    combined: bool = False,
    proportional_sampling: bool = False,
    **kwargs,
):
    if order_id is None:
        huffer_with = None
        if not no_huffer:
            huffer_with = (kernel, navigator)
        order_id = ignite(config, order, *args, verbose=verbose, huffer_with=huffer_with, **kwargs)

    manager = Manager()

    if show_progress:
        progress = Progress(manager, navigator.num_systems(simulation_size))

    if num_procs is not None and num_procs <= 0:
        num_procs = 1

    with Pool(processes=num_procs) as pool:
        if success_sampling:
            successes = count_successes(config.database, order_id)
            target_samples = successes + simulation_size

            while successes < target_samples:
                process_batch(pool,
                              config.database,
                              kernel,
                              navigator,
                              target_samples - successes,
                              order_id,
                              *args,
                              scratch=scratch,
                              success_sampling=success_sampling,
                              progress=progress.queue,
                              verbose=verbose,
                              **kwargs)

                successes = count_successes(config.database, order_id)
        else:
            process_batch(pool,
                          config.database,
                          kernel,
                          navigator,
                          simulation_size,
                          order_id,
                          *args,
                          scratch=scratch,
                          success_sampling=success_sampling,
                          progress=progress.queue,
                          verbose=verbose,
                          **kwargs)

    if progress is not None:
        progress.join()

    return [order_id]


def Eleanor(
    config: str | Config,
    order: str | Order,
    kernel_args: list[Any],
    simulation_size: int,
    *args,
    no_huffer: bool = False,
    num_procs: int | None = None,
    show_progress: bool = False,
    scratch: bool = False,
    success_sampling: bool = False,
    verbose: bool = False,
    order_id: Optional[int] = None,
    combined: bool = False,
    proportional_sampling: bool = False,
    **kwargs,
) -> list[int]:
    order = load_order(order)

    if order.suborders is not None and len(order.suborders.suborders) != 0:
        order_ids: set[int] = set()

        suborders = order.split_suborders()
        combined = combined or order.suborders.combined
        proportional_sampling = proportional_sampling or order.suborders.proportional_sampling

        order_id = None
        if combined:
            config = load_config(config)
            order_id = ignite(config, order, *args, verbose=verbose, **kwargs)

        volume = order.volume()

        for suborder in suborders:
            suborder_samples = simulation_size
            if proportional_sampling:
                suborder_samples = round(suborder_samples * suborder.volume() / volume)

            try:
                suborder_ids = Eleanor(
                    config,
                    suborder,
                    kernel_args,
                    suborder_samples,
                    *args,
                    no_huffer=no_huffer,
                    num_procs=num_procs,
                    show_progress=show_progress,
                    scratch=scratch,
                    success_sampling=success_sampling,
                    verbose=verbose,
                    order_id=order_id,
                    combined=combined,
                    proportional_sampling=proportional_sampling,
                    **kwargs,
                )
                order_ids.update(suborder_ids)
            except Exception as e:
                print("Error: suborder failed", file=stderr)
                print_exception(e, file=stderr)

        return sorted(order_ids)

    config = load_config(config)
    kernel = load_kernel(order, kernel_args, verbose=verbose, **kwargs)
    navigator = order.navigator.load()(order, kernel)

    return _run(
        config,
        order,
        kernel,
        navigator,
        simulation_size,
        *args,
        no_huffer=no_huffer,
        num_procs=num_procs,
        show_progress=show_progress,
        scratch=scratch,
        success_sampling=success_sampling,
        verbose=verbose,
        order_id=order_id,
        combined=combined,
        proportional_sampling=proportional_sampling,
        **kwargs,
    )
