"""
.. currentmodule:: eleanor.hanger

The :mod:`db_comms` module contains functions that aid in communicating with the VS and SS
databases. This is used by :mod:`navigator`, :mod:`helmsman`, and sailor in the corse of reading
and writing to and from the postgres databases housing the VS and SS infromation generating in the
course of sucessful operation.
"""
from contextlib import closing
from os.path import splitext
import pandas as pd
import sqlite3
import sys
from eleanor.hanger.tool_room import determine_ss_kids


def establish_database_connection(camp, verbose=False):
    """
    Connect to a campaign SQLite database.

    :param camp: The campaign whose DB to load
    :type camp: eleanor.campaign.Campaign

    :return: a connection to the campaign's SQLite database
    :rtype: sqlite3.Connection
    """
    conn = sqlite3.connect(camp.campaign_db)
    if verbose:
        print("New connection to campaign db")
    return conn


def create_or_expand_vs_table(conn, camp, elements):
    """
    Create the VS table if it does not exists, otherwise add any new reactant columns that may be required.

    :param conn: connection to the database
    :type conn: sqlite3.Connection
    :param camp: the campaign
    :type camp: eleanor.campaign.Campaign
    :param elements: all elements in the system
    :type element: list

    :return: None
    """
    if table_exists(conn, 'vs') and len(camp.target_rnt) > 0:
        existing_columns = get_column_names(conn, 'vs')

        reaction_columns = [f'{k}_morr' for k in camp.target_rnt.keys()] + \
            [f'{k}_rkb1' for k in camp.target_rnt.keys()]

        new_columns = sorted(set(reaction_columns) - set(existing_columns))

        for column in new_columns:
            add_column(conn, 'vs', column, type='DOUBLE PRECISION', default=0.0, not_null=False)
    else:
        create_vs_table(conn, camp, elements)


def create_vs_table(conn, camp, elements):
    """
    Initiate variable space table on connection 'conn'
    for campaign 'camp.name' with state dimensions 'camp.vs_state'
    and basis dimensions 'camp.vs_basis', and total element
    concentration for ele.
    """

    # Add total element columns, which contain element sums from the
    # other columns which include it.
    # ie, vs[C] = HCO3- + CH4 + CO2(g)_morr
    # This will allow VS dimensions to be compiled piecewise. I must
    # be carefull to note that some columns in this vs table are
    # composits, requiring addition/partial addition in order to
    # construct the true thermodynamic constraints (VS dimensions).
    sql_info = "CREATE TABLE IF NOT EXISTS vs (uuid VARCHAR(32) PRIMARY KEY, camp \
        TEXT NOT NULL, ord INTEGER NOT NULL, file INTEGER NOT NULL, birth \
        DATE NOT NULL, data1 TEXT NOT NULL, code SMALLINT NOT NULL, cb TEXT NOT NULL,"

    sql_state = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in list(camp.vs_state.keys())]) + ','

    sql_basis = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in list(camp.vs_basis.keys())]) + ','

    sql_ele = ",".join([f'"m_{_}" DOUBLE PRECISION NOT NULL' for _ in elements]) + ','

    parts = [sql_info, sql_state, sql_basis, sql_ele]
    if len(camp.target_rnt) > 0:
        sql_rnt_morr = ",".join([f'"{_}_morr" DOUBLE PRECISION DEFAULT 0.0' for _ in camp.target_rnt.keys()]) + ','

        sql_rnt_rkb1 = ",".join([f'"{_}_rkb1" DOUBLE PRECISION DEFAULT 0.0' for _ in camp.target_rnt.keys()]) + ','

        parts.extend([sql_rnt_morr, sql_rnt_rkb1])

    parts.append(' FOREIGN KEY(`ord`) REFERENCES `orders`(`id`)')

    if len(parts) != 0:
        execute_query(conn, ''.join(parts) + ')')


def add_column(conn, table, column, type='DOUBLE PRECISION', default=None, not_null=False):
    sql = f"ALTER TABLE `{table}` ADD COLUMN `{column}` {type}"
    if default is not None:
        sql += f" DEFAULT {default}"
    if not_null:
        sql += " NOT NULL"

    execute_query(conn, sql)


