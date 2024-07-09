import argparse
import os

from eleanor import Eleanor


def main():
    num_cpu = os.cpu_count()

    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("-c", "--campaign", required=True, type=str, help="campaign file")
    arg_parser.add_argument("-s", "--samples", required=True, type=int, help="number of samples")
    arg_parser.add_argument("-p", "--procs", required=False, type=int, default=num_cpu, help="number of processes")
    arg_parser.add_argument("-v", "--verbose", required=False, action="store_true", help="enable verbose output")
    arg_parser.add_argument("-b", "--batch-size", required=False, type=int, default=100, help="the size of db batches")
    arg_parser.add_argument("--progress", required=False, action="store_true", help="enable progress bars")
    arg_parser.add_argument('kernel', nargs='*')

    args = vars(arg_parser.parse_args())

    eleanor = Eleanor(args['campaign'], *args['kernel'])
    eleanor.setup(verbose=args['verbose'])
    eleanor.run(args['samples'], num_cores=args['procs'], batch_size=args['batch_size'], show_progress=args['progress'])
