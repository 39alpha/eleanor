### The db_comms package contains functions that aid in 
### communicating with the VS and SS databases.
### This is used by navigator, helmsman, and sailor in 
### the corse of reading and writing to and from the postgres 
### databases housing the VS and SS infromation generating 
### in the course of sucessful operation.

import sqlite3 as sql
import pandas as pd
import sys, os, shutil
from subprocess import *


_conn = None

###########################   sqlite3   #############################

def establish_server_connection(campaign, _conn = None):
	## TODO: Fix this to work with SQLLite 
	"""Establish SQL connection with local DB"""
	if not _conn:
		campaign_db_name = campaign.name + ".db"
		print('new connection to local db: ' + campaign_db_name)
		_conn = sql.connect(campaign_db_name)

	return _conn

def get_order_number(conn, camp_name):
	"""
	This code reaches out to the sql database to check 
	for the highest order number sitting in 'campaign'.vs
	"""
	rec = retrieve_record(conn, 'select ord from {}_vs'.format(camp_name))
	if len(rec) == 0:
		### if table exists but contains no records, then return order number 0
		### so that the follow on function spicking order numbers move count to 1
		return 0
	else:
		return rec[-1][0]


def retrieve_record(conn, sql_query):
	""" 
	Execute 'postgres_query' on connection 'conn' and return 
	the record 'rec' of that search.
	"""
	try:
		cursor = conn.cursor() 				#	establish cursor
		cursor.execute(sql_query) 		#	excute query
		rec = cursor.fetchall() 			#	retrieve record
		cursor.close()
		return rec
		
	except (Exception, sql.Error) as error :
		print ("Error while fetching data from SQL.", error)
		cursor.close()
		print('  sqlite3 couldnt understand whatever bullshit')
		print('  you were trying to tell it.\n')
		return None



def execute_sql_statement(conn, sql_query):
	""" 
	Execute 'sql_query' on connection 'conn'
	"""
	try:
		cursor = conn.cursor() 				#	establish cursor
		cursor.execute(sql_query) 		#	excute query
		conn.commit()
		cursor.close()
	except (Exception, sql.Error) as error:
		print ("Error while fetching data from SQL.", error)
		cursor.close()
		print('  sqlite3 couldnt understand whatever bullshit')
		print('  you were trying to tell it.\n')
		print('  Im proud of you Marty.\n')
		return None
		
def get_column_names(conn, table):
	"""
	return column names from sql 'table'
	on connection 'conn'
	"""
	try:
		cursor = conn.cursor() 				#	establish cursor
		cursor.execute("Select * FROM {} LIMIT 0".format(table))
		columns = [_[0] for _ in cursor.description] 			#	column names from ss table
		cursor.close()
		return columns
	except (Exception, sql.Error) as error:
		print ("Error while fetching data from SQL", error)
		cursor.close()
		print('  SQL couldnt understand whatever bullshit')
		print('  you were trying to tell it.\n')
		conn.close()
		return None


def retrieve_vs_es_record(conn, vs_cols, es_cols, table, ord_id, format = 'df', name = ''):
	"""
	Retrieve a postgres record of columns combined from 
	a vs table (variable space points), and an es table 
	(equilibrium space points), and store in a pandas datafram.
	
	The join function that allows this union of two tables is joining on 
	the uuid column in each, as limited by the es table.

	This is necessary becausue the vs table contains all systems that were
	attempted in a given order. However, some systems may not converge in eq3/6,
	and therefore may not be represented in the es table.

	if a name is supplied, the df will also be exported to file.
	json and csv are currently supported.

	"""

	combo_rec  = retrieve_record(
		conn, 'select A."{}", B."{}" \
		from {}_vs as A \
		inner join {}_es as B \
		on A.uuid=B.uuid \
		where B.ord = {}'.format(
			'", A."'.join(vs_cols), 
			'", B."'.join(es_cols),
			table, 
			table, 
			ord_id))

	df_col_names  = ["{}_v".format(_) for _ in vs_cols] + ["{}_e".format(_) for _ in es_cols]
	df = pd.DataFrame(combo_rec, columns = df_col_names)

	### if a file name was given, then export the df accordingly
	if name != '':
		if name.split('.')[-1] == 'json':
			df.to_json(name, orient='records')		
		elif name.split('.')[-1] == 'csv':
			df.to_csv(name, index=False)

	return df


