import os
import time
from multiprocessing import Manager, Pool, Value
from multiprocessing.managers import SyncManager

from .kernel.interface import AbstractKernel
from .problem import Problem
from .sailor import sailor
from .yeoman import Yeoman


class Helmsman:
    kernel: AbstractKernel
    yeoman: Yeoman
    queue_manager: SyncManager

    def __init__(self, kernel: AbstractKernel, yeoman: Yeoman):
        self.kernel = kernel
        self.yeoman = yeoman
        self.queue_manager = Manager()

    def run(self, problems: list[Problem], num_cores: int | None = os.cpu_count(), progress: bool = False):
        vs_queue = self.queue_manager.Queue()
        es3_queue = self.queue_manager.Queue()
        es6_queue = self.queue_manager.Queue()

        N = len(problems)
        if num_cores is None or num_cores == 1:
            for problem in problems:
                sailor(self.kernel, problem, vs_queue, es3_queue, es6_queue)
            wait = Value('b', False)
            self.yeoman.run(wait, vs_queue, es3_queue, es6_queue, N, progress)
        else:
            wait = Value('b', True)
            yeoman_process = self.yeoman.fork(wait, vs_queue, es3_queue, es6_queue, N, progress)

            with Pool(processes=num_cores) as pool:
                pool.starmap(sailor, zip([self.kernel] * N, problems, [vs_queue] * N, [es3_queue] * N, [es6_queue] * N))

            with wait.get_lock():
                wait.value = False

            yeoman_process.join()
