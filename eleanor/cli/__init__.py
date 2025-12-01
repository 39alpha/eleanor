import argparse

import eleanor.cli.huffer as huffer
import eleanor.cli.run as run
import eleanor.cli.schema as schema
import eleanor.cli.scratch as scratch


def main():
    parser = argparse.ArgumentParser(
        prog='eleanor',
        description='Run eleanor or interact with a generated dataset',
        allow_abbrev=True,
    )

    subparsers = parser.add_subparsers(required=True)

    huffer.init(subparsers.add_parser('huffer'))
    run.init(subparsers.add_parser('run'))
    schema.init(subparsers.add_parser('schema'))
    scratch.init(subparsers.add_parser('scratch'))

    args = parser.parse_args()
    return args.func(args)


if __name__ == '__main__':
    main()
