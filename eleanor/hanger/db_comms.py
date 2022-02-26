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

def create_vs_table(conn, camp, elements):
    """
    Initiate variable space table on connection 'conn'
    for campaign 'camp.name' with state dimensions 'camp.vs_state'
    and basis dimensions 'camp.vs_basis', and total element
    concentration for ele.
    """

    # Add total eleent columns, which contain element sums from the
    # other columns which include it.
    # ie, vs[C] = HCO3- + CH4 + CO2(g)_morr
    # This will allow VS dimensions to be compiled piecewise. I must
    # be carefull to note that some columns in this vs table are
    # composits, requiring addition/partial addition in order to
    # construct the true thermodynamic constraints (VS dimensions).

    sql_info = "CREATE TABLE vs (uuid VARCHAR(32) PRIMARY KEY, camp \
        TEXT NOT NULL, ord SMALLINT NOT NULL, file INTEGER NOT NULL, birth \
        DATE NOT NULL, code SMALLINT NOT NULL,"
    if len(camp.target_rnt) > 0:

        sql_rnt_morr = ",".join([f'"{_}_morr" DOUBLE PRECISION NOT NULL'
                                for _ in camp.target_rnt.keys()]) + ','

        sql_rnt_rkb1 = ",".join([f'"{_}_rkb1" DOUBLE PRECISION NOT NULL'
                                 for _ in camp.target_rnt.keys()]) + ','
    # Out of if statement
    sql_state = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in
                         list(camp.vs_state.keys())]) + ','

    sql_basis = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in
                         list(camp.vs_basis.keys())]) + ','

    sql_ele = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in
                        elements])

    if len(camp.target_rnt) > 0:
        execute_query(
            conn,
            "".join([sql_info, sql_rnt_morr, sql_rnt_rkb1, sql_state, sql_basis, sql_ele]) + ');')
    else:
        execute_query(
            conn, "".join([sql_info, sql_state, sql_basis, sql_ele]) + ');')

def create_es_table(conn, camp, loaded_sp, elements):
    """
    Initiater equilibrium space (mined from 6o) table on connection 'conn'
    for campaign 'camp_name' with state dimensions 'camp_vs_state' and
    basis dimensions 'camp_vs_basis'. 'basis' is used here for
    dimensioning, however it is not populated with the initial conditions
    (3i) as the vs table is, but is instead popuilated with the output (6o)
    total abundences.

    loaded_sp = list of aq, solid,a nd gas species loaded in test.3i
    instantiated fof the campaign
    """

    sql_info = "CREATE TABLE es (uuid VARCHAR(32) PRIMARY KEY, camp \
        TEXT NOT NULL, ord SMALLINT NOT NULL, file INTEGER NOT NULL, run \
        DATE NOT NULL, mineral TEXT NOT NULL,"

    sql_run = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in
                        ['initial_aff', 'xi_max', 'aH2O', 'ionic', 'tds', 'soln_mass']]) + ','

    sql_state = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in
                          list(camp.vs_state.keys())]) + ','

    # convert vs_basis to elements for ES. This will allow teh use of
    # multiple species containing the same element to be used in the
    # basis, while still tracking total element values in the ES.

    sql_ele = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in
                        elements]) + ','

    sql_sp = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in
                       loaded_sp])

    execute_query(conn, "".join([sql_info, sql_run, sql_state, sql_ele, sql_sp]) + ');')

def get_order_number(conn):
    """
    Get the highest order number from the campaign's variable space table.

    :param conn: connection to the database
    :type conn: sqlite3.Connection

    :return: the greatest order number
    :rtype: int
    """
    rec = retrieve_records(conn, "SELECT MAX(`ord`) FROM `vs`")
    if len(rec) == 0 or rec[0][0] is None:
        return 0
    else:
        return rec[0][0]

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

def retrieve_combined_records(conn, vs_cols, es_cols, limit=None, ord_id=None, where=None,
                              fname=None):
    """
    Retrieve columns from the VS and ES tables, joined on the :code:`uuid` column. The results are
    returned as a Pandas :code:`DataFrame`.

    Since not all of the systems ordered by the navigator will converge in eq3/6, the VS table may
    contain orders for systems that do not exist in the ES table.

    If the :code:`fname` is provided and has either a JSON or CSV file extension, the dataframe
    will be written to that file.

    :param conn: the database connection
    :type conn: sqlite3.Connection
    :param vs_cols: the columns to be selected from the VS table
    :type vs_cols: list
    :param es_cols: the columns to be selected from the ES table
    :type es_cols: list
    :param limit: limit the number of records retrieved 'limit'
    :type limit: int
    :param ord_id: select only rows with this order ID.
    :type order_id: int
    :param fname: path of an output file
    :type fname: str or None
    :param where_constrain: limit sql query with 'where statement',
        for exmaple, where '"CO2" > -3'
    :type where_constrain: str

    :return: A dataframe with the selected columns and rows
    :rtype: pandas.DataFrame
    """
    query = f"SELECT `vs`.`{'`, `vs`.`'.join(vs_cols)}`, \
                     `es`.`{'`, `es`.`'.join(es_cols)}` \
              FROM `vs` INNER JOIN `es` ON `vs`.`uuid` = `es`.`uuid`"

    if ord_id is not None and where is not None:
        query += f" WHERE `es`.`ord` = {ord_id} and {where}"

    elif ord_id is not None:
        query += f" WHERE `es`.`ord` = {ord_id}"

    elif ord_id is not None:
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
        else:
            sys.stderr.write(f"warning: cannot write records; unrecognized format '{ext}'\n")

    return df
