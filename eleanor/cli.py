import argparse
import os

import ray

from eleanor import Eleanor


def main():
    ray.init()

    num_cpu = int(ray.available_resources()['CPU'])

    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("-s", "--num-sailors", required=False, type=int, default=num_cpu, help="number of sailors")
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
    num_sailors = args['num_sailors']
    show_progress = args['progress']
    num_samples = args['samples']
    batch_size = args['batch_size']

    ref = Eleanor.remote(
        campaign,
        kernel_args,
        num_samples,
        num_sailors=num_sailors,
        batch_size=batch_size,
        verbose=verbose,
        show_progress=show_progress,
    )

    ray.wait([ref])
