from ...common import TestCase
from eleanor.hanger.eq36 import Data0
from os.path import abspath, dirname, join, realpath

DATADIR = abspath(join(dirname(realpath(__file__)), '..', '..', 'data'))


class TestData0(TestCase):

    def test_00a(self):
        d0 = Data0.from_file(join(DATADIR, 'db', 'data0.00a'), permissive=True)

    def test_ypf(self):
        d0 = Data0.from_file(join(DATADIR, 'ypf.d0'), permissive=True)
