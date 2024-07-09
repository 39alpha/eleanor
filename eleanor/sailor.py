from queue import Queue
from tempfile import TemporaryDirectory

from .exceptions import EleanorException
from .hanger.tool_room import WorkingDirectory
from .kernel.interface import AbstractKernel
from .problem import Problem
from .typing import Float

Result = tuple[Problem, dict[str, Float] | None, dict[str, Float] | None, int]


def sailor(kernel: AbstractKernel, problem: Problem, queue: Queue[Result], *args, **kwargs) -> None:
    with TemporaryDirectory(prefix="eleanor_") as tempdir:
        with WorkingDirectory(tempdir):
            try:
                es3_result, es6_result = kernel.run(problem, *args, **kwargs)
                queue.put_nowait((problem, es3_result, es6_result, 0))
            except EleanorException as e:
                queue.put_nowait((problem, None, None, int(e.code)))
