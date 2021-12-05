###
### Navigator.py         
### Generates orders (sets of points in VS) to be stored in VS 
### postgresql database. These orders are to be managed by the 
### helmsman at her leisure.
### Tucker Ely and then 39Alpha
### October 6nd 2020 and then Dec 12th 2021

version = '0.1'

import sqlite3 as sql
import psycopg2.extras as extras
import sys, uuid, random, itertools
import numpy as np
import pandas as pd
from time import *
import matplotlib.pyplot as plt

from hanger.db_comms import *
from hanger.tool_room import *
from hanger.data0_tools import *

### loaded campagin
import campaign


camp = campaign.Campaign("CSS0_1.json")

def main():

        # os.chdir('..')
	### number of sample points requested in current order
	print(os.getcwd())
	if camp.distro == 'BF':
		### BF = Brute force, whose order lenth is set by the combination 
		### needed to fulfill the variables listed in the campain file. The
		### resolution is set by reso in campagin file
		order_len = 'BF'


	elif camp.distro == 'random':
		### first argument is a number corresponding to desired order length
		### for random uniform order
		order_len = camp.reso


	print('Loading campagin {}.\n'.format(camp.name))


	conn = establish_server_connection(camp.name + ".db")


	### Determine campaign status in postgres database. 
	### If VS/ES tables already exist, then dont touch them,
	### just determine the next new order number.
	### If no tables exists for the campaign, then run the
	### huffer to initiate VS/ES, and set order number to 1.
	order_number = check_campaign_tables(conn)
	

	if order_number == 1:
		### new campaign
		huffer(conn)
	

	### grab needed species and element data from huffer test.3o files
	elements = determine_ele_set(path = '{}_huffer/'.format(camp.name))
	sp_names = determine_loaded_sp(path = '{}_huffer/'.format(camp.name))


	### current order birthday
	date = strftime("%Y-%m-%d", gmtime()) 			



	### Generate orders. This can be altered later to call a variety of        
	### functions that yeild different VS point distributions.
	if camp.disro == 'random':
		orders = random_uniform_order(date, order_number, camp.reso, elements)
	
	elif camp.distro == 'BF':
		orders = brute_force_order(conn, date, order_number, elements)
	


	### Send dataframe containing new orders to postgres database
	orders_to_sql(conn, '{}_vs'.format(camp.name), order_number, orders)
	


	conn.close()



	print(' The Navigator has done her job.')
	print('   While she detected no "obvious" faults,')
	print('   she notes that you may have fucked up')
	print('   repeatedly, but the QA code required to')
	print('   detect your fuck ups has not been written.\n')




def huffer(conn):
	""" 
	The huffer performs steps required to initiate a new campaign. 
	It is only run to initiate a new campaign, and not to initiate 
	new orders on an existing campaign. This is becuase the VS and 
	ES only need to be set up once per campaign. Any information 
	that may be needed throughout the life of a campign which the 
	huffer might provide, is stored in the huffers folder.

	(1) Test instantiated 3i file for errors.
	(2) Determine the correct varaibels for vs and es 
		tables given loaded species.
	(3) Establish dynamically accessed data0's (not yet built)

	"""
	print('Running the Huffer.')
	

	### build huffer directory and step in
	mk_check_del_directory('{}_huffer'.format(camp.name))    	#	build test directory
	mk_check_del_directory('{}_fig'.format(camp.name))    		#	build figure directory

	os.chdir('{}_huffer'.format(camp.name)) 					#	step into directory
	
	### build test.3i file from mean vlaues for each variable that is
	### set to a range in the new campaign.
	state_dict = {}
	for _ in camp.vs_state.keys():
		state_dict[_] = np.mean(camp.vs_state[_])

	basis_dict = {}
	for _ in camp.vs_basis.keys():
		basis_dict[_] = np.mean(camp.vs_basis[_])

	### (1) build and run test.3i
	print('\n Processing test.3i.')
	

	### select proper data0
	suffix = data0_suffix(state_dict['T_cel'], state_dict['P_bar'])


	###	build 'verbose' 3i, with solid solutions on 
	camp.local_3i.write(
		'test.3i', state_dict, basis_dict, output_details = 'v')
	out, err = runeq(3, suffix, 'test.3i')



	try:
		### if 3o is generated
		lines = grab_lines('output')
	except:
		print('\n Huffer fail:')
		sys.exit('  I fucked that up didnt I?\n')


	#### Run QA on 3i


	elements = determine_ele_set()


	### estalibsh new table based on vs_state and vs_basis
	initiate_postgresql_VS_table(conn, elements)



	### (2) build state_space for es table
	###	list of loaded aq, solid, and gas species to be appended
	sp_names = determine_loaded_sp()



	### estalibsh new ES table based on loaded species.
	initiate_postgresql_ES_table(conn, sp_names, elements)	

	os.chdir('..')
	
	print('\n Huffer complete.\n')


