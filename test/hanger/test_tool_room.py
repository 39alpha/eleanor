from .. common import TestCase
import eleanor.hanger.tool_room as tr
import os
from os.path import realpath, join
from tempfile import TemporaryDirectory

class TestToolRoom(TestCase):
    """
    Tests of the eleanor.hanger.tool_room module
    """

    def test_canary(self):
        """
        Confirm that the test case is being run
        """
        self.assertTrue(True)

    def test_working_directory(self):
        """
        Ensure that :class:`WorkingDirectory` changes directory to the desired path and back again.
        """
        cwd = os.getcwd()
        new_dir = realpath(join(cwd, '..'))

        wd = tr.WorkingDirectory('..')

        self.assertEquals(wd.path, new_dir)
        self.assertEquals(wd.cwd, cwd)

        with wd as new_cwd:
            self.assertEquals(new_cwd, new_dir)
            self.assertEquals(os.getcwd(), new_cwd)
            self.assertEquals(wd.path, cwd)

        self.assertEquals(os.getcwd(), cwd)
        self.assertEquals(wd.path, new_dir)
        self.assertEquals(wd.cwd, cwd)

    def test_working_directory_nonexistant_directory(self):
        """
        Ensure that if you try to switch to a non-existant directory, the properties of the
        :class:`WorkingDirectory` do not change.
        """
        cwd = os.getcwd()

        wd = tr.WorkingDirectory('not-real')

        self.assertEquals(wd.path, join(cwd, 'not-real'))
        self.assertEquals(wd.cwd, cwd)

        with self.assertRaises(FileNotFoundError):
            with wd:
                pass

        self.assertEquals(os.getcwd(), cwd)
        self.assertEquals(wd.path, join(cwd, 'not-real'))
        self.assertEquals(wd.cwd, cwd)

    def test_working_directory_handles_error(self):
        """
        Ensure that if the :class:`WorkingDirectory` code block raises, we switch back to the
        previous working directory.
        """
        cwd = os.getcwd()

        wd = tr.WorkingDirectory('..')

        self.assertEquals(wd.path, realpath(join(cwd, '..')))
        self.assertEquals(wd.cwd, cwd)

        with self.assertRaises(ValueError):
            with wd:
                raise ValueError('whomp')

        self.assertEquals(os.getcwd(), cwd)
        self.assertEquals(wd.path, realpath(join(cwd, '..')))
        self.assertEquals(wd.cwd, cwd)

    def test_working_directory_can_be_nested(self):
        """
        Ensure that the :class:`WorkingDirectory` context manager can be nested.
        """
        cwd0 = os.getcwd()
        with TemporaryDirectory() as root:
            self.assertNotEquals(root, cwd0)
            os.mkdir(join(root, "abc"))
            with tr.WorkingDirectory(root) as cwd1:
                self.assertEquals(os.getcwd(), root)
                self.assertEquals(cwd1, root)
                with tr.WorkingDirectory("abc") as cwd2:
                    self.assertEquals(os.getcwd(), join(root, "abc"))
                    self.assertEquals(cwd2, join(root, "abc"))
                self.assertEquals(os.getcwd(), root)
            self.assertEquals(os.getcwd(), cwd0)
