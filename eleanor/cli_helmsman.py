#!/usr/bin/env python
import argparse
import eleanor

if __name__ == "__main__":
    # Set up the argument parser
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("-c", "--campaign", required=True, type=str,
                            help=".JSON file with the campaign specifications")
    arg_parser.add_argument("-d", "--data0files", required=True, type=str,
                            help="Path from current directory to the location of the data0 files")
    arg_parser.add_argument("-o", "--order", required=False, type=int,
                            help="The order number for this dataset")
    cli_args = vars(arg_parser.parse_args())
    if not cli_args.get("order",None):
        order = 1
        # TODO: Come up with a function to grab the highest un-run order
    my_camp = eleanor.Campaign.from_json(cli_args["campaign"], cli_args["data0files"])
    eleanor.Helmsman(my_camp, order)
