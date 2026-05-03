import argparse
from traceback import print_exception

from eleanor import Eleanor
from eleanor.cli.util import ConfigArgs, add_config_args, config_from_args, typed_args
from eleanor.exceptions import EleanorException
from eleanor.executor import available_executors, load_executor
from eleanor.order import load_order
from eleanor.output.null import NullConfig, NullSink


class RunArgs(ConfigArgs):
    """Argparse fields accepted by the ``run`` command."""

    order: str
    order_id: int | None
    tag: str | None
    simulation_size: int
    num_procs: int | None
    verbose: bool
    scratch: bool
    kernel_args: list[str] | None
    progress: bool
    null_sink: bool
    parallel: str | None
    chunks_per_worker: int | None
    batch_size: int | None
    max_nav_attempts: int


def init(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.description = "Run eleanor"

    _ = parser.add_argument("-n", "--num-procs", required=False, type=int, help="number of processes")
    _ = parser.add_argument("-v", "--verbose", required=False, action="store_true", help="enable verbose output")
    _ = parser.add_argument("-s", "--scratch", required=False, action="store_true", help="save scratch for all sailors")
    _ = parser.add_argument(
        "-k", "--kernel-args", required=False, action="append", help="arguments to pass to the kernel"
    )
    _ = parser.add_argument("--order-id", required=False, type=int, help="override the order id")
    _ = parser.add_argument("--tag", required=False, type=str, help="override the order tag")
    _ = parser.add_argument(
        "--null-sink",
        required=False,
        action="store_true",
        help="override config output sink with NullSink (useful for tests/benchmarks)",
    )
    _ = parser.add_argument(
        "-p",
        "--progress",
        required=False,
        action="store_true",
        help="enable progress bars (disabled by --verbose)",
    )
    _ = parser.add_argument(
        "--parallel",
        required=False,
        metavar="BACKEND",
        help=(
            "parallel backend (overrides configuration). Built-in backends are "
            "serial and multiprocessing; additional backends may be "
            'contributed by third-party packages via the "eleanor.executors" '
            "entry-point group."
        ),
    )
    _ = parser.add_argument(
        "--chunks-per-worker",
        required=False,
        type=int,
        help="number of chunks per worker (overrides configuration)",
    )
    _ = parser.add_argument(
        "--batch-size",
        required=False,
        type=int,
        help="navigator batch size (default: all points in one batch)",
    )
    _ = parser.add_argument(
        "--max-nav-attempts",
        required=False,
        type=int,
        default=1,
        help="max attempts per navigation point before failing (default: %(default)s)",
    )
    _ = parser.add_argument("order", type=str, help="order file")
    _ = parser.add_argument("simulation_size", type=int, help="the size of the simulation")

    add_config_args(parser)

    parser.set_defaults(func=execute)

    return parser


def execute(parser: argparse.ArgumentParser, ns: argparse.Namespace) -> None:
    args = typed_args(RunArgs, ns)

    kernel_args: list[object] = list(args["kernel_args"] or [])
    show_progress = args["progress"] and not args["verbose"]
    parallel = args["parallel"]
    chunks_per_worker = args["chunks_per_worker"]
    batch_size = args["batch_size"]
    max_nav_attempts = args["max_nav_attempts"]
    null_sink = args["null_sink"]

    try:
        config = config_from_args(parser, args, require_database=not null_sink)
        if parallel is None:
            parallel = config.parallel.backend
        else:
            executors = available_executors()
            if parallel not in executors:
                choices = ", ".join(sorted(executors))
                raise EleanorException(
                    f'unsupported executor "{parallel}"; choose from {choices}',
                )
        if chunks_per_worker is None:
            chunks_per_worker = config.parallel.chunks_per_worker

        order = load_order(args["order"])
        if args["order_id"] is not None:
            order.id = args["order_id"]
        if args["tag"] is not None:
            order.tag = args["tag"]

        output_sink = NullSink(NullConfig(support_worker_writes=parallel != "serial")) if null_sink else None

        with load_executor(kind=parallel, num_workers=args["num_procs"]) as executor:
            with Eleanor(config, kernel_args, executor=executor) as eleanor:
                order_ids = eleanor.run(
                    order,
                    args["simulation_size"],
                    scratch=args["scratch"],
                    show_progress=show_progress,
                    verbose=args["verbose"],
                    parallel=parallel,
                    chunks_per_worker=chunks_per_worker,
                    batch_size=batch_size,
                    max_nav_attempts=max_nav_attempts,
                    output_sink=output_sink,
                )

        if args["verbose"]:
            print("Orders created or extended:", order_ids)
    except Exception as e:
        if args["verbose"]:
            print_exception(e)
        else:
            print(e)
