from eleanor.campaign import Campaign
from eleanor.hanger.tool_room import Six_i, IOPT_4
from tempfile import NamedTemporaryFile, TemporaryDirectory
from os.path import isdir, isfile, join, realpath
import json
import os
from .common import TestCase


class TestCampaign(TestCase):
    """
    Tests of the eleanor.campaign module
    """

    def setUp(self):
        """
        Setup the tests
        """
        self.config = {
            'campaign': 'CSS0',
            'est_date': '4Dec2021',
            'notes': 'template',
            'creator': '39A',
            'mode': 'Reaction EQ',
            'initial fluid constraints': {
                'T_cel': [0.5, 6],
                'P_bar': [4, 6],
                'fO2': [-20, -1],
                'cb': 'Cl-',
                'basis': {
                    'H+': [-7, -9],
                    'Na+': 0.4860597,
                    'Mg+2': 0.0547421,
                    'Ca+2': [0.008, 0.012],
                    'K+': 0.0105797,
                    'Sr+2': 0.0000940,
                    'Cl-': 0.5657647,
                    'SO4-2': 0.0292643,
                    'HCO3-': 0.0020380,
                    'Br-': 0.0008728,
                    'B(OH)3': 0.0004303,
                    'F-': 0.0000708
                }
            },
            'reactant': {
                'CO2(g)': ['gas', [-7, -0.5], 1]
            },
            'vs_distro': 'BF',
            'resolution': 4,
            'suppress min': True,
            'suppress min exemptions': ['calcite'],
            'solid solutions': True,
            'suppress sp': [],
        }

    def test_canary(self):
        """
        Confirm that the test case is being run
        """
        self.assertTrue(True)

    def test_init_with_solid_solution(self):
        """
        Ensure that campaigns can be initialized to use solid solutions
        """
        camp = Campaign(self.config, self.data0_dir)

        self.assertEqual(camp.data0_dir, self.data0_dir)
        self.assertEqual(camp._raw, self.config)

        self.assertEqual(camp.name, self.config['campaign'])
        self.assertEqual(camp.notes, self.config['notes'])
        self.assertEqual(camp.est_date, self.config['est_date'])
        self.assertEqual(camp.target_rnt, self.config['reactant'])
        self.assertEqual(camp.suppress_min, self.config['suppress min'])
        self.assertEqual(camp.min_supp_exemp, self.config['suppress min exemptions'])
        self.assertEqual(camp.cb, 'Cl-')
        self.assertEqual(camp.vs_state, {'T_cel': [0.5, 6], 'P_bar': [4, 6], 'fO2': [-20, -1]})
        self.assertEqual(camp.vs_basis, self.config['initial fluid constraints']['basis'])
        self.assertEqual(camp.distro, self.config['vs_distro'])
        self.assertEqual(camp.reso, self.config['resolution'])
        self.assertEqual(camp.SS, self.config['solid solutions'])

        self.assertIsInstance(camp.local_6i, Six_i)
        self.assertEqual(camp.local_6i.switches['iopt_4'], IOPT_4.PERMIT_SS)
        self.assertEqual(camp.local_6i.suppress_min, self.config['suppress min'])
        self.assertEqual(camp.local_6i.min_supp_exemp, self.config['suppress min exemptions'])

    def test_init_without_solid_solution(self):
        """
        Ensure that campaigns can be initalized without solid solutions
        """
        self.config['solid solutions'] = False

        camp = Campaign(self.config, self.data0_dir)

        self.assertEqual(camp.data0_dir, self.data0_dir)
        self.assertEqual(camp._raw, self.config)

        self.assertEqual(camp.name, self.config['campaign'])
        self.assertEqual(camp.notes, self.config['notes'])
        self.assertEqual(camp.est_date, self.config['est_date'])
        self.assertEqual(camp.target_rnt, self.config['reactant'])
        self.assertEqual(camp.suppress_min, self.config['suppress min'])
        self.assertEqual(camp.min_supp_exemp, self.config['suppress min exemptions'])
        self.assertEqual(camp.cb, 'Cl-')
        self.assertEqual(camp.vs_state, {'T_cel': [0.5, 6], 'P_bar': [4, 6], 'fO2': [-20, -1]})
        self.assertEqual(camp.vs_basis, self.config['initial fluid constraints']['basis'])
        self.assertEqual(camp.distro, self.config['vs_distro'])
        self.assertEqual(camp.reso, self.config['resolution'])
        self.assertEqual(camp.SS, self.config['solid solutions'])

        self.assertIsInstance(camp.local_6i, Six_i)
        self.assertEqual(camp.local_6i.switches['iopt_4'], IOPT_4.IGNORE_SS)
        self.assertEqual(camp.local_6i.suppress_min, self.config['suppress min'])
        self.assertEqual(camp.local_6i.min_supp_exemp, self.config['suppress min exemptions'])

    def test_load_from_json(self):
        """
        Ensure that a campaign can be loaded from a JSON-formatted file.
        """
        with NamedTemporaryFile(mode='w+') as handle:
            json.dump(self.config, handle, indent=True)
            handle.seek(0)
            camp = Campaign.from_json(handle.name, self.data0_dir)

        self.assertEqual(camp.data0_dir, self.data0_dir)
        self.assertEqual(camp._raw, self.config)

        self.assertEqual(camp.name, self.config['campaign'])
        self.assertEqual(camp.notes, self.config['notes'])
        self.assertEqual(camp.est_date, self.config['est_date'])
        self.assertEqual(camp.target_rnt, self.config['reactant'])
        self.assertEqual(camp.suppress_min, self.config['suppress min'])
        self.assertEqual(camp.min_supp_exemp, self.config['suppress min exemptions'])
        self.assertEqual(camp.cb, 'Cl-')
        self.assertEqual(camp.vs_state, {'T_cel': [0.5, 6], 'P_bar': [4, 6], 'fO2': [-20, -1]})
        self.assertEqual(camp.vs_basis, self.config['initial fluid constraints']['basis'])
        self.assertEqual(camp.distro, self.config['vs_distro'])
        self.assertEqual(camp.reso, self.config['resolution'])
        self.assertEqual(camp.SS, self.config['solid solutions'])

        #  self.assertIsInstance(camp.local_3i, Three_i)
        #  self.assertEqual(camp.local_3i.cb, 'Cl-')

        self.assertIsInstance(camp.local_6i, Six_i)
        self.assertEqual(camp.local_6i.switches['iopt_4'], IOPT_4.PERMIT_SS)
        self.assertEqual(camp.local_6i.suppress_min, self.config['suppress min'])
        self.assertEqual(camp.local_6i.min_supp_exemp, self.config['suppress min exemptions'])

    def test_create_env(self):
        """
        Ensure that a campaign's working directory can be created
        """
        camp = Campaign(self.config, self.data0_dir)

        with TemporaryDirectory() as root:
            camp.create_env(dir=root, verbose=False)

            self.assertEquals(camp.campaign_dir, realpath(join(root, camp.name)))

            campaign_dir = join(root, self.config['campaign'])
            self.assertTrue(isdir(campaign_dir))

            huffer_dir = join(campaign_dir, 'huffer')
            self.assertTrue(isdir(huffer_dir))

            fig_dir = join(campaign_dir, 'fig')
            self.assertTrue(isdir(fig_dir))

            order_json = join(campaign_dir, 'orders', camp.hash + '.json')
            self.assertTrue(isfile(order_json))
            self.assertTrue(isfile(join(campaign_dir, 'orders', 'campaign.json')))

            with open(order_json, mode='r', encoding='utf-8') as handle:
                dumped = json.load(handle)
                self.assertEqual(dumped, self.config)

    def test_change_env(self):
        """
        Ensure that calling create_env with a new :code:`dir` argument creates a new campaign
        directory.
        """
        camp = Campaign(self.config, self.data0_dir)
        with TemporaryDirectory() as root:
            camp.create_env(dir=root, verbose=False)
        self.assertEquals(camp.campaign_dir, realpath(join(root, camp.name)))

        with TemporaryDirectory() as root:
            camp.create_env(dir=root, verbose=False)

            campaign_dir = join(root, self.config['campaign'])
            self.assertTrue(isdir(campaign_dir))

            huffer_dir = join(campaign_dir, 'huffer')
            self.assertTrue(isdir(huffer_dir))

            fig_dir = join(campaign_dir, 'fig')
            self.assertTrue(isdir(fig_dir))

            order_json = join(campaign_dir, 'orders', camp.hash + '.json')
            self.assertTrue(isfile(order_json))
            self.assertTrue(isfile(join(campaign_dir, 'orders', 'campaign.json')))

            with open(order_json, mode='r', encoding='utf-8') as handle:
                dumped = json.load(handle)
                self.assertEqual(dumped, self.config)

        self.assertEquals(camp.campaign_dir, realpath(join(root, camp.name)))
        self.assertEquals(camp.order_file, join(camp.campaign_dir, 'orders', camp.hash + '.json'))

    def test_working_directory(self):
        """
        Ensure that the campaign can provide a context manager for switching into and out of the
        campaign directory.
        """
        camp = Campaign(self.config, self.data0_dir)
        with TemporaryDirectory() as root:
            camp.create_env(dir=root, verbose=False)
            with camp.working_directory():
                self.assertEquals(os.getcwd(), realpath(join(root, self.config['campaign'])))

                self.assertTrue(isdir('huffer'))
                self.assertTrue(isdir('fig'))
                self.assertTrue(isfile(join('orders', camp.hash + '.json')))
                self.assertTrue(isfile(join('orders', 'campaign.json')))

    def test_working_directory_creates_env(self):
        """
        Ensure that the campaign creates the working directory before swtiching into and out of the
        directory.
        """
        camp = Campaign(self.config, self.data0_dir)
        with TemporaryDirectory() as root:
            with camp.working_directory(dir=root, verbose=False):
                self.assertEquals(os.getcwd(), realpath(join(root, self.config['campaign'])))

                self.assertTrue(isdir('huffer'))
                self.assertTrue(isdir('fig'))
                self.assertTrue(isfile(join('orders', camp.hash + '.json')))
                self.assertTrue(isfile(join('orders', 'campaign.json')))
