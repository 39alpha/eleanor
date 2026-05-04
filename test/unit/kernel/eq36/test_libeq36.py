from unittest import mock

from eleanor.kernel.eq36.libeq36 import get_libpath, read_data1

from ...common import TestCase


class TestEq36Libeq36(TestCase):
    """
    Tests of selected platform behavior in eleanor.kernel.eq36.libeq36.
    """

    @staticmethod
    def _successful_header_side_effect(*args):
        for i, value in [
            (1, 1),  # ikta_asv
            (2, 1),  # ipbt_asv
            (3, 1),  # ipch_asv
            (4, 1),  # ipcv_asv
            (5, 1),  # jpfc_asv
            (6, 1),  # napa_asv
            (7, 1),  # narx_asv
            (8, 1),  # nata_asv
            (9, 1),  # nbta_asv
            (10, 1),  # ncta_asv
            (11, 1),  # ngta_asv
            (12, 1),  # nlta_asv
            (13, 1),  # nmta_asv
            (14, 1),  # npta_asv
            (15, 1),  # nmuta_asv
            (16, 1),  # nslta_asv
            (17, 1),  # nsta_asv
            (18, 1),  # ntid_asv
            (19, 2),  # ntpr_asv
            (20, 1),  # nxta_asv
        ]:
            args[i]._obj.value = value
        args[-1]._obj.value = 0

    def test_get_libpath_linux_and_darwin(self):
        """
        Ensure supported platforms map to expected shared-library names.
        """
        with mock.patch("platform.system", return_value="Linux"):
            self.assertTrue(get_libpath().endswith("lib/libeq36.so"))

        with mock.patch("platform.system", return_value="Darwin"):
            self.assertTrue(get_libpath().endswith("lib/libeq36.dylib"))

    def test_get_libpath_rejects_unsupported_platforms(self):
        """
        Ensure unsupported platforms are rejected explicitly.
        """
        with mock.patch("platform.system", return_value="Windows"):
            with self.assertRaises(RuntimeError):
                get_libpath()

        with mock.patch("platform.system", return_value="FreeBSD"):
            with self.assertRaises(RuntimeError):
                get_libpath()

    def test_read_data1_open_failure_closes_file(self):
        """
        Ensure read_data1 surfaces open errno failures and still closes the native handle.
        """

        def open_side_effect(_fname, data1_ptr, errno_ptr, _flen):
            data1_ptr._obj.value = 7
            errno_ptr._obj.value = 1

        with (
            mock.patch("eleanor.kernel.eq36.libeq36.open_data1", side_effect=open_side_effect) as open_mock,
            mock.patch("eleanor.kernel.eq36.libeq36.read_header") as header_mock,
            mock.patch("eleanor.kernel.eq36.libeq36.close_data1") as close_mock,
        ):
            with self.assertRaisesRegex(Exception, "failed to open data1 file"):
                read_data1("fake.d1")

        self.assertEqual(open_mock.call_args[0][0], b"fake.d1")
        self.assertEqual(open_mock.call_args[0][3], len(b"fake.d1"))
        header_mock.assert_not_called()
        close_mock.assert_called_once()
        self.assertEqual(close_mock.call_args[0][0].value, 7)

    def test_read_data1_wraps_open_exception_without_close(self):
        """
        Ensure open_data1 exceptions are wrapped and close_data1 is not called.
        """
        with (
            mock.patch(
                "eleanor.kernel.eq36.libeq36.open_data1",
                side_effect=RuntimeError("open exploded"),
            ) as open_mock,
            mock.patch("eleanor.kernel.eq36.libeq36.read_header") as header_mock,
            mock.patch("eleanor.kernel.eq36.libeq36.close_data1") as close_mock,
        ):
            with self.assertRaisesRegex(Exception, "failed to open data1 file") as cm:
                read_data1("broken-open.d1")

        open_mock.assert_called_once()
        header_mock.assert_not_called()
        close_mock.assert_not_called()
        self.assertIsInstance(cm.exception.__cause__, RuntimeError)
        self.assertEqual(str(cm.exception.__cause__), "open exploded")

    def test_read_data1_wraps_open_oserror_without_close(self):
        """
        Ensure non-RuntimeError open failures are wrapped and still do not call close_data1.
        """
        with (
            mock.patch(
                "eleanor.kernel.eq36.libeq36.open_data1",
                side_effect=OSError("open os error"),
            ) as open_mock,
            mock.patch("eleanor.kernel.eq36.libeq36.read_header") as header_mock,
            mock.patch("eleanor.kernel.eq36.libeq36.close_data1") as close_mock,
        ):
            with self.assertRaisesRegex(Exception, "failed to open data1 file") as cm:
                read_data1("broken-open-oserror.d1")

        open_mock.assert_called_once()
        header_mock.assert_not_called()
        close_mock.assert_not_called()
        self.assertIsInstance(cm.exception.__cause__, OSError)
        self.assertEqual(str(cm.exception.__cause__), "open os error")

    def test_read_data1_header_failure_closes_file(self):
        """
        Ensure header errno failures are raised and cleanup uses the opened handle.
        """

        def open_side_effect(_fname, data1_ptr, _errno_ptr, _flen):
            data1_ptr._obj.value = 11

        def header_side_effect(*args):
            args[-1]._obj.value = 3

        with (
            mock.patch("eleanor.kernel.eq36.libeq36.open_data1", side_effect=open_side_effect) as open_mock,
            mock.patch("eleanor.kernel.eq36.libeq36.read_header", side_effect=header_side_effect) as header_mock,
            mock.patch("eleanor.kernel.eq36.libeq36.read_body") as body_mock,
            mock.patch("eleanor.kernel.eq36.libeq36.close_data1") as close_mock,
        ):
            with self.assertRaisesRegex(Exception, "failed to read data1 header"):
                read_data1("fake.d1")

        open_mock.assert_called_once()
        header_mock.assert_called_once()
        body_mock.assert_not_called()
        close_mock.assert_called_once()
        self.assertEqual(close_mock.call_args[0][0].value, 11)

    def test_read_data1_success_path_returns_expected_structure(self):
        """
        Ensure successful mocked reads call into body parser and return expected payload shape.
        """
        with (
            mock.patch("eleanor.kernel.eq36.libeq36.open_data1") as open_mock,
            mock.patch(
                "eleanor.kernel.eq36.libeq36.read_header",
                side_effect=self._successful_header_side_effect,
            ) as header_mock,
            mock.patch("eleanor.kernel.eq36.libeq36.read_body") as body_mock,
            mock.patch("eleanor.kernel.eq36.libeq36.close_data1") as close_mock,
        ):
            data = read_data1("ok.d1")

        open_mock.assert_called_once()
        header_mock.assert_called_once()
        body_mock.assert_called_once()
        close_mock.assert_called_once()
        self.assertEqual(float(data.min_temperature), 0.0)
        self.assertEqual(data.max_temperature_range.tolist(), [0.0, 0.0])
        self.assertEqual(int(data.nxrn1a), -1)
        self.assertEqual(int(data.nxrn2a), -1)

    def test_read_data1_wraps_header_exception_and_closes_file(self):
        """
        Ensure hard exceptions from read_header are wrapped with cause and cleanup uses opened handle.
        """

        def open_side_effect(_fname, data1_ptr, _errno_ptr, _flen):
            data1_ptr._obj.value = 13

        with (
            mock.patch("eleanor.kernel.eq36.libeq36.open_data1", side_effect=open_side_effect) as open_mock,
            mock.patch(
                "eleanor.kernel.eq36.libeq36.read_header",
                side_effect=RuntimeError("header exploded"),
            ) as header_mock,
            mock.patch("eleanor.kernel.eq36.libeq36.read_body") as body_mock,
            mock.patch("eleanor.kernel.eq36.libeq36.close_data1") as close_mock,
        ):
            with self.assertRaisesRegex(Exception, "failed to read data1 header") as cm:
                read_data1("bad-header.d1")

        open_mock.assert_called_once()
        header_mock.assert_called_once()
        body_mock.assert_not_called()
        close_mock.assert_called_once()
        self.assertEqual(close_mock.call_args[0][0].value, 13)
        self.assertIsInstance(cm.exception.__cause__, RuntimeError)
        self.assertEqual(str(cm.exception.__cause__), "header exploded")

    def test_read_data1_wraps_body_exception_and_closes_file(self):
        """
        Ensure hard exceptions from read_body are wrapped with cause and cleanup uses opened handle.
        """

        def open_side_effect(_fname, data1_ptr, _errno_ptr, _flen):
            data1_ptr._obj.value = 17

        with (
            mock.patch("eleanor.kernel.eq36.libeq36.open_data1", side_effect=open_side_effect) as open_mock,
            mock.patch(
                "eleanor.kernel.eq36.libeq36.read_header",
                side_effect=self._successful_header_side_effect,
            ) as header_mock,
            mock.patch(
                "eleanor.kernel.eq36.libeq36.read_body",
                side_effect=RuntimeError("body exploded"),
            ) as body_mock,
            mock.patch("eleanor.kernel.eq36.libeq36.close_data1") as close_mock,
        ):
            with self.assertRaisesRegex(Exception, "failed to read data1 body") as cm:
                read_data1("bad-body.d1")

        open_mock.assert_called_once()
        header_mock.assert_called_once()
        body_mock.assert_called_once()
        close_mock.assert_called_once()
        self.assertEqual(close_mock.call_args[0][0].value, 17)
        self.assertIsInstance(cm.exception.__cause__, RuntimeError)
        self.assertEqual(str(cm.exception.__cause__), "body exploded")

    def test_read_data1_non_ascii_filename_raises_encode_error(self):
        """
        Ensure non-ASCII filenames preserve ascii-encoding failure behavior.
        """
        with mock.patch("eleanor.kernel.eq36.libeq36.open_data1") as open_mock:
            with self.assertRaises(UnicodeEncodeError):
                read_data1("μ.d1")
        open_mock.assert_not_called()

    def test_read_data1_raises_when_errno_set_by_read_body(self):
        """
        Ensure read_data1 raises when read_body sets a nonzero errno and cleanup uses opened handle.
        """

        def open_side_effect(_fname, data1_ptr, _errno_ptr, _flen):
            data1_ptr._obj.value = 19

        def body_sets_errno(*args):
            args[-1]._obj.value = 99

        with (
            mock.patch("eleanor.kernel.eq36.libeq36.open_data1", side_effect=open_side_effect) as open_mock,
            mock.patch(
                "eleanor.kernel.eq36.libeq36.read_header",
                side_effect=self._successful_header_side_effect,
            ) as header_mock,
            mock.patch("eleanor.kernel.eq36.libeq36.read_body", side_effect=body_sets_errno) as body_mock,
            mock.patch("eleanor.kernel.eq36.libeq36.close_data1") as close_mock,
        ):
            with self.assertRaisesRegex(Exception, "failed to read data1 body"):
                read_data1("errno-after-body.d1")

        open_mock.assert_called_once()
        header_mock.assert_called_once()
        body_mock.assert_called_once()
        close_mock.assert_called_once()
        self.assertEqual(close_mock.call_args[0][0].value, 19)