def create_orders_table(conn):
    """
    Create the orders table with the following columns:
      * :code:`id` (:code:`SMALLINT`) - the order id
      * :code:`campaign_hash` (:code:`VARCHAR(64)`) - the hash of the campaign specification
      * :code:`data`0_hash (:code:`VARCHAR(64)`) - the hash of the data0 directory
      * :code:`name` (:code:`TEXT`) - the name of the campaign
      * :code:`create_date` (:code:`TIMESTAMP`) - the date the order was created

    The :code:`create_date` defaults to the time at which the row is created. The :code:`id` is the
    primary key for the table, and :code:`campaign_hash` and :code:`data0_hash` jointly form an
    index.
    """
    execute_query(
        conn, '''
        CREATE TABLE IF NOT EXISTS `orders` (`id` INTEGER PRIMARY KEY AUTOINCREMENT,
                               `campaign_hash` VARCHAR(64) NOT NULL,
                               `data0_hash` VARCHAR(64) NOT NULL,
                               `name` TEXT NOT NULL,
                               `create_date` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)
    ''')

    execute_query(
        conn, '''
        CREATE UNIQUE INDEX IF NOT EXISTS `orders_hash_index`
        ON `orders` (`campaign_hash`, `data0_hash`)
    ''')


def create_es_tables(conn, camp, sp, solids, ss, gases, elements):
    """
    Initialize the EQ3 and EQ6 equilibrium tables, to be filled from the mined 3o and 6o files, respectively.

    :param conn: the database connection
    :param camp: the campaign
    :param sp: loaded aqueous, solid and gas species
    :param ss: loaded solid solution species
    :param gases: loaded gases
    :param elements: loaded elements
    """
    solids = [_ for _ in solids if _ != 'None']
    ss = [_ for _ in ss if _ != 'None']
    ss_kids = []
    if len(ss) > 0:
        ss_kids = determine_ss_kids(camp, ss, solids)

    create_es3_table(conn, camp, sp, solids, ss, ss_kids, gases, elements)
    create_es6_table(conn, camp, sp, solids, ss, ss_kids, gases, elements)


def create_es3_table(conn, camp, sp, solids, ss, ss_kids, gases, elements):
    """
    Initialize the EQ3 equilibrium table, to be filled from the mined 3o file.

    :param conn: the database connection
    :param camp: the campaign
    :param sp: loaded aqueous, solid and gas species
    :param ss: loaded solid solution species
    :param gases: loaded gases
    :param elements: loaded elements
    """

    sql_info = "CREATE TABLE IF NOT EXISTS es3 (uuid VARCHAR(32) PRIMARY KEY,\
        ord INTEGER NOT NULL, file INTEGER NOT NULL, run DATE NOT NULL, \
        extended_alk DOUBLE PRECISION, charge_imbalance_eq DOUBLE PRECISION NOT NULL, "

    sql_run = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in ['a_H2O', 'ionic', 'tds', 'soln_mass']]) + ','

    sql_state = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in list(camp.vs_state.keys()) + ['pH']]) + ','

    # convert vs_basis to elements for ES. This will allow teh use of
    # multiple species containing the same element to be used in the
    # basis, while still tracking total element values in the ES.

    sql_ele = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in [f'm_{_}' for _ in elements]]) + ','

    # aq species, log activity (a_...) and log molal (m_...)
    sql_sp_a = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in [f'a_{_}' for _ in sp]]) + ','

    sql_sp_m = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in [f'm_{_}' for _ in sp]]) + ','

    # solids, log QoverK
    sql_sol_qk = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in [f'qk_{_}' for _ in solids]]) + ','

    sql_gas = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in [f'f_{_}' for _ in gases]]) + ','

    sql_ss = ",".join([f'"qk_{_}" DOUBLE PRECISION' for _ in ss]) + ','

    sql_fk = ' FOREIGN KEY(`ord`) REFERENCES `orders`(`id`), \
               FOREIGN KEY(`uuid`) REFERENCES `vs`(`uuid`)'

    parts = [sql_info, sql_run, sql_state, sql_ele, sql_sp_a, sql_sp_m, sql_sol_qk, sql_gas, sql_ss, sql_fk]
    parts = [_ for _ in parts if _ != ',']
    execute_query(conn, ''.join(parts) + ')')


