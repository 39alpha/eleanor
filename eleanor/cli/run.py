import argparse
from traceback import print_exception

from eleanor import Eleanor
from eleanor.cli.util import ConfigArgs, add_config_args, config_from_args, typed_args
from eleanor.exceptions import EleanorException
from eleanor.executor import available_executors
from eleanor.order import load_order


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
    combined: bool
    proportional: bool
    success_sampling: bool
    parallel: str | None
    chunks_per_worker: int | None


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
        "-p",
        "--progress",
        required=False,
        action="store_true",
        help="enable progress bars (disabled by --verbose)",
    )
    _ = parser.add_argument(
        "-C",
        "--combined",
        required=False,
        action="store_true",
        help="store suborders as a single order",
    )
    _ = parser.add_argument(
        "-P",
        "--proportional",
        required=False,
        action="store_true",
        help="use proportional sampling",
    )
    _ = parser.add_argument(
        "--success-sampling",
        required=False,
        action="store_true",
        help="sample size counts successes only",
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

    try:
        config = config_from_args(parser, args)
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

        with Eleanor(config, kernel_args, num_procs=args["num_procs"]) as eleanor:
            order_ids = eleanor.run(
                order,
                args["simulation_size"],
                scratch=args["scratch"],
                show_progress=show_progress,
                combined=args["combined"],
                proportional_sampling=args["proportional"],
                success_sampling=args["success_sampling"],
                verbose=args["verbose"],
                parallel=parallel,
                chunks_per_worker=chunks_per_worker,
            )

        if args["verbose"]:
            print("Orders created or extended:", order_ids)
    except Exception as e:
        if args["verbose"]:
            print_exception(e)
        else:
            print(e)
