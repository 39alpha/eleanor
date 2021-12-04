import json



class Campaign(object):
    """The Campaign class defines the modelling objectives and priorities
        These include -
        
        
    """
    def __init__(self, file_name):
        self.file_name = file_name
        dat = json.load(open(file_name))

        self.name           = dat['campaign']
        self.notes          = dat['notes']
        self.est_date       = dat['est_date']
        self.target_rnt     = dat['Reactant']

        self.suppress_min   = dat['suppress min']
        self.min_supp_exemp = dat['supress min exemptions']
        self.reso           = dat['BF resoliution']

        self.cb             = dat['Initial Fluid Constraints']['cb']
        self.vs_state = {key: dat['Initial Fluid Constraints'][key] for key in ['T_cel', 'P_bar', 'fO2']}

        # self.cb             = dat['Initial Fluid Constraints']['cb']

        # In case we need anything else just store it in _raw
        self._raw = dat
       
    




    