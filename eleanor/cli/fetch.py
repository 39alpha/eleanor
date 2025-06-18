#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
from copy import deepcopy
from dataclasses import asdict
from getpass import getpass

from eleanor.config import DatabaseConfig, load_config


def main():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument(
        '-c',
        '--config',
        required=False,
        type=str,
        default=os.path.expanduser('~/.config/eleanor/local.yaml'),
        help='the database configuration file to use',
    )
    arg_parser.add_argument(
        '-r',
        '--remote-database',
        required=False,
        type=str,
        help='override the remote database from the configuration file',
    )
    arg_parser.add_argument(
        '-l',
        '--local-database',
        required=False,
        type=str,
        help='override the local database (default: --remote-database)',
    )

    args = vars(arg_parser.parse_args())

    config_path = os.path.expanduser(args['config'])
    remote_database = args['remote_database']
    local_database = args['local_database']

    print(f'Loading {args["config"]}')
    config = load_config(config_path).database

    if remote_database is not None:
        kwargs = asdict(config)
        kwargs.update({'database': remote_database})
        config = DatabaseConfig(**kwargs)

    if local_database is None:
        local_database = config.database

    password = getpass(prompt='Local PostgreSQL Password: ')

    ps = subprocess.Popen(
        ['psql', '-d', 'postgres'],
        env={
            **os.environ,
            'PGPASSWORD': password,
        },
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    ps.communicate(input=f'DROP DATABASE {local_database}; CREATE DATABASE {local_database};', )

    fetch = subprocess.Popen(
        [
            'pg_dump', '--no-owner', '-h', (config.host or ''), '-U', (config.username or ''), '-d',
            (config.database or '')
        ],
        env={
            **os.environ,
            'PGPASSWORD': config.password or '',
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    env = deepcopy(os.environ)
    env['PGPASSWORD'] = password
    load = subprocess.Popen(
        ['psql', '-d', local_database],
        env={
            **os.environ, 'PGPASSWORD': password
        },
        stdin=fetch.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = load.communicate()

    if stderr:
        print(str(stderr, 'utf-8'), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
