from .. common import TestCase
from eleanor.hanger.eq36 import Eq36Exception, eqpt, eq3, eq6
from eleanor.hanger.tool_room import WorkingDirectory
from tempfile import TemporaryDirectory
from os.path import abspath, dirname, exists, join, realpath

import os

DATADIR = abspath(join(dirname(realpath(__file__)), '..', 'data'))

class TestEQ36(TestCase):
    """
    Test the eleanor.hanger.eq36 module
    """
    def test_canary(self):
        """
        Ensure that the test suite is running and all that.
        """
        self.assertTrue(True)

    def test_eqpt(self):
        """
        Ensure that running EPQT on a data0 file generates files with the same
        basename and the following extenions in the current working directory;
        :code:`'.po'`, :code:`'.d1'`, :code:`'.s'` and :code:`'.d1f'`.
        """
        cwd = os.getcwd()
        with TemporaryDirectory() as tmpdir:
            self.assertNotEqual(os.getcwd(), tmpdir)
            os.chdir(tmpdir)
            data0 = join(DATADIR, "ymp.d0")

            eqpt(data0)

            for ext in ['.po', '.d1', '.s', '.d1f']:
                fname = join(tmpdir, "ymp" + ext)
                self.assertTrue(exists(fname))

            os.chdir(cwd)

    def test_eq3(self):
        """
        Ensure that running EQ3 on data1 and 3i files generates files with the
        same basename and the following extenions in the current working
        directory; :code:`'.3o'`, :code:`'.3p'`.
        """
        cwd = os.getcwd()
        with TemporaryDirectory() as tmpdir:
            self.assertNotEqual(os.getcwd(), tmpdir)
            os.chdir(tmpdir)
            data1 = join(DATADIR, "ymp.d1")
            threei = join(DATADIR, "acidmwb.3i")

            eq3(data1, threei)

            for ext in ['.3p', '.3o']:
                fname = join(tmpdir, "acidmwb" + ext)
                self.assertTrue(exists(fname))

            os.chdir(cwd)

    def test_eq3_error(self):
        """
        Ensure that running EQ3 on a broken 3i file raises an Eq36Exception.
        """
        with TemporaryDirectory() as tmpdir:
            self.assertNotEqual(os.getcwd(), tmpdir)
            with WorkingDirectory(tmpdir):
                data1 = join(DATADIR, "eq36_error", "test.d1")
                threei = join(DATADIR, "eq36_error", "bad.3i")

                with self.assertRaises(Eq36Exception):
                    eq3(data1, threei)

    def test_eq6(self):
        """
        Ensure that running EQ6 on data1 and 3i files generates files with the
        same basename and the following extenions in the current working
        directory; :code:`'.6o'`, :code:`'.6p'`.
        """
        cwd = os.getcwd()
        with TemporaryDirectory() as tmpdir:
            self.assertNotEqual(os.getcwd(), tmpdir)
            os.chdir(tmpdir)
            data1 = join(DATADIR, "ymp.d1")
            sixi = join(DATADIR, "crisqtz.6i")

            eq6(data1, sixi)

            for ext in ['.6p', '.6o']:
                fname = join(tmpdir, "crisqtz" + ext)
                self.assertTrue(exists(fname))

            os.chdir(cwd)

    def test_eq6_error(self):
        """
        Ensure that running eq6 on a broken 6i file raises an Eq36Exception.
        """
        with TemporaryDirectory() as tmpdir:
            self.assertNotEqual(os.getcwd(), tmpdir)
            with WorkingDirectory(tmpdir):
                data1 = join(DATADIR, "eq36_error", "test.d1")
                sixi = join(DATADIR, "eq36_error", "bad.6i")

                with self.assertRaises(Eq36Exception):
                    eq6(data1, sixi)
