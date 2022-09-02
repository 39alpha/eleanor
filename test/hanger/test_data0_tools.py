from .. common import TestCase
import eleanor.hanger.data0_tools as data0

class TestData0Tools(TestCase):
    """
    Tests of the eleanor.hanger.data0_tools module
    """

    def test_canary(self):
        """
        Confirm that the test case is being run
        """
        self.assertTrue(True)

    def test_canonical_d0_name(self):
        self.assertEqual(data0.canonical_d0_name('apple.d0'), 'apple.d0')
        self.assertEqual(data0.canonical_d0_name('apple.txt'), 'apple_txt.d0')
        self.assertEqual(data0.canonical_d0_name('apple.'), 'apple.d0')
        self.assertEqual(data0.canonical_d0_name('apple'), 'apple.d0')

        self.assertEqual(data0.canonical_d0_name('apple.txt.d0'), 'apple.txt.d0')
        self.assertEqual(data0.canonical_d0_name('apple.txt.txt'), 'apple.txt_txt.d0')
        self.assertEqual(data0.canonical_d0_name('apple.txt.'), 'apple.txt.d0')

        self.assertEqual(data0.canonical_d0_name('/abc/apple.d0'), '/abc/apple.d0')
        self.assertEqual(data0.canonical_d0_name('/abc/apple.txt'), '/abc/apple_txt.d0')
        self.assertEqual(data0.canonical_d0_name('/abc/apple.'), '/abc/apple.d0')
        self.assertEqual(data0.canonical_d0_name('/abc/apple'), '/abc/apple.d0')

        self.assertEqual(data0.canonical_d0_name('abc/apple.d0'), 'abc/apple.d0')
        self.assertEqual(data0.canonical_d0_name('abc/apple.txt'), 'abc/apple_txt.d0')
        self.assertEqual(data0.canonical_d0_name('abc/apple.'), 'abc/apple.d0')
        self.assertEqual(data0.canonical_d0_name('abc/apple'), 'abc/apple.d0')
