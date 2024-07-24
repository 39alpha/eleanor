from tempfile import TemporaryDirectory

from .exceptions import EleanorException
from .hanger.tool_room import WorkingDirectory
from .kernel.interface import AbstractKernel
from .models import VSPoint
from .yeoman import Yeoman


def sailor(kernel: AbstractKernel, yeoman: Yeoman, vs_point: VSPoint, *args, **kwargs) -> None:
    with TemporaryDirectory(prefix="eleanor_") as tempdir:
        with WorkingDirectory(tempdir):
            try:
                es_points = kernel.run(vs_point, *args, **kwargs)
                exit_code = 0
            except EleanorException as e:
                es_points = []
                exit_code = e.code

            vs_point.es_points = es_points
            vs_point.exit_code = exit_code
            yeoman.add(vs_point)
