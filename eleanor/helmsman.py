import os
import time
from multiprocessing import Manager, Pool, Value
from multiprocessing.managers import SyncManager
from queue import Queue

from .kernel.interface import AbstractKernel
from .problem import Problem
from .sailor import Result, sailor
from .yeoman import Yeoman


class Helmsman:
    kernel: AbstractKernel
    yeoman: Yeoman

    def __init__(self, kernel: AbstractKernel, yeoman: Yeoman):
        self.kernel = kernel
        self.yeoman = yeoman

    def run(self,
            problems: list[Problem],
            num_cores: int | None = os.cpu_count(),
            batch_size: int = 100,
            show_progress: bool = False):

        queue_manager = Manager()
        queue: Queue[Result] = queue_manager.Queue()

        N = len(problems)
        if num_cores is None or num_cores == 1:
            for problem in problems:
                sailor(self.kernel, problem, queue)
            wait = Value('b', False)
            self.yeoman.run(queue, N, batch_size, show_progress)
        else:
            wait = Value('b', True)
            yeoman_process = self.yeoman.fork(queue, N, batch_size, show_progress)

            with Pool(processes=num_cores) as pool:
                pool.starmap(sailor, zip([self.kernel] * N, problems, [queue] * N))

            with wait.get_lock():
                wait.value = False

            yeoman_process.join()
