from collections.abc import Callable, Generator
from types import ModuleType
from typing import (
    Any,
    ClassVar,
    Self,
    TypeAlias,
    TypedDict,
    TypeVar,
    Unpack,
    cast,
    override,
)

import numpy as np
from numpy.typing import NDArray

__all__ = [
    'Any',
    'Array1D',
    'Array2D',
    'Callable',
    'ClassVar',
    'EleanorKwargs',
    'Generator',
    'ModuleType',
    'NDArray',
    'Number',
    'Self',
    'Species',
    'TypeAlias',
    'TypeVar',
    'TypedDict',
    'Unpack',
    'cast',
    'override',
]

Number: TypeAlias = int | float


class EleanorKwargs(TypedDict, total=False):
    """Options forwarded through the Eleanor / Sailor / AbstractKernel chain.

    These are the keyword arguments that originate at the CLI (or at a
    programmatic caller) and flow as ``**kwargs`` through the forwarding
    methods all the way down to :class:`eleanor.sailor.Sailor` and the
    concrete :class:`eleanor.kernel.interface.AbstractKernel` leaves. Typing
    the bag as a single ``TypedDict`` lets ``pyright`` verify each hop
    without needing ``cast(Callable[..., T], …)`` at every forwarding site.
    """
    verbose: bool
    scratch: bool
    num_procs: int | None
    show_progress: bool
    success_sampling: bool

type Array1D[ScalarT: np.generic] = np.ndarray[tuple[int], np.dtype[ScalarT]]
type Array2D[ScalarT: np.generic] = np.ndarray[tuple[int, int], np.dtype[ScalarT]]

Species: TypeAlias = tuple[list[str], list[str], list[str], list[str], list[str], list[str]]
