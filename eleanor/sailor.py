import io
import os
import zipfile
from datetime import datetime
from os.path import join
from tempfile import TemporaryDirectory

import ray

import eleanor.equilibrium_space as es
import eleanor.variable_space as vs

from .config import DatabaseConfig
from .exceptions import EleanorException
from .kernel.interface import AbstractKernel
from .typing import Optional
from .util import WorkingDirectory
from .yeoman import Yeoman


def collect_scratch(dir: str) -> Optional[vs.Scratch]:
    try:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_BZIP2, allowZip64=True, compresslevel=9) as zip:
            for filename in os.listdir(dir):
                zip.write(join(dir, filename), filename)
        return vs.Scratch(id=None, zip=buffer.getvalue())
    except Exception as e:
        return vs.Scratch(id=None, zip=bytes('\0', 'ascii'))


def __run(
    kernel: AbstractKernel,
    vs_point: vs.Point,
    *args,
    scratch: bool = False,
    **kwargs,
) -> vs.Point:
    with TemporaryDirectory(prefix="eleanor_") as tempdir:
        with WorkingDirectory(tempdir):
            vs_point.start_date = datetime.now()
            es_points: list[es.Point] = []
            try:
                es_points = kernel.run(vs_point, *args, **kwargs)
                if scratch:
                    vs_point.scratch = collect_scratch(tempdir)
                exit_code = 0
            except EleanorException as e:
                print(e)
                exit_code = e.code
                vs_point.scratch = collect_scratch(tempdir)
            except Exception as e:
                print(e)
                exit_code = -1
                vs_point.scratch = collect_scratch(tempdir)

            vs_point.es_points = es_points
            vs_point.exit_code = exit_code
            vs_point.complete_date = datetime.now()

            return vs_point


def sailor_actor(yeoman: ray.actor.ActorHandle, *args, **kwargs):
    vs_point = __run(*args, **kwargs)
    yeoman.write.remote(vs_point)


def sailor_config(config: DatabaseConfig, *args, verbose: bool = False, **kwargs):
    if config.dialect == 'sqlite':
        raise EleanorException('sailors cannot instantiate SQLite3 yeomans; use the YeomanActor')

    vs_point = __run(*args, verbose=verbose, **kwargs)

    with Yeoman(config, verbose=verbose) as yeoman:
        yeoman.write(vs_point)


@ray.remote
def sailor(yeoman_or_config: ray.actor.ActorHandle | DatabaseConfig, *args, **kwargs):
    if isinstance(yeoman_or_config, DatabaseConfig):
        sailor_config(yeoman_or_config, *args, **kwargs)
    else:
        sailor_actor(yeoman_or_config, *args, **kwargs)
