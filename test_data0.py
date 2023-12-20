import sys
from eleanor.hanger.eq36 import Data0

data0 = Data0.from_file(sys.argv[1], permissive=False)
print(data0.fname)
print(data0.magic)