###################    postgres table functions   ####################

def check_campaign_tables(conn):
	"""
	(1) query sql to see if tables already esits for campaign 
		'camp_name' (not a new campaign).
	(2) if so, return most recent order number.
	(3) if camp_name is new, then return order_num = 1 and run the
		huffer.
	""" 

	### (1) query postgres to see if tables already esits for the
	### loaded campaign 'camp_name'
	cur = conn.cursor()
	cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='{}_vs'; ".format(camp.name))


	if cur.rowcount == 1:
		### (2) table already exists, and the campaign has been run 
		### before.
		last_order = get_order_number(conn, camp.name)

		next_order_number = last_order + 1
		return next_order_number
	else:
		### (3) new campaign!  Congratulations!
		### exit to run huffer
		next_order_number = 1
		return next_order_number
	

def initiate_sql_VS_table(conn, elements):
	""" 
	Initiate variable space table on connection 'conn'
	for campaign 'camp.name' with state dimensions 'camp.vs_state'
	and basis dimensions 'camp.vs_basis', and total element 
	concentration for ele.
	"""

	### Add total eleent columns, which contain element sums from the 
	### other columns which include it.
	### ie, vs[C] = HCO3- + CH4 + CO2(g)_morr
	### This will allow VS dimensions to be compiled piecewise. I must 
	### be carefull to note that some columns in this vs table are
	### composits, requiring addition/partial addition in order to 
	### construct the true thermodynamic constraints (VS dimensions).



	sql_info      = "CREATE TABLE {}_vs (uuid VARCHAR(32) PRIMARY KEY, camp \
		TEXT NOT NULL, ord SMALLINT NOT NULL, file INTEGER NOT NULL, birth \
		DATE NOT NULL, code SMALLINT NOT NULL,".format(camp.name)
	if len(camp.target_rnt) > 0:
		sql_rnt_morr  = ",".join([f'"{_}_morr" DOUBLE PRECISION NOT NULL' 
			for _ in camp.target_rnt.keys()]) + ','
		sql_rnt_rkb1  = ",".join([f'"{_}_rkb1" DOUBLE PRECISION NOT NULL' 
			for _ in camp.target_rnt.keys()]) + ','
	sql_state     = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in 
		list(camp.vs_state.keys())]) + ','
	sql_basis     = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in 
		list(camp.vs_basis.keys())]) + ','
	sql_ele       = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in 
		elements])



	if len(camp.target_rnt) > 0:
		execute_sql_statement(
			conn, "".join([sql_info, sql_rnt_morr, sql_rnt_rkb1, sql_state, 
				sql_basis, sql_ele]) + ');')
	else:	
		execute_sql_statement(
			conn, "".join([sql_info, sql_state, sql_basis, sql_ele]) + ');')

		
def initiate_postgresql_ES_table(conn, loaded_sp, elements):
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
	


	sql_info  = "CREATE TABLE {}_es (uuid VARCHAR(32) PRIMARY KEY, camp \
		TEXT NOT NULL, ord SMALLINT NOT NULL, file INTEGER NOT NULL, run \
		DATE NOT NULL, mineral TEXT NOT NULL,".format(camp.name)
	
	sql_run   = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in 
		['initial_aff', 'xi_max', 'aH2O', 'ionic', 'tds', 'soln_mass']]) + ','
	
	sql_state = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in 
		list(camp.vs_state.keys())]) + ','
	
	### convert vs_basis to elements for ES. This will allow teh use of 
	### multiple species containing the same element to be used in the
	### basis, while still tracking total element values in the ES.
	
	sql_ele   = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in 
		elements]) + ','
	
	sql_sp    = ",".join([f'"{_}" DOUBLE PRECISION NOT NULL' for _ in 
		loaded_sp])
	

	execute_sql_statement(conn, "".join([sql_info, sql_run, sql_state, sql_ele, sql_sp]) + ');')


