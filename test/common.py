import unittest
from os.path import dirname, join, realpath

class TestCase(unittest.TestCase):
    @property
    def data0_dir(self):
        return realpath(join(dirname(__file__), 'data', 'db'))