def create_es6_table(conn, camp, sp, solids, ss, ss_kids, gases, elements):
    """
    Initialize the EQ6 equilibrium table, to be filled from the mined 6o file.

    :param conn: the database connection
    :param camp: the campaign
    :param sp: loaded aqueous, solid and gas species
    :param ss: loaded solid solution species
    :param gases: loaded gases
    :param elements: loaded elements
    """

    sql_info = "CREATE TABLE IF NOT EXISTS es6 (uuid VARCHAR(32) PRIMARY KEY,\
        ord INTEGER NOT NULL, file INTEGER NOT NULL, run DATE NOT NULL, \
        extended_alk DOUBLE PRECISION, charge_imbalance_eq DOUBLE PRECISION NOT NULL, "

    run_columns = ['initial_aff', 'xi_max', 'a_H2O', 'ionic', 'tds', 'soln_mass']
    sql_run = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in run_columns]) + ','

    sql_state = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in list(camp.vs_state.keys()) + ['pH']]) + ','

    # convert vs_basis to elements for ES. This will allow teh use of
    # multiple species containing the same element to be used in the
    # basis, while still tracking total element values in the ES.

    sql_ele = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in [f'm_{_}' for _ in elements]]) + ','

    # aq species, log activity (a_...) and log molal (m_...)
    sql_sp_a = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in [f'a_{_}' for _ in sp]]) + ','

    sql_sp_m = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in [f'm_{_}' for _ in sp]]) + ','

    # solids, log QoverK
    sql_sol_qk = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in [f'qk_{_}' for _ in solids]]) + ','

    # solids, moles
    sql_sol_m = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in [f'm_{_}' for _ in solids]]) + ','

    sql_gas = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in [f'f_{_}' for _ in gases]]) + ','

    sql_ss_qk = ",".join([f'"qk_{_}" DOUBLE PRECISION' for _ in ss]) + ','

    sql_ss_m = ",".join([f'"m_{_}" DOUBLE PRECISION' for _ in ss]) + ','

    sql_ss_kids_m = ",".join([f'"m_{_}" DOUBLE PRECISION' for _ in ss_kids]) + ','

    sql_fk = ' FOREIGN KEY(`ord`) REFERENCES `orders`(`id`), \
               FOREIGN KEY(`uuid`) REFERENCES `vs`(`uuid`)'

    parts = [
        sql_info, sql_run, sql_state, sql_ele, sql_sp_a, sql_sp_m, sql_sol_qk, sql_sol_m, sql_gas, sql_ss_qk, sql_ss_m,
        sql_ss_kids_m, sql_fk
    ]
    parts = [_ for _ in parts if _ != ',']
    execute_query(conn, ''.join(parts) + ')')


def get_order_number(conn, camp, insert=True):
    """
    Get the order number based on the campaign hashes. If no corresponding order is found and
    :code:`insert = True`, the hashes are added to the order table and the new order number is
    returned.

    :param conn: connection to the database
    :type conn: sqlite3.Connection
    :param camp: the campaign
    :type camp: eleanor.campaign.Campaign

    :return: the greatest order number
    :rtype: int
    """
    create_orders_table(conn)

    orders = execute_query(
        conn, f"SELECT `id` FROM `orders` where `campaign_hash` = '{camp.hash}' \
        AND `data0_hash` = '{camp.data0_hash}'").fetchall()

    if len(orders) > 1:
        # DGM: This should never happen because there is a unique index on the hash columns
        raise RuntimeError('more than one order found for campaign and data0 hash')
    elif len(orders) == 1:
        return orders[0][0]

    if insert:
        execute_query(
            conn, f"INSERT INTO `orders` (`campaign_hash`, `data0_hash`, `name`) \
                      VALUES ('{camp.hash}', '{camp.data0_hash}', '{camp.name}')").fetchall()
        return get_order_number(conn, camp, insert=False)
    else:
        raise RuntimeError('failed to insert order')


def get_file_number(conn, camp, order_number):
    """
    Get the next file number, starting from 0, for a given campaign and order.

    :param conn: connection to the database
    :type conn: sqlite3.Connection
    :param camp: the campaign
    :type camp: eleanor.campaign.Campaign
    :param order_number: the order number
    :type order_number: int

    :return: the next file number
    :rtype: int
    """
    try:
        file = execute_query(
            conn, f"SELECT MAX(`file`) from `vs` where `camp` = '{camp.name}' \
            AND `ord` = '{order_number}'").fetchall()

        if len(file) >= 1:
            return file[0][0] + 1
    except Exception:
        pass

    return 0


