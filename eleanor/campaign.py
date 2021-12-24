# pylint: disable=too-few-public-methods
"""
.. currentmodule:: eleanor.campaign

The :class:`Campaign` class contains the specification of modeling objectives.
"""
import json
from os import mkdir
from os.path import isdir, join
from .hanger import tool_room

class Campaign:
    """
    The Campaign class is used to specify modeling objectives.

    .. autosummary:
       :nosignatures:

       create_campaign_env

    :param config: a campaign configuration
    :type config: dict
    """
    def __init__(self, config):
        # In case we need anything else just store it in _raw
        self._raw = config
        # Metadata
        self.name = self._raw['campaign']
        self.notes = self._raw['notes']
        self.est_date = self._raw['est_date']
        self.target_rnt = self._raw['reactant']
        # modelling data
        self.suppress_min = self._raw['suppress min']
        self.min_supp_exemp = self._raw['suppress min exemptions']
        # self.reso = self._raw['bf resolution']
        self.cb = self._raw['initial fluid constraints']['cb']
        self.vs_state = {key: self._raw['initial fluid constraints'][key] for key in
                         ['T_cel', 'P_bar', 'fO2']}
        self.vs_basis = self._raw['initial fluid constraints']['basis']

        self.distro = self._raw['vs_distro']
        # if distro == BF, reso = numebr of subdivision on each var
        # if distro == random, reso = total numebr of vs points in order
        self.reso = self._raw['resolution']

        self.SS = self._raw['solid solutions']
        if self.SS:
            iopt4 = '1'
        else:
            iopt4 = '0'

        # It's best not to create the directory structure at intialization time. Doing so makes
        # testing more difficult, and means we have to be careful when and where Campaign objects
        # are created.
        #
        # self.create_env()

        self.local_3i = tool_room.Three_i(self.cb)
        self.local_6i = tool_room.Six_i(suppress_min=self.suppress_min,
                                        iopt4=iopt4,
                                        min_supp_exemp=self.min_supp_exemp)

    def create_env(self, dir='.', verbose=True):
        """
        Prepare a directory to store information about the campaign.
        """
        # Top level directory
        campaign_dir = join(dir, self.name)
        if not isdir(campaign_dir):
            if verbose:
                print(f'Creating campaign directory {campaign_dir}')
            mkdir(campaign_dir)

            huffer_dir = join(campaign_dir, 'huffer')
            mkdir(huffer_dir)

        # Check Figure directory
        fig_dir = join(campaign_dir, 'fig')
        if not isdir(fig_dir):
            mkdir(fig_dir)

        # Write campaign spec to file (as a hard copy)
        campaign_json = join(campaign_dir, 'campaign.json')
        with open(campaign_json, mode='w', encoding='utf-8') as handle:
            json.dump(self._raw, handle, indent=True)

    @classmethod
    def from_json(cls, fname):
        """
        Create a :class:`Campaign` from the contents of a JSON file.

        :param fname: path to the campain JSON file
        :type fname: str

        :return: a :class:`Campaign`
        :rtype: eleanor.eleanor.Campaign
        """
        with open(fname, 'r') as handle:
            data = json.load(handle)
            return cls(data)
