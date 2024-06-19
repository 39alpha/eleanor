import unittest
from os.path import abspath, dirname, join, realpath

from eleanor.hanger.eq36 import Data0

from ...common import TestCase


class TestData0(TestCase):

    def test_00a(self):
        d0 = Data0.from_file(self.data0_path('data0.00a'), permissive=True)

    @unittest.skip('Handling of complex species/solid names is borked')
    def test_ypf(self):
        d0 = Data0.from_file(self.data0_path('ypf.d0'), permissive=True)
