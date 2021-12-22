###
### radar tools
### functions used for viasualizing vs and ss data
### This file is loaded as a package by the radar family of
### codes.
###
### Tucker Ely 
### January 2021



import sys, os, random
from subprocess import * 
from time import *
from sklearn import preprocessing

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from mpl_toolkits.axes_grid1 import make_axes_locatable
from matplotlib.colors import ListedColormap, LinearSegmentedColormap


### custom packages
from .db_comms import *
from .tool_room import *

pwd = os.getcwd()



big_palette1 = ['#7CEA9C','#F433AB','#2E5EAA','#593959','#F0C808','#DD1C1A','#F05365','#FF9B42','#B2945B','#000000','#FF0000', '#FFA500', '#FFFF00', '#008000', '#0000FF', '#4B0082']

blu_gren = ['#7CEA9C', '#00B2CA']
blu_pnk = ['#F433AB', '#00B2CA']

big_palette2 = ['#ff0000', '#4F8BEB']



rainbow_blk = LinearSegmentedColormap.from_list("mycmap", ["#020004","#75228f","#3e53d2","#4eb01f","#ffd805","#fd9108","#dd2823"])
rainbow = LinearSegmentedColormap.from_list("mycmap", ["#75228f","#3e53d2","#4eb01f","#ffd805","#fd9108","#dd2823"])





		
def group_by_solids(conn, camp_name, ord_id):
	
	"""
	Determine each unique combination of precipitates in a order (ord_id)
	"""

	lines = grab_lines(os.path.join(pwd, '{}_huffer'.format(camp_name), 'test.3o'))
	solids 			= []
	solid_solutions	= []

	for _ in range(len(lines)):
		if re.findall('^\n', lines[_]):
			pass
		
		elif '           --- Saturation States of Pure Solids ---' in lines[_]:
			x = 4
			while not re.findall('^\n', lines[_ + x]): 	#	signals the end of the solid solutions block	
				if 'None' not in lines[_ + x]:
					solids.append(lines[_ + x][:30].strip())
					x += 1
				else:
					x += 1
			del x
		
		elif '           --- Saturation States of Solid Solutions ---' in lines[_]:
			x = 4
			while not re.findall('^\n', lines[_ + x]): 	#	signals the end of the solid solutions block	
				if 'None' not in lines[_ + x]:
					solids.append(lines[_ + x][:30].strip())
					x += 1
				else:
					x += 1
			del x

	all_precip = [_ for _ in solids + solid_solutions]# if _ != camp.tm] 		#	lsit of all possible precipaiutes, excluing the target mineral, which is in all files.


	### retrieve record of all_precip columns from postgres table 'camp.name', for order # 'ord_id'
	solids_sql   = ",".join([f'"{_}"' for _ in all_precip])
	all_rec = retrieve_postgres_record(conn, 'select {} from {}_es where ord = {}'.format(solids_sql, camp_name, ord_id))
	

	### find unique co-precipitation combinations 
	solid_combinations = [] 	#	build list for precipitation combinations


	for _ in all_rec:
		ind = []
		for x in range(len(_)):
			if _[x] > 0:
				ind.append(x)

		### grab index of values over 0,
		solid_combinations.append([all_precip[i] for i in ind])
	

	### unique mineral co-precipiation occrrances in  order # ord_id
	unique_combinations = [ list(x) for x in set(tuple(x) for x in solid_combinations) if list(x) !=[]] + ['']

	### dictionary of unique mineral combinations, with an int index to reference color
	### this random association between the names and the color, once established here, presists.
	combo_dict = {}
	for _ in range(len(unique_combinations)):
		### z_dict['miner_set_name'] = index
		combo_dict['_'.join(unique_combinations[_])] = _

	return combo_dict



