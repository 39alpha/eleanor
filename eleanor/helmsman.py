import os
from multiprocessing import Pool

from .kernel.interface import AbstractKernel
from .problem import Problem
from .sailor import sailor
from .yeoman import Yeoman


class Helmsman:
    kernel: AbstractKernel

    def __init__(self, kernel: AbstractKernel):
        self.kernel = kernel

    def __call__(self, problem: Problem, *args, **kwargs):
        with Yeoman() as yeoman:
            sailor(self.kernel, yeoman, problem, *args, **kwargs)
            yeoman.commit()

    def run(self, problems: list[Problem], *args, num_cores: int | None = os.cpu_count(), **kwargs):
        N = len(problems)
        if num_cores is None or num_cores == 1:
            for problem in problems:
                self(problem, *args, **kwargs)
        else:
            with Pool(processes=num_cores - 1, initializer=Yeoman.dispose) as pool:
                pool.starmap(self, zip(problems, [args] * N, [kwargs] * N))
