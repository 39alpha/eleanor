import sys
from contextlib import ExitStack
from dataclasses import replace
from traceback import print_exception
from typing import cast

import click

from eleanor import Eleanor
from eleanor.cli.util import config_from_args, config_options, postgres_sinks
from eleanor.exceptions import EleanorError
from eleanor.executor import load_executor
from eleanor.executor.registry import available_executors
from eleanor.executor.settings import ExecutorSettings
from eleanor.order import load_order
from eleanor.output.interface import AbstractOutputSink
from eleanor.output.null import NullSink, NullSinkSettings
from eleanor.output.postgres.settings import PostgresSinkSettings


def _complete_executor(_ctx: click.Context, _param: click.Parameter, incomplete: str) -> list[str]:
    from eleanor.executor.registry import available_executors

    return [name for name in sorted(available_executors()) if name.startswith(incomplete)]


def _parse_order_ids(tokens: tuple[str, ...]) -> str | dict[str, str] | None:
    """Turn repeated ``--order-id`` values into what :meth:`Eleanor.run` wants."""
    if not tokens:
        return None

    if len(tokens) == 1 and "=" not in tokens[0]:
        return tokens[0]

    parsed: dict[str, str] = {}
    for token in tokens:
        name, separator, value = token.partition("=")
        if not separator or not name:
            msg = f"--order-id {token!r} must be given as SINK=ID when more than one is supplied"
            raise EleanorError(msg)
        if name in parsed:
            msg = f"--order-id given twice for output sink {name!r}"
            raise EleanorError(msg)
        parsed[name] = value
    return parsed


@click.command()
@click.argument("order", type=click.Path(exists=True))
@click.argument("simulation_size", type=click.INT)
@click.option("-n", "--num-workers", type=int, default=None, help="Number of worker processes.")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output.")
@click.option("-s", "--scratch", is_flag=True, help="Save scratch for all systems regardless of error status.")
@click.option("-k", "--kernel-args", multiple=True, help="Arguments to pass to the kernel.")
@click.option(
    "--order-id",
    type=str,
    multiple=True,
    help=(
        "Resume/extend an existing run, as SINK=ID. Repeat once per output sink; "
        "the bare form ID is accepted when only one sink is configured. "
        "The id format is the output sink's own."
    ),
)
@click.option("--tag", type=str, multiple=True, help="Add order tag(s).")
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
@click.option(
    "--timing",
    is_flag=True,
    help="Report a wall-clock attribution of the dispatch loop to stderr when the run finishes.",
)
@config_options()
def run(
    order: str,
    simulation_size: int,
    num_workers: int | None,
    verbose: bool,
    scratch: bool,
    kernel_args: tuple[str, ...],
    order_id: tuple[str, ...],
    tag: tuple[str, ...],
    null_sink: bool,
    bulk_load: bool | None,
    progress: bool,
    executor: str | None,
    chunks_per_worker: int | None,
    batch_size: int | None,
    max_nav_attempts: int,
    timing: bool,
    config: str,
    database: str | None,
) -> None:
    """Run eleanor."""
    kernel_args_list: list[object] = list(kernel_args)
    show_progress = progress and not verbose

    try:
        config_obj = config_from_args(config, database, require_database=not null_sink)

        if bulk_load is not None and not null_sink:
            targets = postgres_sinks(config_obj)
            if not targets:
                cause = (
                    f"got {', '.join(sorted({e.kind for e in config_obj.output}))}"
                    if config_obj.output
                    else "no output sink provided"
                )
                msg = f"--bulk-load is only supported when an output sink has kind 'postgres' ({cause})"
                raise EleanorError(msg)
            for entry in targets:
                entry.settings = replace(
                    cast(PostgresSinkSettings, entry.settings),
                    bulk_load_optimization=bulk_load,
                )

        if executor is None:
            executor = config_obj.executor.kind
        else:
            executors = available_executors()
            if executor not in executors:
                choices = ", ".join(sorted(executors))
                msg = f"unsupported executor {executor!r}; choose from {choices}"
                raise EleanorError(msg)

        if chunks_per_worker is None:
            chunks_per_worker = config_obj.executor.settings.chunks_per_worker

        if executor == config_obj.executor.kind:
            executor_settings = replace(config_obj.executor.settings, chunks_per_worker=chunks_per_worker)
        else:
            executor_settings = ExecutorSettings(chunks_per_worker=chunks_per_worker)

        if num_workers is not None:
            executor_settings = replace(executor_settings, num_workers=num_workers)

        order_obj = load_order(order)
        if tag:
            order_obj.tags = list(dict.fromkeys([*order_obj.tags, *tag]))

        with ExitStack() as stack:
            output_sink: dict[str, AbstractOutputSink[int]] | None = None
            if null_sink:
                sink_settings = NullSinkSettings(support_worker_commit=executor != "serial")
                output_sink = {"null": stack.enter_context(NullSink(sink_settings))}

            executor_obj = stack.enter_context(load_executor(kind=executor, settings=executor_settings))

            with Eleanor(config=config_obj, executor=executor_obj) as eleanor:
                order_ids = eleanor.run(
                    order_obj,
                    simulation_size,
                    kernel_args=kernel_args_list,
                    scratch=scratch,
                    show_progress=show_progress,
                    verbose=verbose,
                    chunks_per_worker=chunks_per_worker,
                    batch_size=batch_size,
                    max_nav_attempts=max_nav_attempts,
                    timing=timing,
                    output_sink=output_sink,
                    resume_id=_parse_order_ids(order_id),
                )

        if verbose:
            for name, allocated in order_ids.items():
                print(f"Order created or extended: {name}={allocated}")
    except KeyboardInterrupt as e:
        name = getattr(e, "signal_name", None) or "interrupt"
        print(f"Eleanor run interrupted by {name}; sink finalized cleanly.")
        sys.exit(130)
    except Exception as e:
        print_exception(e)
