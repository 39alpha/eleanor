#!/usr/bin/env python
import argparse
import eleanor
import os


def helmsman():
    # Set up the argument parser
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("-c",
                            "--campaign",
                            required=True,
                            type=str,
                            help=".JSON file with the campaign specifications")
    arg_parser.add_argument("-d",
                            "--data0files",
                            required=True,
                            type=str,
                            help="Path from current directory to the location of the data0 files")
    arg_parser.add_argument("-o", "--order", required=False, type=int, help="The order number for this dataset")
    arg_parser.add_argument("-k", "--keep", required=False, type=int, default=100, help="Keep every nth file")
    arg_parser.add_argument("-p",
                            "--procs",
                            required=False,
                            type=int,
                            default=os.cpu_count(),
                            help="Number of processes used for parallel processing")
    arg_parser.add_argument("-q", "--quiet", required=False, action="store_true", help="Suppress console messages")
    arg_parser.add_argument("--no-progress", required=False, action="store_true", help="Disable progress bars")
    cli_args = vars(arg_parser.parse_args())

    my_camp = eleanor.Campaign.from_json(cli_args["campaign"], cli_args["data0files"])
    eleanor.Helmsman(my_camp,
                     ord_id=cli_args["order"],
                     num_cores=cli_args["procs"],
                     keep_every_n_files=cli_args["keep"],
                     quiet=cli_args["quiet"],
                     no_progress=cli_args["no_progress"])


def navigator():
    # Set up the argument parser
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("-c",
                            "--campaign",
                            required=True,
                            type=str,
                            help=".JSON file with the campaign specifications")
    arg_parser.add_argument("-d",
                            "--data0files",
                            required=True,
                            type=str,
                            help="Path from current directory to the location of the data0 files")
    arg_parser.add_argument("-q", "--quiet", required=False, action="store_true", help="Suppress console messages")

    cli_args = vars(arg_parser.parse_args())
    my_camp = eleanor.Campaign.from_json(cli_args["campaign"], cli_args["data0files"])
    my_camp.create_env(verbose=False)
    eleanor.Navigator(my_camp, quiet=cli_args["quiet"])


def combined():

    # Set up the argument parser
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("-c",
                            "--campaign",
                            required=True,
                            type=str,
                            help=".JSON file with the campaign specifications")
    arg_parser.add_argument("-d",
                            "--data0files",
                            required=True,
                            type=str,
                            help="Path from current directory to the location of the data0 files")
    arg_parser.add_argument("-o", "--order", required=False, type=int, help="The order number for this dataset")
    arg_parser.add_argument("-k", "--keep", required=False, type=int, default=100, help="Keep every nth file")
    arg_parser.add_argument("-p",
                            "--procs",
                            required=False,
                            type=int,
                            default=os.cpu_count(),
                            help="Number of processes used for parallel processing")
    arg_parser.add_argument("-q", "--quiet", required=False, action="store_true", help="Suppress console messages")
    arg_parser.add_argument("--no-progress", required=False, action="store_true", help="Disable progress bars")
    cli_args = vars(arg_parser.parse_args())

    my_camp = eleanor.Campaign.from_json(cli_args["campaign"], cli_args["data0files"])
    my_camp.create_env(verbose=False)
    eleanor.Navigator(my_camp, quiet=cli_args["quiet"])
    eleanor.Helmsman(my_camp,
                     ord_id=cli_args["order"],
                     num_cores=cli_args["procs"],
                     keep_every_n_files=cli_args["keep"],
                     quiet=cli_args["quiet"],
                     no_progress=cli_args["no_progress"])
