from queue import Queue
from tempfile import TemporaryDirectory

from .exceptions import EleanorException
from .hanger.tool_room import WorkingDirectory
from .kernel.interface import AbstractKernel
from .models import ESPoint, VSPoint
from .problem import Problem
from .typing import Float


def sailor(kernel: AbstractKernel, problem: Problem, queue: Queue[VSPoint], *args, **kwargs) -> None:
    with TemporaryDirectory(prefix="eleanor_") as tempdir:
        with WorkingDirectory(tempdir):
            try:
                es_points = kernel.run(problem, *args, **kwargs)
                exit_code = 0
            except EleanorException as e:
                es_points = []
                exit_code = e.code

            vs_point = VSPoint.from_problem(problem)
            vs_point.es_points = es_points
            vs_point.exit_code = exit_code
            queue.put_nowait(vs_point)
