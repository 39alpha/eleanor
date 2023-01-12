from contextlib import closing
from eleanor.campaign import Campaign
from os.path import isfile, join
from tempfile import TemporaryDirectory
import eleanor.hanger.db_comms as dbc
import pandas as pd
import sqlite3
from .. common import TestCase

class TestDBComms(TestCase):
    """
    Tests of the eleanor.hanger.db_comms module
    """

    def test_canary(self):
        """
        Confirm that the test case is being run
        """
        self.assertTrue(True)

    def setUp(self):
        """
        Set up the TestCase.
        """
        self.campaign = Campaign({
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
        }, self.data0_dir)

    def test_establish_database_connection(self):
        """
        Ensure that we can connect to a campaign's database.
        """
        with TemporaryDirectory() as root:
            self.campaign.create_env(dir=root, verbose=False)
            conn = dbc.establish_database_connection(self.campaign, verbose=False)
            conn.close()

            self.assertTrue(isfile(join(self.campaign.campaign_dir, 'campaign.sql')))

    def test_get_order_number(self):
        """
        Ensure that :meth:`get_order_number` returns the correct answer.
        """
        with TemporaryDirectory() as root:
            self.campaign.create_env(dir=root, verbose=False)
            conn = dbc.establish_database_connection(self.campaign, verbose=False)

            order_number = dbc.get_order_number(conn, self.campaign)
            self.assertEqual(order_number, 1)

            order_number = dbc.get_order_number(conn, self.campaign)
            self.assertEqual(order_number, 1)

            self.campaign._hash = 'abc123'
            order_number = dbc.get_order_number(conn, self.campaign)
            self.assertEqual(order_number, 2)

            self.campaign._data0_hash = '123abc'
            order_number = dbc.get_order_number(conn, self.campaign)
            self.assertEqual(order_number, 3)

    def test_retrieve_records(self):
        with TemporaryDirectory() as root:
            self.campaign.create_env(dir=root, verbose=False)
            conn = dbc.establish_database_connection(self.campaign, verbose=False)

            with self.assertRaises(sqlite3.Error):
                dbc.retrieve_records(conn, 'SELECT * FROM `vs`')

            conn.execute('CREATE TABLE `vs` (`ord` SMALLINT)')

            with self.assertRaises(sqlite3.Error):
                dbc.retrieve_records(conn, 'nonsense query')

            conn.executemany('INSERT INTO `vs` VALUES (?)',
                             [(1,), (2,), (3,)])

            records = dbc.retrieve_records(conn, 'SELECT * FROM `vs`')
            self.assertEqual(len(records), 3)

    def test_execute_query(self):
        with TemporaryDirectory() as root:
            self.campaign.create_env(dir=root, verbose=False)
            conn = dbc.establish_database_connection(self.campaign, verbose=False)

            with self.assertRaises(sqlite3.Error):
                dbc.execute_query(conn, 'INSERT INTO `vs` VALUES (1)')

            with self.assertRaises(sqlite3.Error):
                dbc.execute_query(conn, 'nonsense query')

            dbc.execute_query(conn, 'CREATE TABLE `vs` (`ord` SMALLINT)')

            with closing(conn.execute('PRAGMA table_info(`vs`)')) as cursor:
                columns = [row[1] for row in cursor.fetchall()]

            self.assertEqual(columns, ['ord'])

    def test_get_column_names(self):
        with TemporaryDirectory() as root:
            self.campaign.create_env(dir=root, verbose=False)
            conn = dbc.establish_database_connection(self.campaign, verbose=False)

            dbc.execute_query(conn, 'CREATE TABLE `vs` (`ord` SMALLINT)')

            self.assertEqual(dbc.get_column_names(conn, 'not-a-real-table'), [])
            self.assertEqual(dbc.get_column_names(conn, 'vs'), ['ord'])

    def test_retrieve_combined_records(self):
        with TemporaryDirectory() as root:
            self.campaign.create_env(dir=root, verbose=False)
            conn = dbc.establish_database_connection(self.campaign, verbose=False)

            with self.assertRaises(sqlite3.Error):
                dbc.retrieve_combined_records(conn, ['X'], ['Y'])

            dbc.execute_query(conn, 'CREATE TABLE `vs` (`uuid` VAR(256), `ord` SMALLINT)')
            dbc.execute_query(conn, 'CREATE TABLE `es6` (`uuid` VARCHAR(256), `ord` SMALLINT)')

            with self.assertRaises(sqlite3.Error):
                dbc.retrieve_combined_records(conn, ['X'], ['Y'])

            dbc.execute_query(conn, 'DROP TABLE `vs`')
            dbc.execute_query(conn, 'DROP TABLE `es6`')
            dbc.execute_query(conn, 'CREATE TABLE `vs` (`uuid` VARCHAR(256), `ord` SMALLINT, `X` REAL, `U` REAL)')
            dbc.execute_query(conn, 'CREATE TABLE `es6` (`uuid` VARCHAR(256), `ord` SMALLINT, `Y` REAL, `V` REAL)')

            df = dbc.retrieve_combined_records(conn, ['X'], ['Y'])
            self.assertEqual(sorted(df.columns), ['X_v', 'Y_e'])
            self.assertEqual(len(df), 0)

            conn.executemany('INSERT INTO `vs` VALUES (?, ?, ?, ?)',
                             [('a', 1, 1.1, 2.1),
                              ('b', 1, 1.2, 2.2),
                              ('c', 2, 1.3, 2.3)])

            df = dbc.retrieve_combined_records(conn, ['X'], ['Y'])
            self.assertEqual(sorted(df.columns), ['X_v', 'Y_e'])
            self.assertEqual(len(df), 0)

            conn.executemany('INSERT INTO `es6` VALUES (?, ?, ?, ?)',
                             [('a', 1, 3.1, 4.1),
                              ('b', 1, 3.2, 4.2)])

            df = dbc.retrieve_combined_records(conn, ['X'], ['Y'])
            self.assertEqual(sorted(df.columns), ['X_v', 'Y_e'])
            self.assertEqual(len(df), 2)
            self.assertEqual([tuple(r) for r in df.to_numpy()],
                              [(1.1, 3.1), (1.2, 3.2)])

            conn.executemany('INSERT INTO `es6` VALUES (?, ?, ?, ?)',
                             [('c', 2, 3.3, 4.3)])

            df = dbc.retrieve_combined_records(conn, ['X'], ['Y'])
            self.assertEqual(sorted(df.columns), ['X_v', 'Y_e'])
            self.assertEqual(len(df), 3)
            self.assertEqual([tuple(r) for r in df.to_numpy()],
                              [(1.1, 3.1), (1.2, 3.2), (1.3, 3.3)])

            df = dbc.retrieve_combined_records(conn, ['X'], ['Y'], ord_id=2)
            self.assertEqual(sorted(df.columns), ['X_v', 'Y_e'])
            self.assertEqual(len(df), 1)
            self.assertEqual([tuple(r) for r in df.to_numpy()],
                              [(1.3, 3.3)])

            with self.campaign.working_directory() as campdir:
                expected = dbc.retrieve_combined_records(conn, ['X'], ['Y'], fname='data.json')
                self.assertTrue(isfile(join(campdir, 'data.json')))
                got = pd.read_json('data.json')
                self.assertTrue((got.columns == expected.columns).all())
                self.assertTrue((got.to_numpy() == expected.to_numpy()).all())

                expected = dbc.retrieve_combined_records(conn, ['X'], ['Y'], fname='data.csv')
                self.assertTrue(isfile(join(campdir, 'data.csv')))
                got = pd.read_csv('data.csv')
                self.assertTrue((got.columns == expected.columns).all())
                self.assertTrue((got.to_numpy() == expected.to_numpy()).all())

    def test_create_vs_table(self):
        with TemporaryDirectory() as root:
            self.campaign.create_env(dir=root, verbose=False)
            conn = dbc.establish_database_connection(self.campaign, verbose=False)
            dbc.create_vs_table(conn, self.campaign, ['X'])

            result = dbc.execute_query(conn, 'pragma table_info(vs)').fetchall()
            self.assertEqual(len(result), 26)
            columns = list(map(lambda x: x[1], result))
            self.assertIn('X', columns)

    def test_create_es_tables(self):
        with TemporaryDirectory() as root:
            self.campaign.create_env(dir=root, verbose=False)
            conn = dbc.establish_database_connection(self.campaign, verbose=False)
            dbc.create_es_tables(conn, self.campaign, ['W'], ['X'], ['Y'], ['Z'])

            result = dbc.execute_query(conn, 'pragma table_info(es3)').fetchall()
            self.assertEqual(len(result), 17)
            columns = list(map(lambda x: x[1], result))
            for c in ['Z', 'aW', 'Y', 'X']:
                self.assertIn(c, columns)

            result = dbc.execute_query(conn, 'pragma table_info(es6)').fetchall()
            self.assertEqual(len(result), 20)
            columns = list(map(lambda x: x[1], result))
            for c in ['Z', 'aW', 'mW', 'Y', 'X']:
                self.assertIn(c, columns)

    def test_create_orders_table(self):
        with TemporaryDirectory() as root:
            self.campaign.create_env(dir=root, verbose=False)
            conn = dbc.establish_database_connection(self.campaign, verbose=False)
            dbc.create_orders_table(conn)

            result = dbc.execute_query(conn, 'pragma table_info(orders)').fetchall()
            columns = list(map(lambda x: x[1], result))
            self.assertEqual(columns, ['id', 'campaign_hash', 'data0_hash', 'name', 'create_date'])