def solid_groups(conn, pwd, camp_name, ord_id, out = 'assemblages'):
    
    """
    color plot points based on the solids present, with
    each unique combination of precipiotates getting its own color
    and/or its own unique marker.
    ord_id = order #
    """


    ### determine list of all solids in ss columns
    lines = grab_lines(os.path.join(pwd, '{}_huffer'.format(camp_name), 'test.3o'))
    solids          = []
    solid_solutions = []



    for _ in range(len(lines)):
        if re.findall('^\n', lines[_]):
            pass
        elif '           --- Saturation States of Pure Solids ---' in lines[_]:
            x = 4
            while not re.findall('^\n', lines[_ + x]):  #   signals the end of the solid solutions block    
                if 'None' not in lines[_ + x]:
                    solids.append(lines[_ + x][:30].strip())
                    x += 1
                else:
                    x += 1
            del x
        elif '           --- Saturation States of Solid Solutions ---' in lines[_]:
            x = 4
            while not re.findall('^\n', lines[_ + x]):  #   signals the end of the solid solutions block    
                if 'None' not in lines[_ + x]:
                    solids.append(lines[_ + x][:30].strip())
                    x += 1
                else:
                    x += 1
            del x


    all_precip = [_ for _ in solids + solid_solutions]


    if out == 'phases':
        ### only the list of solids is wanted
        return all_precip


    if out == 'assemblages':
        ### assemblage names are wanted in conjunction with a specifc 
        ### ord_id in camp_name


        ### retrieve ss postgres record 
        solids_sql   = ",".join([f'"{_}"' for _ in all_precip])
        all_rec = retrieve_postgres_record(conn, 'select {} from {}_es where ord = {}'.format(solids_sql, camp_name, ord_id))
        
        ### find unique co-precipitation combinations 
        ### build list for precipitation combinations
        solid_combinations = []     
        for _ in all_rec:
            ind = []
            for x in range(len(_)):
                if _[x] >= 0:
                    ### if affinity >= 0 ie precipitation either happend or 
                    ### would have if precip was turned on.
                    ind.append(x)                    
            ### grab index of values over 0,
            solid_combinations.append([all_precip[i] for i in ind])
        ### unique mineral co-precipiation occrrances in  order # ord_id
        unique_combinations = [ list(x) for x in set(
            tuple(x) for x in solid_combinations) if list(x) !=[]] + ['']


        ### dictionary of unique mineral combinations, with an int index 
        ### to reference color. This random association between the names 
        ### and the color, once established here, presists.
        combo_dict = {}
        for _ in range(len(unique_combinations)):
            ### z_dict['miner_set_name'] = index
            combo_dict['_'.join(unique_combinations[_])] = _


        ### generate color index as the combintion of minerals names precipiated
        z_ind = ['_'.join(_) for _ in solid_combinations]
        
        return combo_dict




###################################################################################
################################  Color Fucntions  ################################
color_dict = {
		'1': ['#E76F51', '#264653', '#2A9D8F', '#F4A261', '#E9C46A', '#100B00', '#A5CBC3', '#3B341f', '#2F004F'],
		'2': ['#ff0000', '#ffa500', '#ffff00', '#008000', '#0000ff', '#4b0082', '#000000'],
		'3': ['#7CEA9C','#F433AB','#2E5EAA','#593959','#F0C808','#DD1C1A','#F05365','#FF9B42','#B2945B','#000000','#FF0000', '#FFA500', '#FFFF00', '#008000', '#0000FF', '#4B0082']
		}



def get_continuous_cmap(hex_list, float_list=None):
    ### https://towardsdatascience.com/beautiful-custom-colormaps-with-matplotlib-5bab3d1f0e72
    """
    Create and return a color map that can be used in heatmap figures. If :code:`float_list` is
    not provided, then the color map graduates linearly betwean each color in :code:`hex_list`.
    If :code:`float_list` is provided, then each each color in :code:`hex_list` is mapped to the
    respective location in :code:`float_list`.

    :param hex_list: hex-code strings
    :type hex_list: list
    :param float_list: Floating-point values between 0 and 1 with the same length as :code:`hex_list`. Must start with 0 and end with 1.
    :type float_list: list

    :return: A color map
    :rtype: matplotlib.colors.LinearSegmentedColormap
    """

    rgb_list = [rgb_to_dec(hex_to_rgb(i)) for i in hex_list]
    if type(float_list) != list:
        float_list = list(np.linspace(0,1,len(rgb_list)))
        
        
    cdict = dict()
    for num, col in enumerate(['red', 'green', 'blue']):
        col_list = [[float_list[i], rgb_list[i][num], rgb_list[i][num]] for i in range(len(float_list))]
        cdict[col] = col_list
    cmp = matplotlib.colors.LinearSegmentedColormap('my_cmp', segmentdata=cdict, N=256)
    return cmp

