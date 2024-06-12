import unittest
import random
import numpy as np
from .common import TestCase
from eleanor import Campaign, Helmsman, Navigator
from eleanor.hanger import db_comms
from tempfile import TemporaryDirectory
from shutil import copytree
from os.path import join


class TestIntegration(TestCase):
    """
    Tests integration between Campaign, Navigator and Helmsmen Classes
    """

    def test_canary(self):
        """
        Confirm that the test case is being run
        """
        self.assertTrue(True)

    def test_is_seedable(self):
        """
        Ensure that we can seed the RNGs and get the same result between runs.
        """

        campaign_json = self.data_path("regression", "campaign.json")
        compaign_data0 = self.data_path("regression", "db")
        camp = Campaign.from_json(campaign_json, compaign_data0)

        vs_1, es3_1, es6_1 = self.worker(camp)
        vs_2, es3_2, es6_2 = self.worker(camp)

        self.assertEqual(vs_1, vs_2)
        self.assertEqual(es3_1, es3_2)
        self.assertEqual(es6_1, es6_2)

    def worker(self, camp):
        """
        Run eleanor on a campaign within a temporary testing directory.
        """
        random.seed(2024)
        np.random.seed(2024)

        with TemporaryDirectory() as root:
            camp.create_env(dir=root, verbose=False)

            Navigator(camp, quiet=True)
            Helmsman(camp, ord_id=None, num_cores=1, keep_every_n_files=1, quiet=True, no_progress=False)

            conn = db_comms.establish_database_connection(camp, verbose=False)

            vs = list(conn.execute('SELECT * FROM vs'))
            es3 = list(conn.execute('SELECT * FROM es3'))
            es6 = list(conn.execute('SELECT * FROM es6'))

            conn.close()

            return (vs, es3, es6)
