import argparse
import os

from eleanor import Eleanor


def main():
    num_cpu = os.cpu_count()

    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("-p", "--procs", required=False, type=int, default=num_cpu, help="number of processes")
    arg_parser.add_argument("-v", "--verbose", required=False, action="store_true", help="enable verbose output")
    arg_parser.add_argument("-b", "--batch-size", required=False, type=int, default=100, help="the size of db batches")
    arg_parser.add_argument("--progress", required=False, action="store_true", help="enable progress bars")
    arg_parser.add_argument("campaign", type=str, help="campaign file")
    arg_parser.add_argument("samples", type=int, help="number of samples")
    arg_parser.add_argument('kernel_args', nargs='*')

    args = vars(arg_parser.parse_args())

    campaign = args['campaign']
    kernel_args = args['kernel_args']
    verbose = args['verbose']
    num_cores = args['procs']
    show_progress = args['progress']
    num_samples = args['samples']
    batch_size = args['batch_size']

    eleanor = Eleanor(campaign, *kernel_args)
    eleanor.run(
        num_samples,
        num_cores=num_cores,
        batch_size=batch_size,
        verbose=verbose,
        show_progress=show_progress,
    )
