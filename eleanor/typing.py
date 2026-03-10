from types import *  # pyright: ignore[reportWildcardImportFromLibrary]
from typing import *  # pyright: ignore[reportWildcardImportFromLibrary]

import numpy as np
from numpy.typing import *  # pyright: ignore[reportWildcardImportFromLibrary]

Number: TypeAlias = int | float

type Array1D[ScalarT: np.generic] = np.ndarray[tuple[int], np.dtype[ScalarT]]
type Array2D[ScalarT: np.generic] = np.ndarray[tuple[int, int], np.dtype[ScalarT]]

Species: TypeAlias = tuple[list[str], list[str], list[str], list[str], list[str], list[str]]
