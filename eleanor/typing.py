from typing import *

import numpy as np
from numpy.typing import *

Integer = int | np.integer[Any]

Float = float | np.floating[Any]

Number = Integer | Float

Species = tuple[list[str], list[str], list[str], list[str], list[str], list[str]]
