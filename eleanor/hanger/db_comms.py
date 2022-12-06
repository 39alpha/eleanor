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

    sql_ele = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in elements]) + ','

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
    execute_query(conn, '''
        CREATE TABLE IF NOT EXISTS `orders` (`id` INTEGER PRIMARY KEY AUTOINCREMENT,
                               `campaign_hash` VARCHAR(64) NOT NULL,
                               `data0_hash` VARCHAR(64) NOT NULL,
                               `name` TEXT NOT NULL,
                               `create_date` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)
    ''')

    execute_query(conn, '''
        CREATE UNIQUE INDEX IF NOT EXISTS `orders_hash_index`
        ON `orders` (`campaign_hash`, `data0_hash`)
    ''')


def create_es_table(conn, camp, sp, ss, gases, elements):
    """
    Initiater equilibrium space (mined from 6o) table on connection 'conn'
    for campaign 'camp_name' with state dimensions 'camp_vs_state' and
    basis dimensions 'camp_vs_basis'. 'basis' is used here for
    dimensioning, however it is not populated with the initial conditions
    (3i) as the vs table is, but is instead popuilated with the output (6o)
    total abundences.

    :param conn: the database connection
    :param camp: the campaign
    :param loaded_sp: loaded aqueous, solid and gas species
    :param loaded_ss: loaded solid solution species
    """

    sql_info = "CREATE TABLE IF NOT EXISTS es (uuid VARCHAR(32) PRIMARY KEY,\
        ord INTEGER NOT NULL, file INTEGER NOT NULL, run \
        DATE NOT NULL,"

    run_columns = ['initial_aff', 'xi_max', 'aH2O', 'ionic', 'tds', 'soln_mass', 'extended_alk']
    sql_run = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in run_columns]) + ','

    sql_state = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in
                          list(camp.vs_state.keys()) + ['pH']]) + ','

    # convert vs_basis to elements for ES. This will allow teh use of
    # multiple species containing the same element to be used in the
    # basis, while still tracking total element values in the ES.

    sql_ele = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in
                        elements]) + ','
    # molal / moles
    sql_sp_m = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in
                        [f'm{_}' for _ in sp]]) + ','
    # activity / affinity
    sql_sp_a = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in
                        [f'a{_}' for _ in sp]]) + ','

    sql_gas = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in
                        gases]) + ','

    sql_ss = ",".join([f'"{_}" DOUBLE PRECISION' for _ in ss]) + ','

    sql_fk = ' FOREIGN KEY(`ord`) REFERENCES `orders`(`id`), \
               FOREIGN KEY(`uuid`) REFERENCES `vs`(`uuid`)'

    parts = [sql_info, sql_run, sql_state, sql_ele, sql_sp_a, sql_sp_m, sql_gas, sql_ss, sql_fk]
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

    orders = execute_query(conn, f"SELECT `id` FROM `orders` where `campaign_hash` = '{camp.hash}' \
        AND `data0_hash` = '{camp.data0_hash}'").fetchall()

    if len(orders) > 1:
        # DGM: This should never happen because there is a unique index on the hash columns
        raise RuntimeError('more than one order found for campaign and data0 hash')
    elif len(orders) == 1:
        return orders[0][0]

    if insert:
        execute_query(conn,
                      f"INSERT INTO `orders` (`campaign_hash`, `data0_hash`, `name`) \
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
        file = execute_query(conn, f"SELECT MAX(`file`) from `vs` where `camp` = '{camp.name}' \
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
    :param \*args: Additional arguments to Connection.execute # noqa (EW605)

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
    :param \*args: additional arguments to be propagated to Connection.execute # noqa (EW605)
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

def retrieve_combined_records(conn, vs_cols, es_cols,
                              limit=None,
                              ord_id=None,
                              where=None,
                              fname=None):
    """
    Retrieve columns from the `vs` and `es` tables, joined on the :code:`uuid` column. The results
    are returned as a Pandas :code:`DataFrame`.

    Since not all of the systems ordered by the Navigator will converge in EQ3/6, the `vs` table may
    contain orders for systems that do not exist in the `es` table.

    If the :code:`fname` is provided and has either a `.pickle`, `.json` or `.csv` file extension,
    the DataFrame will be written to that file.

    :param conn: the database connection
    :type conn: sqlite3.Connection
    :param vs_cols: the columns to be selected from the `vs` table
    :type vs_cols: list
    :param es_cols: the columns to be selected from the `es` table
    :type es_cols: list
    :param limit: limit the number of records retrieved 'limit'
    :type limit: int
    :param ord_id: select only rows with this order ID.
    :type order_id: int
    :param fname: path of an output file
    :type fname: str or None
    :param where_constrain: limit sql query with 'where statement',
        for example, where '"CO2" > -3'
    :type where_constrain: str

    :return: A DataFrame with the selected columns and rows
    :rtype: pandas.DataFrame
    """
    query = f"SELECT `vs`.`{'`, `vs`.`'.join(vs_cols)}`, \
                     `es`.`{'`, `es`.`'.join(es_cols)}` \
              FROM `vs` INNER JOIN `es` ON `vs`.`uuid` = `es`.`uuid`"

    if ord_id is not None and where is not None:
        query += f" WHERE `es`.`ord` = {ord_id} and {where}"

    elif ord_id is not None:
        query += f" WHERE `es`.`ord` = {ord_id}"

    elif where is not None:
        query += f" WHERE {where}"

    if limit is not None:
        query += f" LIMIT {limit}"

    records = retrieve_records(conn, query)

    df_columns = [f"{c}_v" for c in vs_cols] + [f"{c}_e" for c in es_cols]
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