def orders_to_sql(conn, table, ord, df):
	"""
	Write pandas dataframe 'df' to sql 'table' on connection'conn.'
	"""
	print('Attempting to write order # {}'.format(ord))
	print('  to postgresql table {}'.format(table))
	print('  . . . ')
	tuples = [tuple(x) for x in df.to_numpy()]
	cols = ','.join([ '"{}"'.format(_) for _ in list(df.columns)])
	query  = "INSERT INTO %s(%s) VALUES %%s" % (table, cols)



	cursor = conn.cursor()


	try:
		extras.execute_values(cursor, query, tuples)
		conn.commit()
		cursor.close()
	except (Exception, pg.DatabaseError) as error:
		print("Error: %s" % error)
		conn.rollback()
		cursor.close()
		conn.close()
		sys.exit()



	print("  Orders writen.\n")


##############################    Order forms    ##############################

def brute_force_order(conn, date, order_number, elements):
	"""
	Generate randomily distributed points in VS to be managed 
	by the helmsman as a sinlge 'order'
	### (1) determin brute force dimensions, then calculate into order

	### (2) add 6i rnt info
	### (2) add state 
	### (3) add basis
	"""

	print('Generating order # {} via brute_force_order().'.format(order_number))


	### (1) add BF_var dimensions to order
	### calculate order size, warn user, then proceded:
	BF_vars = {} 	# brute force variables
	
	for _ in camp.target_rnt.keys():
		if isinstance(camp.target_rnt[_][1], (list)): 	
			BF_vars['"{}_morr"'.format(_)] = camp.target_rnt[_][1]
		if isinstance(camp.target_rnt[_][2], (list)):
			BF_vars['"{}_rkb1"'.format(_)] = camp.target_rnt[_][2]

	for _ in camp.vs_state.keys():
		if isinstance(camp.vs_state[_], (list)):
			BF_vars[_] = camp.vs_state[_]	
	
	for _ in camp.vs_basis.keys(): 		
		### cycle through basis species		
		if isinstance(camp.vs_basis[_], list): 	
			BF_vars[_] = camp.vs_basis[_]

	
	### warn user of dataframe size to be built
	order_size = camp.reso**len(BF_vars)
	if order_size > 100000:
		answer = input('\n\n The brute force method will generate {} \n\
    VS samples. Thats pretty fucking big.\n\
    Are you sure you want to proceed? (Y E S/N)\n'.format(order_size))
		if answer == 'Y E S':
			pass
		else:
			sys.exit("ABORT !")
	
	df = process_BF_vars(BF_vars, camp.reso)
	
	### value precision in postgres table
	precision = 6


	### unique id column. also sets row length, to which all 
	### following constants will follow
	df['uuid']  = [uuid.uuid4().hex for _ in range(order_size)] 	
	
	df['camp']  = camp.name
	
	### file name numbers
	df['file']  = list(range(order_size))	
	
	df['ord']   = order_number
	
	df['birth'] = date
	
	### run codes.  This variable houses error codes once the orders 
	### of been executed
	df['code'] 	= 0 


	### (2) add vs_rnt dimensions to orders
	for _ in camp.target_rnt.keys():
		### handle morr
		if isinstance(camp.target_rnt[_][1], (list)): 	
			vals = [float(np.round(random.uniform(camp.target_rnt[_][1][0],
				camp.target_rnt[_][1][1]), precision)) for i in 
				range(order_size)]
			df['{}_morr'.format(_)] = vals

		else:
			### _ is fixed value. n = order_size is automatic for a 
			### constant given existing df length
			df['{}_morr'.format(_)] = float(np.round(camp.target_rnt[_][1], 
				precision))

		### handle rkb1
		if isinstance(camp.target_rnt[_][2], (list)):
			pass
		else:
			### is fixed value. n = order_size is automatic for a 
			### constant given existing df length
			df['{}_rkb1'.format(_)] = float(np.round(camp.target_rnt[_][2], 
				precision))


	### (3) add fixed vs_state dimensions to orders
	for _ in camp.vs_state.keys():
		if isinstance(camp.vs_state[_], (list)):
			pass
		else:
			### is fixed value. n = order_size is automatic for a constant 
			### given existing df length
			df['{}'.format(_)] = float(np.round(camp.vs_state[_], precision))


	###	(4) add fixed vs_basis dimensions to orders
	for _ in camp.vs_basis.keys(): 		
		
		### cycle through basis species		
		if isinstance(camp.vs_basis[_], list): 	
			pass
		else:
			### is fixed value. n = order_size is automatic for a constant 
			### given existing df length
			vals = np.round(camp.vs_basis[_], precision)
			df['{}'.format(_)] = float(vals)



	### stack df's together
	### calculate element totals columns 
	### aqueous element totals. vs point-local dictionary
	ele_totals = {}
	for _ in elements:
		ele_totals[_] = [0]*order_size


	### build element totals one element at a time, as multiple vs spcies may
	### contain the same element.

	for _ in elements:
		### for a given element	present in the campaign	
		
		local_vs_sp = []
		for b in list(slop_df.index):	

			### for species listed/constrained in vs
			sp_dict = species_info(b)# keys = constiuent elements, values= sto

			if _ in sp_dict.keys():
				### if element _ in vs species, store in 
				### local_vs_sp as ['vs sp name', 
				### sto_of_element_in_sp]
				local_vs_sp.append([b, sp_dict[_]])	


		### build total element molality column into VS df		
		for b in local_vs_sp:
			### for each species b in loaded data0 that contins target element _,
			### identify the ones that are loaded in vs (list(df.columns)).
			if '{}'.format(b[0]) in list(df.columns): 
				### basis is present in campaign, so add its molalities 
				### to element total
				ele_totals[_] = ele_totals[_] + float(b[1])*(  10**df['{}'.format(b[0])]  )
		
				### technical note: recalculating the amount of "O" present by evaluating
				### the postgres database in psql with 
				###     ( select (4*10^"SO4-2" + 3*10^"HCO3-" 
				###      + 3*10^"B(OH)3" + 2*10^"SiO2" + 4*10^"HPO4-2" 
				###      + 3*10^"NO3-"), 10^"O" from teos_cal_2_vs;)
				### reveals potential machine errror magnitudes. as the element totals calculated
				### in the lines immediately preceduing this comment are off by +- 10^-7->10^-9 
				### from the psql derived totals. THis is problematic given that I do evalute element
				### totals across 10^-7 --> 10^-9  concentrations. I imagine thaty i can decrese
				### this error by not moving between log and normal so many times.

		
		df['{}'.format(_)] = np.round(np.log10(ele_totals[_]), precision)


	print(df)
	### reorder columns to match VS table
	cols = get_column_names(conn, '{}_vs'.format(camp.name))
	df = df[cols]

	print('  Order # {} established (n = {})\n'.format(order_number, order_size))


	return df