def hex_to_rgb(value):
    '''
    Converts hex to rgb colours
    value: string of 6 characters representing a hex colour.
    Returns: list length 3 of RGB values'''
    value = value.strip("#") # removes hash symbol if present
    lv = len(value)
    return tuple(int(value[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))

def rgb_to_dec(value):
    '''
    Converts rgb to decimal colours (i.e. divides each value by 256)
    value: list (length 3) of RGB values
    Returns: list (length 3) of decimal values'''
    return [v/256 for v in value]







Fe_O_S_palette = {
    '':"#000000",'PYRITE':"#02d625",
    'MAGNETITE_PYRITE':"#f7e14f", 'MAGNETITE_PYRRHOTITE':"#ff8c00", 'MAGNETITE':"#e6c785", # hot tones  (light to dark)
    'HEMATITE':"#3ad4f2", 'HEMATITE_MAGNETITE':"#146ee3", 'HEMATITE_PYRITE':"#0211b5",  # cold tones (light to dark)
    'HEMATITE_MAGNETITE_PYRITE':"#ff05b0", "MAGNETITE_PYRITE_PYRRHOTITE":"#ff0000"
    }


# Fe_O_S_palette = {
#     '':"#000000",'PYRITE':"#e60000",
#     'MAGNETITE_PYRITE':"#f7e14f", 'MAGNETITE_PYRRHOTITE':"#ff8c00", 'MAGNETITE':"#02d625", # hot tones  (light to dark)
#     'HEMATITE':"#c2c0c0", 'HEMATITE_MAGNETITE':"#5e5d5d", 'HEMATITE_PYRITE':"#1c0069",  # cold tones (light to dark)
#     'HEMATITE_MAGNETITE_PYRITE':"#3ad4f2", "MAGNETITE_PYRITE_PYRRHOTITE":"#146ee3"
#     }

Fe_O_S_rainbow = {
    '':"#757575",
    'PYRITE':"#E9110C",
    'MAGNETITE_PYRITE':"#E9640C",
    'MAGNETITE_PYRRHOTITE':"#E9C70C",
    'MAGNETITE':"#21C9A1",
    'HEMATITE':"#00AF1D",
    'HEMATITE_MAGNETITE':"#1C7EFB", 
    'HEMATITE_PYRITE':"#3508CA",
    'HEMATITE_MAGNETITE_PYRITE':"#F33BEE", 
    "MAGNETITE_PYRITE_PYRRHOTITE":"#000000"
    }

CaMgSiH2O_pal_original = {
    "AHM"     : "#E9110C",
    "AIM"     : "#3508CA",
    "mtc-brc-ctl" :"#FF2EE1",
    "mtc-di-ctl"  :"#F52B1D",
    "di-ctl-tr"   :"#000000",
    "ctl-tlc-tr"  :"#3508CA",
    "mtc-brc" : "#E9C70C",
    "ctl-brc" : "#21C9A1",
    "mtc-ctl" : "#00AF1D",
    "mtc-di"  : "#1C7EFB",
    "di-ctl"  : "#FF842E",
    "di-tr"   : "#F6D71E",
    "ctl-tr"  : "#A3F61E",
    "ctl-tlc" : "#6FDBF9",
    "tlc-tr"  : "#f7e14f",
    "mtc_only": "#ff8c00",
    "brc_only": "#e6c785",
    "ctl_only": "#FF9CF1",
    "di_only" : "#0211b5",
    "tr_only" : "#00AA07",
    "tlc_only": "#3508CA",
    'none'    : "#C3C3C3",
    }

CaMgSiH2O_pal_2 = {
    "AHM"     : "#E9110C",
    "AIM"     : "#3508CA",
    "mtc-brc-ctl" :"#e0d4a3",
    "mtc-di-ctl"  :"#F52B1D",
    "di-ctl-tr"   :"#21C9A1",
    "ctl-tlc-tr"  :"#3508CA",
    "mtc-brc" : "#E9C70C",
    "ctl-brc" : "#000000",
    "mtc-ctl" : "#00AF1D",
    "mtc-di"  : "#1C7EFB",
    "di-ctl"  : "#FF842E",
    "di-tr"   : "#F6D71E",
    "ctl-tr"  : "#A3F61E",
    "ctl-tlc" : "#6FDBF9",
    "tlc-tr"  : "#f7e14f",
    "mtc_only": "#ff8c00",
    "brc_only": "#e6c785",
    "ctl_only": "#FF9CF1",
    "di_only" : "#0211b5",
    "tr_only" : "#00AA07",
    "tlc_only": "#3508CA",
    'none'    : "#C3C3C3",
    'cpxN'    : "#3508CA",
    }


### bright pink "#ff05b0"
### light pink "#F46EF2"
### candy apple green "#00AA07"
### light lime green #A3F61E
### light grey.   "#C3C3C3"
### pink black blues "#146ee3" , "#0211b5" , "#ff05b0" , "#000000" 
### light blue.  "#146ee3"
### light blue    #6FDBF9
### sand #e6c785
### yellow   #F6D71E
### organe   #FF842E
### dark red  #9D0303 
###      red #ff0000
###      pink  #FF2EE1
### light pink #FF9CF1
