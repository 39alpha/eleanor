import unittest
from eleanor.campaign import Campaign
from eleanor.hanger.tool_room import Three_i, Six_i
from tempfile import NamedTemporaryFile, TemporaryDirectory
from os import listdir
from os.path import isdir, isfile, join, realpath
import re
import json
import os

class TestCampaign(unittest.TestCase):
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
            'solid solutions': True
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
        camp = Campaign(self.config, '/path/to/db')

        self.assertEqual(camp.data0dir, '/path/to/db')
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

        self.assertIsInstance(camp.local_3i, Three_i)
        self.assertEqual(camp.local_3i.cb, 'Cl-')

        self.assertIsInstance(camp.local_6i, Six_i)
        self.assertEqual(camp.local_6i.iopt4, ' 1')
        self.assertEqual(camp.local_6i.suppress_min, self.config['suppress min'])
        self.assertEqual(camp.local_6i.min_supp_exemp, self.config['suppress min exemptions'])

    def test_init_without_solid_solution(self):
        """
        Ensure that campaigns can be initalized without solid solutions
        """
        self.config['solid solutions'] = False

        camp = Campaign(self.config, '/path/to/db')

        self.assertEqual(camp.data0dir, '/path/to/db')
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

        self.assertIsInstance(camp.local_3i, Three_i)
        self.assertEqual(camp.local_3i.cb, 'Cl-')

        self.assertIsInstance(camp.local_6i, Six_i)
        self.assertEqual(camp.local_6i.iopt4, ' 0')
        self.assertEqual(camp.local_6i.suppress_min, self.config['suppress min'])
        self.assertEqual(camp.local_6i.min_supp_exemp, self.config['suppress min exemptions'])

    def test_load_from_json(self):
        """
        Ensure that a campaign can be loaded from a JSON-formatted file.
        """
        with NamedTemporaryFile(mode='w+') as handle:
            json.dump(self.config, handle, indent=True)
            handle.seek(0)
            camp = Campaign.from_json(handle.name, '/path/to/db')

        self.assertEqual(camp.data0dir, '/path/to/db')
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

        self.assertIsInstance(camp.local_3i, Three_i)
        self.assertEqual(camp.local_3i.cb, 'Cl-')

        self.assertIsInstance(camp.local_6i, Six_i)
        self.assertEqual(camp.local_6i.iopt4, ' 1')
        self.assertEqual(camp.local_6i.suppress_min, self.config['suppress min'])
        self.assertEqual(camp.local_6i.min_supp_exemp, self.config['suppress min exemptions'])

    def test_create_env(self):
        """
        Ensure that a campaign's working directory can be created
        """
        camp = Campaign(self.config, '/path/to/db')

        with TemporaryDirectory() as campaign_dir:
            camp.create_env(dir=campaign_dir, verbose=False)

            self.assertEquals(camp.campaign_dir, campaign_dir)

            campaign_dir = campaign_dir
            self.assertTrue(isdir(campaign_dir))

            huffer_dir = join(campaign_dir, 'huffer')
            self.assertTrue(isdir(huffer_dir))

            fig_dir = join(campaign_dir, 'fig')
            self.assertTrue(isdir(fig_dir))

            campaign_json = join(campaign_dir, 'campaign.json')
            self.assertTrue(isfile(campaign_json))

            with open(campaign_json, mode='r', encoding='utf-8') as handle:
                dumped = json.load(handle)
                self.assertEqual(dumped, self.config)

    def test_change_env(self):
        """
        Ensure that calling create_env with a new :code:`dir` argument creates a new campaign
        directory.
        """
        camp = Campaign(self.config, '/path/to/db')
        with TemporaryDirectory() as campaign_dir:
            camp.create_env(dir=campaign_dir, verbose=False)
        self.assertEquals(camp.campaign_dir, campaign_dir)

        with TemporaryDirectory() as campaign_dir:
            camp.create_env(dir=campaign_dir, verbose=False)

            self.assertTrue(isdir(campaign_dir))

            huffer_dir = join(campaign_dir, 'huffer')
            self.assertTrue(isdir(huffer_dir))

            fig_dir = join(campaign_dir, 'fig')
            self.assertTrue(isdir(fig_dir))

            campaign_json = join(campaign_dir, 'campaign.json')
            self.assertTrue(isfile(campaign_json))

            with open(campaign_json, mode='r', encoding='utf-8') as handle:
                dumped = json.load(handle)
                self.assertEqual(dumped, self.config)

        self.assertEquals(camp.campaign_dir, campaign_dir)

    def test_working_directory(self):
        """
        Ensure that the campaign can provide a context manager for switching into and out of the
        campaign directory.
        """
        camp = Campaign(self.config, '/path/to/db')
        with TemporaryDirectory() as campaign_dir:
            camp.create_env(dir=campaign_dir, verbose=False)
            with camp.working_directory():
                self.assertEquals(os.getcwd(), campaign_dir)

                self.assertTrue(isdir('huffer'))
                self.assertTrue(isdir('fig'))
                self.assertFalse(isdir('backup'))
                self.assertTrue(isfile('campaign.json'))

    def test_working_directory_creates_env(self):
        """
        Ensure that the campaign creates the working directory before swtiching into and out of the
        directory.
        """
        camp = Campaign(self.config, '/path/to/db')
        with TemporaryDirectory() as campaign_dir:
            with camp.working_directory(dir=campaign_dir, verbose=False):
                self.assertEquals(os.getcwd(), campaign_dir)

                self.assertTrue(isdir('huffer'))
                self.assertTrue(isdir('fig'))
                self.assertTrue(isfile('campaign.json'))

    def test_no_backup(self):
        """
        Ensure that we do not create a backup when an identical JSON file is loaded in the same
        environment.
        """
        camp = Campaign(self.config, '/path/to/db')
        with TemporaryDirectory() as campaign_dir:
            camp.create_env(dir=campaign_dir, verbose=False)
            camp.create_env(dir=campaign_dir, verbose=False)
            self.assertFalse(isdir(join(camp.campaign_dir, 'backup')))

    def test_create_backup(self):
        """
        Ensure that we create a backup when the campaign is changed and we load the same
        environment.
        """
        camp = Campaign(self.config, '/path/to/db')
        with TemporaryDirectory() as campaign_dir:
            camp.create_env(dir=campaign_dir, verbose=False)

            # This is a hack until we get get some proper getters and setters setup for the
            # Campaign.
            camp._raw['campaign'] = 'a different name'
            camp.create_env(dir=campaign_dir, verbose=False)
            backup_dir = join(camp.campaign_dir, 'backup')
            self.assertTrue(isdir(backup_dir))
            backups = listdir(backup_dir)
            pattern = re.compile('^campaign_\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d+.json')
            self.assertTrue(all(map(lambda f: pattern.match(f), backups)))