def process_BF_vars(BF_vars, reso):
	"""
	create dataframe containing all samples brute force samples
	"""
	exec_text = 'grid = np.mgrid['
	for _ in BF_vars:
		### want reso = number of sample poiunts to capture min and max values
		### hence manipulation of the max value 
		min_val = BF_vars[_][0] #-8
		max_val = BF_vars[_][1] #-6
		step = (max_val - min_val) / (reso - 1)
		build_str = '{}:{}:{}'.format(min_val, max_val + step, step)
		exec_text = '{}{},'.format(exec_text, build_str)

	exec_text = '{}].reshape({},-1).T'.format(exec_text[:-1], len(BF_vars))

	exec(exec_text, locals(), globals())

	return pd.DataFrame(grid, columns = list(BF_vars.keys()))

def random_uniform_order(date, order_number, order_size, elements):
	"""
	Generate randomily sampled points in VS to be managed by the 
	helmsman as a sinlge 'order'
	### (1) add info to all runs
	### (2) add 6i rnt info
	### (2) add state 
	### (3) add basis
	"""

	print('Generating order # {} via random_uniform.'.format(order_number))
	### value precision in postgres table
	precision = 6
	


	### (1) add run info to orders
	df          = pd.DataFrame()

	### unique id column. also sets row length, to which all 
	### following constants will follow
	df['uuid']  = [uuid.uuid4().hex for _ in range(order_size)] 	
	
	df['camp']  = camp.name
	
	### file name numbers
	df['file']  = list(range(order_size))	
	
	df['ord']   = order_number
	
	df['birth'] = date
	
	### run codes.  This variable houses error codes once the orders 
	### of been executed
	df['code'] 	= 0 

	

	### (2) add vs_rnt dimensions to orders
	for _ in camp.target_rnt.keys():
		### handle morr
		if isinstance(camp.target_rnt[_][1], (list)): 	
			###	_ is range, thus make n=order_size random choices within 
			### range  
			vals = [float(np.round(random.uniform(camp.target_rnt[_][1][0],
				camp.target_rnt[_][1][1]), precision)) for i in 
				range(order_size)]
			df['{}_morr'.format(_)] = vals
		else:
			### _ is fixed value. n = order_size is automatic for a 
			### constant given existing df length
			df['{}_morr'.format(_)] = float(np.round(camp.target_rnt[_][1], 
				precision))



		### handle rkb1
		if isinstance(camp.target_rnt[_][2], (list)):
			###	 is range, thus make n=order_size random choices within 
			### range
			vals = [float(np.round(random.uniform(camp.target_rnt[_][2][0], 
				camp.target_rnt[_][2][1]), precision)) for i in 
				range(order_size)]
			df['{}_rkb1'.format(_)] = vals
		else:
			### is fixed value. n = order_size is automatic for a 
			### constant given existing df length
			df['{}_rkb1'.format(_)] = float(np.round(camp.target_rnt[_][2], 
				precision))



	### (3) add vs_state dimensions to orders
	for _ in camp.vs_state.keys():
		if isinstance(camp.vs_state[_], (list)):
			if _ == "P_bar":
				### P is limited tot data0 step size (currently 0.5 bars)
				P_options  = [_/2 for _ in list(range(int(2*camp.vs_state[_][0]), int(2*camp.vs_state[_][1])))]
				vals = [random.choice(P_options) for i in range(order_size)]
			else:
				###	 is range, thus make n=order_size random choices within range
				vals = [float(np.round(random.uniform(camp.vs_state[_][0], 
					camp.vs_state[_][1]), precision)) for i in range(order_size)]
			df['{}'.format(_)] = vals

		else:
			### is fixed value. n = order_size is automatic for a constant 
			### given existing df length
			df['{}'.format(_)] = float(np.round(camp.vs_state[_], precision))



	###	(4) add vs_basis dimensions to orders
	for _ in camp.vs_basis.keys(): 		
		
		### cycle through basis species		
		if isinstance(camp.vs_basis[_], list): 	
			###	 is range, thus make n=order_size random choices within range
			vals = [float(np.round(random.uniform(camp.vs_basis[_][0], 
				camp.vs_basis[_][1]), precision)) for i in range(order_size)]
			df['{}'.format(_)] = vals

		else:
			### is fixed value. n = order_size is automatic for a constant 
			### given existing df length
			vals = np.round(camp.vs_basis[_], precision)
			df['{}'.format(_)] = float(vals)



	### calculate element totals columns 
	### aqueous element totals. vs point-local dictionary
	ele_totals = {}
	for _ in elements:
		ele_totals[_] = [0]*order_size


	### build element totals one element at a time, as multiple vs spcies may
	### contain the same element.

	for _ in elements:
		### for a given element	present in the campaign	
		
		local_vs_sp = []
		for b in list(slop_df.index):	

			### for species listed/constrained in vs
			sp_dict = species_info(b)# keys = constiuent elements, values= sto

			if _ in sp_dict.keys():
				### if element _ in vs species, store in 
				### local_vs_sp as ['vs sp name', 
				### sto_of_element_in_sp]
				local_vs_sp.append([b, sp_dict[_]])	


		### build total element molality column into VS df		
		for b in local_vs_sp:
			### for each species b in loaded data0 that contins target element _,
			### identify the ones that are loaded in vs (list(df.columns)).
			if '{}'.format(b[0]) in list(df.columns): 
				### basis is present in campaign, so add its molalities 
				### to element total
				ele_totals[_] = ele_totals[_] + float(b[1])*(  10**df['{}'.format(b[0])]  )
		
				### technical note: recalculating the amount of "O" present by evaluating
				### the postgres database in psql with 
				###     ( select (4*10^"SO4-2" + 3*10^"HCO3-" 
				###      + 3*10^"B(OH)3" + 2*10^"SiO2" + 4*10^"HPO4-2" 
				###      + 3*10^"NO3-"), 10^"O" from teos_cal_2_vs;)
				### reveals potential machine errror magnitudes. as the element totals calculated
				### in the lines immediately preceduing this comment are off by +- 10^-7->10^-9 
				### from the psql derived totals. THis is problematic given that I do evalute element
				### totals across 10^-7 --> 10^-9  concentrations. I imagine thaty i can decrese
				### this error by not moving between log and normal so many times.

		
		df['{}'.format(_)] = np.round(np.log10(ele_totals[_]), precision)


	print('  Order # {} established (n = {})\n'.format(order_number, order_size))


	return df


if __name__ == "__main__":
	main()


