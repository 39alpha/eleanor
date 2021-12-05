""" The Campaign class for Eleanor contains the class methods for defining modelling objectives"""
import json
import os
from .hanger import tool_room

class Campaign(object):
    """The Campaign class defines the modelling objectives and priorities
        These include -
    """
    def __init__(self, file_name):
        self.file_name = file_name
        dat = json.load(open(file_name))
        # In case we need anything else just store it in _raw
        self._raw = dat
        # Metadata
        self.name = dat['campaign']
        self.notes = dat['notes']
        self.est_date = dat['est_date']
        self.target_rnt = dat['Reactant']
        # modelling data
        self.suppress_min = dat['suppress min']
        self.min_supp_exemp = dat['supress min exemptions']
        #self.reso           = dat['BF resolution']

        self.cb             = dat['Initial Fluid Constraints']['cb']
        self.vs_state       = {key: dat['Initial Fluid Constraints'][key] for key in [
                                'T_cel', 'P_bar', 'fO2']}
        self.vs_basis       = dat['Initial Fluid Constraints']['basis']
        
        self.target_rnt     = dat['Reactant']
        self.distro         = dat['VS_distro']

        ### if distro == BF, reso = numebr of subdivision on each var
        ### if distro == random, reso = total numebr of vs points in order
        self.reso           = dat['resolution']        

        self.SS       = dat['Employ Solid Solutions']
        if self.SS == True:
            iopt4 = '1'
        else:
            iopt4 = '0'

        self.create_campaign_env()
            
        self.local_3i = tool_room.Three_i(self.cb)
        self.local_6i = tool_room.Six_i(suppress_min = self.suppress_min, iopt4 = iopt4, min_supp_exemp=self.min_supp_exemp)


    def create_campaign_env(self):
        """ Prepare the local directory to store information about the campaign in a single 
            directory 
        """
        # Top level directory
        if not os.path.isdir(self.name):
            print("Building new Campaign folder based on name")
            os.mkdir(self.name)
            os.mkdir(os.path.join(self.name, "huffer"))
        # Check Figure directory
        if not os.path.isdir(os.path.join(self.name, "fig")):
            os.mkdir(os.path.join(self.name, "fig"))
        # Write campaign spec to file (as a hard copy)
        campaign_name_fname = os.path.join(self.name, self.name + ".json") 
        with open(campaign_name_fname, "w") as outfile:
            outfile.write(json.dumps(self._raw))


    
