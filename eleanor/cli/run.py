import argparse

from eleanor import Eleanor


def main():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("-p", "--num-procs", required=False, type=int, help="number of processes")
    arg_parser.add_argument("-v", "--verbose", required=False, action="store_true", help="enable verbose output")
    arg_parser.add_argument("-s", "--scratch", required=False, action="store_true", help="save scratch for all sailors")
    arg_parser.add_argument("-b", "--batch-size", required=False, type=int, default=100, help="the size of db batches")
    arg_parser.add_argument("-c", "--config", required=False, type=str, help="path to the configuration file")
    arg_parser.add_argument("--progress", required=False, action="store_true", help="enable progress bars")
    arg_parser.add_argument("--no-huffer", required=False, action="store_true", help="disable the huffer")
    arg_parser.add_argument("--success-sampling",
                            required=False,
                            action="store_true",
                            help="sample size counts success only")
    arg_parser.add_argument("campaign", type=str, help="campaign file")
    arg_parser.add_argument("samples", type=int, help="number of samples")
    arg_parser.add_argument('kernel_args', nargs='*')

    args = vars(arg_parser.parse_args())

    batch_size = args['batch_size']
    campaign = args['campaign']
    config = args['config']
    kernel_args = args['kernel_args']
    no_huffer = args['no_huffer']
    num_procs = args['num_procs']
    num_samples = args['samples']
    scratch = args['scratch']
    show_progress = args['progress']
    success_sampling = args['success_sampling']
    verbose = args['verbose']

    Eleanor(
        config,
        campaign,
        kernel_args,
        num_samples,
        batch_size=batch_size,
        no_huffer=no_huffer,
        num_procs=num_procs,
        scratch=scratch,
        show_progress=show_progress,
        success_sampling=success_sampling,
        verbose=verbose,
    )
