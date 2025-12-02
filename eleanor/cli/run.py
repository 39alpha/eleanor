import argparse

from eleanor import Eleanor
from eleanor.cli.util import add_config_args, config_from_args


def init(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.description = 'Run eleanor'

    parser.add_argument('-n', '--num-procs', required=False, type=int, help='number of processes')
    parser.add_argument('-v', '--verbose', required=False, action='store_true', help='enable verbose output')
    parser.add_argument('-s', '--scratch', required=False, action='store_true', help='save scratch for all sailors')
    parser.add_argument('-k', '--kernel-args', required=False, action='append', help='arguments to pass to the kernel')
    parser.add_argument('--progress', required=False, action='store_true', help='enable progress bars')
    parser.add_argument('--no-huffer', required=False, action='store_true', help='disable the huffer')
    parser.add_argument('--success-sampling',
                        required=False,
                        action='store_true',
                        help='sample size counts success only')
    parser.add_argument('order', type=str, help='order file')
    parser.add_argument('simulation_size', type=int, help='the size of the simulation')

    add_config_args(parser)

    parser.set_defaults(func=execute)

    return parser


def execute(ns: argparse.Namespace):
    args = vars(ns)

    order = args['order']
    kernel_args = args['kernel_args']
    no_huffer = args['no_huffer']
    num_procs = args['num_procs']
    simulation_size = args['simulation_size']
    scratch = args['scratch']
    show_progress = args['progress']
    success_sampling = args['success_sampling']
    verbose = args['verbose']

    config = config_from_args(args)

    ids = Eleanor.run(
        config,
        order,
        kernel_args,
        simulation_size,
        no_huffer=no_huffer,
        num_procs=num_procs,
        scratch=scratch,
        show_progress=show_progress,
        success_sampling=success_sampling,
        verbose=verbose,
    )
    print(ids)