def retrieve_records(conn, query, *args, **kwargs):
    """
    Execute an SQL query on a connection and return the resulting record.

    :param conn: The connection
    :type conn: sqlite3.Connection
    :param query: The query (may include placeholders)
    :type query: str
    :param \\*args: Additional arguments to Connection.execute # noqa (EW605)

    :return: the resulting records
    :rtype: list
    """
    cursor = conn.cursor()
    try:
        cursor.execute(query, *args, **kwargs)
        return cursor.fetchall()
    finally:
        cursor.close()


def execute_query(conn, query, *args, **kwargs):
    """
    Execute an SQL query on a connection, discarding the results.

    :param conn: the connection
    :type conn: sqlite3.Connection
    :param \\*args: additional arguments to be propagated to Connection.execute # noqa (EW605)
    :return: the results of the query
    """
    with conn:
        return conn.execute(query, *args, **kwargs)


def table_exists(conn, table):
    """
    Determine whether or not a given table exists in the database.

    :param conn: the database connection
    :type conn: sqlite3.Connection
    :param table: the table
    :type table: str

    :return: whether or not the table exists
    :rtype: bool
    """
    with closing(conn.execute(f"PRAGMA table_info(`{table}`)")) as cursor:
        return cursor.fetchone() is not None


def get_column_names(conn, table):
    """
    Get the column names of a given database table.

    :param conn: the database connection
    :type conn: sqlite3.Connection
    :param table: the table
    :type table: str

    :return: the names of the columns of the table
    :rtype: list
    """
    with closing(conn.execute(f"PRAGMA table_info(`{table}`)")) as cursor:
        return [row[1] for row in cursor.fetchall()]


def retrieve_combined_records(conn, vs_cols, es3_cols, es6_cols, limit=None, ord_id=None, where=None, fname=None):
    if len(es3_cols) == 0 and len(es6_cols) == 0:
        query = f"SELECT `vs`.`{'`, `vs`.`'.join(vs_cols)}` FROM `vs`"

    elif len(es3_cols) == 0:
        query = f"SELECT `vs`.`{'`, `vs`.`'.join(vs_cols)}`, \
                    `es6`.`{'`, `es6`.`'.join(es6_cols)}` \
                 FROM `vs` INNER JOIN `es6` ON `vs`.`uuid` = `es6`.`uuid`"

    elif len(es6_cols) == 0:
        query = f"SELECT `vs`.`{'`, `vs`.`'.join(vs_cols)}`, \
                    `es3`.`{'`, `es3`.`'.join(es3_cols)}` \
                 FROM `vs` INNER JOIN `es3` ON `vs`.`uuid` = `es3`.`uuid`"

    else:
        query = f"SELECT `vs`.`{'`, `vs`.`'.join(vs_cols)}`, \
                     `es3`.`{'`, `es3`.`'.join(es3_cols)}`, \
                     `es6`.`{'`, `es6`.`'.join(es6_cols)}` \
                 FROM `vs` INNER JOIN `es3` ON `vs`.`uuid` = `es3`.`uuid` \
                           INNER JOIN `es6` ON `vs`.`uuid` = `es6`.`uuid`"

    if ord_id is not None and where is not None:
        query += f" WHERE `vs`.`ord` = {ord_id} and {where}"

    elif ord_id is not None:
        query += f" WHERE `vs`.`ord` = {ord_id}"

    elif where is not None:
        query += f" WHERE {where}"

    if limit is not None:
        query += f" LIMIT {limit}"

    records = retrieve_records(conn, query)

    df_columns = [f"{c}_v" for c in vs_cols] + [f"{c}_e3" for c in es3_cols] + [f"{c}_e6" for c in es6_cols]

    df = pd.DataFrame(records, columns=df_columns)

    if fname is not None:
        _, ext = splitext(fname)
        if ext == '.json':
            df.to_json(fname, orient='records')
        elif ext == '.csv':
            df.to_csv(fname, index=False)
        elif ext == '.pickle':
            df.to_pickle(fname)
        else:
            sys.stderr.write(f"warning: cannot write records; unrecognized format '{ext}'\n")

    return df


def execute_vs_exit_updates(conn, vs_points):
    """
    Execute the SQLite3 command to update the VS points based on exit codes.

    :param conn: the database connection
    :type conn: sqlite3.Connection
    :param vs_points: list of tuples where each tuple has two values (exit_code, uuid)
    :type vs_points: list

    :return: None
    :rtype: None
    """
    cur = conn.cursor()
    cur.executemany("UPDATE vs SET code = ? WHERE uuid = ?;", vs_points)
    conn.commit()
    return None
