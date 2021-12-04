import json



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
        self.est_date       = dat['date']
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
        self.reso = dat.get("BF resolution", None)
        if self.distro == "BF" and not self.reso:
            raise AttributeError('Brute force has been declared, but "BF resolution" has not')
        # In case we need anything else just store it in _raw
        self._raw = dat
       
    




    