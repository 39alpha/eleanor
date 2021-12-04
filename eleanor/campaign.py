import json
import tool_room


class Campaign(object):
    """The Campaign class defines the modelling objectives and priorities
        These include -
        
        
    """
    def __init__(self, file_name):
        self.file_name = file_name
        dat = json.load(open(file_name))
        # Metadata
        self.name           = dat['campaign']
        self.notes          = dat['notes']
        self.est_date       = dat['est_date']
        self.target_rnt     = dat['Reactant']
        # modelling data
        self.suppress_min   = dat['suppress min']
        self.min_supp_exemp = dat['supress min exemptions']
        self.reso           = dat['BF resolution']

        self.cb             = dat['Initial Fluid Constraints']['cb']
        self.vs_state       = {key: dat['Initial Fluid Constraints'][key] for key in [
                                'T_cel', 'P_bar', 'fO2']}
        self.vs_basis       = dat['Initial Fluid Constraints']['basis']
        
        self.target_rnt     = dat['Reactant']
        self.distro         = dat['VS_distro']

        ### if distro == BF, reso = numebr of subdivision on each var
        ### if distro == random, reso = total numebr of vs points in order
        self.reso           = dat['resolution']        

        # self.reso = dat.get("BF resolution", None)
        # if self.distro == "BF" and not self.reso:
        #     raise AttributeError('Brute force has been declared, but "BF resolution" has not')
        


        # In case we need anything else just store it in _raw
        self._raw = dat

        self.SS       = dat['Employ Solid Solutions']
        if self.SS == Ture:
            iopt4 = '1'
        else:
            iopt4 = '0'
            
        self.local_3i = tool_room.three_i(cb)
        self.local_6i = tool_room.six_i(suppress_min = self.suppress_min, iopt4 = iopt4, min_supp_exemp=self.min_supp_exemp)




    