from queue import Queue
from tempfile import TemporaryDirectory

from .exceptions import EleanorException
from .hanger.tool_room import WorkingDirectory
from .kernel.interface import AbstractKernel
from .problem import Problem


def sailor(kernel: AbstractKernel, problem: Problem, vs_queue: Queue, es3_queue: Queue, es6_queue: Queue, *args,
           **kwargs) -> None:

    with TemporaryDirectory(prefix="eleanor_") as tempdir:
        with WorkingDirectory(tempdir):
            try:
                es3_result, es6_result = kernel.run(problem, *args, **kwargs)
                vs_queue.put_nowait((0, problem))
                es3_queue.put_nowait(es3_result)
                es6_queue.put_nowait(es6_result)
            except EleanorException as e:
                vs_queue.put_nowait((int(e.code), problem))
