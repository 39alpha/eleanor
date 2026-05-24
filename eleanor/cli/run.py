import sys
from contextlib import ExitStack
from traceback import print_exception

import click

from eleanor import Eleanor
from eleanor.cli.util import config_from_args, config_options
from eleanor.exceptions import EleanorException
from eleanor.executor import load_executor
from eleanor.executor.registry import available_executors
from eleanor.order import load_order
from eleanor.output.interface import OutputSink
from eleanor.output.null import NullConfig, NullSink


def _complete_executor(_ctx: click.Context, _param: click.Parameter, incomplete: str) -> list[str]:
    from eleanor.executor.registry import available_executors

    return [name for name in sorted(available_executors()) if name.startswith(incomplete)]


@click.command()
@click.argument("order", type=click.Path(exists=True))
@click.argument("simulation_size", type=click.INT)
@click.option("-n", "--num-procs", type=int, default=None, help="Number of processes.")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output.")
@click.option("-s", "--scratch", is_flag=True, help="Save scratch for all sailors.")
@click.option("-k", "--kernel-args", multiple=True, help="Arguments to pass to the kernel.")
@click.option("--order-id", type=int, default=None, help="Override the order id.")
@click.option("--tag", type=str, default=None, help="Override the order tag.")
@click.option("--null-sink", is_flag=True, help="Override config output sink with NullSink.")
@click.option(
    "--bulk-load/--no-bulk-load",
    default=None,
    help=(
        "Override bulk-load optimization on the postgres sink "
        "(--bulk-load enables, --no-bulk-load disables; default: use config file)."
    ),
)
@click.option("-p", "--progress", is_flag=True, help="Enable progress bars (disabled by --verbose).")
@click.option(
    "--executor",
    default=None,
    metavar="KIND",
    envvar="ELEANOR_EXECUTOR",
    shell_complete=_complete_executor,
    help="Executor kind (overrides configuration).",
)
@click.option("--chunks-per-worker", type=int, default=None, help="Chunks per worker (overrides configuration).")
@click.option("--batch-size", type=int, default=None, help="Navigator batch size.")
@click.option("--max-nav-attempts", type=click.IntRange(min=1), default=1, help="Max attempts per navigation point.")
@config_options()
def run(
    order: str,
    simulation_size: int,
    num_procs: int | None,
    verbose: bool,
    scratch: bool,
    kernel_args: tuple[str, ...],
    order_id: int | None,
    tag: str | None,
    null_sink: bool,
    bulk_load: bool | None,
    progress: bool,
    executor: str | None,
    chunks_per_worker: int | None,
    batch_size: int | None,
    max_nav_attempts: int,
    config: str,
    database: str | None,
) -> None:
    """Run eleanor."""
    kernel_args_list: list[object] = list(kernel_args)
    show_progress = progress and not verbose

    try:
        config_obj = config_from_args(config, database, require_database=not null_sink)
        if bulk_load is not None and not null_sink:
            if config_obj.output.kind != "postgres":
                cause = (
                    f'got "{config_obj.output.kind}"'
                    if config_obj.output.kind is not None
                    else "no output sink provided"
                )
                raise EleanorException(f'--bulk-load is only supported when output.kind == "postgres" ({cause})')
            config_obj.output.args["bulk_load_optimization"] = bulk_load
        if executor is None:
            executor = config_obj.executor.kind
        else:
            executors = available_executors()
            if executor not in executors:
                choices = ", ".join(sorted(executors))
                raise EleanorException(
                    f'unsupported executor "{executor}"; choose from {choices}',
                )
        if chunks_per_worker is None:
            chunks_per_worker = config_obj.executor.chunks_per_worker

        order_obj = load_order(order)
        if order_id is not None:
            order_obj.id = order_id
        if tag is not None:
            order_obj.tag = tag

        with ExitStack() as stack:
            output_sink: OutputSink | None = None
            if null_sink:
                output_sink = stack.enter_context(NullSink(NullConfig(support_worker_writes=executor != "serial")))
            executor_obj = stack.enter_context(load_executor(kind=executor, num_workers=num_procs))
            with Eleanor(config=config_obj, kernel_args=kernel_args_list, executor=executor_obj) as eleanor:
                order_ids = eleanor.run(
                    order_obj,
                    simulation_size,
                    scratch=scratch,
                    show_progress=show_progress,
                    verbose=verbose,
                    chunks_per_worker=chunks_per_worker,
                    batch_size=batch_size,
                    max_nav_attempts=max_nav_attempts,
                    output_sink=output_sink,
                )

        if verbose:
            print("Orders created or extended:", order_ids)
    except KeyboardInterrupt as e:
        name = getattr(e, "signal_name", None) or "interrupt"
        print(f"Eleanor run interrupted by {name}; sink finalized cleanly.")
        sys.exit(130)
    except Exception as e:
        if verbose:
            print_exception(e)
        else:
            print(e)
