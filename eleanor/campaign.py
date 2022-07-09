# pylint: disable=too-few-public-methods
"""
.. currentmodule:: eleanor.campaign

The :class:`Campaign` class contains the specification of modeling objectives.
"""
from .hanger import tool_room
from os import mkdir, rename
from os.path import isdir, join, realpath
import json
import shutil


class Campaign:
    """
    The Campaign class is used to specify modeling objectives, before the 
    Navigator and Helmsman are run.

    A Campaign can be initialized by either providing a dictionary
    configuration or using the :meth:`from_json` method to load
    from a JSON-formatted file.

    The following keys must exist in the dictionary or JSON file:

    - :code:`'campaign'` - the name of the campaign (:code:`str`)
    - :code:`'notes'` - any nodes about the campaign (:code:`str`)
    - :code:`'est_date'` - date of the campaign creation (:code:`str`)
    - :code:`'reactant'` - *TODO*
    - :code:`'suppress min'` - *TODO*
    - :code:`'suppress min exemptions'` - *TODO*
    - :code:`'initial fluid constraints'` - configuration of fluid constraints (:code:`dict`)
        - :code:`'T_cel'` - temperature in celsius (:code:`float` or :code:`List[float]`)
        - :code:`'P_bar'` - pressure in bars (:code:`float` or :code:`List[float]`)
        - :code:`'fO2'` - log oxygen fugacity (:code:`float` or :code:`List[float]`)
        - :code:`'cb'` - basis species to adjust for charge balance on (:code:`str` )
        - :code:`'basis'` - configuration of basis species and values (:code:`dict`)
    - :code:`'vs_distro'` - method for sampling variable space (vs) (:code:`str` )
    - :code:`'resolution'` - number of vs points in order ( if :code:`'vs_distro' == 'random')
                           - subdivisions on each non-fixed dimension ( if :code:`'vs_distro' ==
                             'BF')
    - :code:`'solid solutions'` - turn on solid solutions (:code:`bool`)

    .. autosummary:
       :nosignatures:

       create_campaign_env

    :param config: a campaign configuration
    :type config: dict
    """
    def __init__(self, config, data0_dir):
        self.data0_dir = realpath(data0_dir)
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
        self.cb = self._raw['initial fluid constraints']['cb']
        self.vs_state = {key: self._raw['initial fluid constraints'][key] for key in
                         ['T_cel', 'P_bar', 'fO2']}
        self.vs_basis = self._raw['initial fluid constraints']['basis']
        self.distro = self._raw['vs_distro']
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

        self.local_3i = tool_room.Three_i()
        self.local_6i = tool_room.Six_i(suppress_min=self.suppress_min,
                                        iopt4=iopt4,
                                        min_supp_exemp=self.min_supp_exemp)

        self._campaign_dir = None

        self._hash = None
        self._data0_hash = None

    @property
    def campaign_dir(self):
        """
        Get the current campaign directory. Will be :code:`None` if :meth:`create_env` has not been
        called.

        :return: the current campaign directory
        :rtype: str or None
        """
        return self._campaign_dir

    @property
    def campaign_db(self):
        if self._campaign_dir is None:
            error_msg = "campaign environment not created; cannot get campaign database path"
            raise RuntimeError(error_msg)
        return join(self._campaign_dir, 'campaign.sql')

    @property
    def hash(self):
        return self._hash

    @property
    def data0_hash(self):
        return self._data0_hash

    @property
    def order_file(self):
        return join(self.campaign_dir, 'orders', self.hash + '.json')

    def create_env(self, dir=None, verbose=True):
        """
        Prepare a directory to store information about the campaign, and save the absolute path in
        :attr:`campaign_dir`.

        This method will create the following directory and file structure: ::

           {dir}/{name}
           |
           +-- huffer
           |
           +-- fig
           |
           +-- orders

        where :code:`{dir}` is the root directory, :code:`{name}` is the campaign name,
        and :code:`huffer`, :code:`fig` and :code:`orders` are directories.

        :param dir: The root directory in which to create the campaing directory
        :type dir: str
        :param verbose: Generate verbose terminal output
        :type verbose: bool
        """
        # Top level directory
        if dir is None and self._campaign_dir is None:
            self._campaign_dir = realpath(join('.', self.name))
        elif dir is not None:
            self._campaign_dir = realpath(join(dir, self.name))

        if not isdir(self.campaign_dir):
            if verbose:
                print(f'Creating campaign directory {self.campaign_dir}\n')
            mkdir(self.campaign_dir)

            huffer_dir = join(self.campaign_dir, 'huffer')
            mkdir(huffer_dir)

        # Check figure directory
        fig_dir = join(self.campaign_dir, 'fig')
        if not isdir(fig_dir):
            mkdir(fig_dir)

        order_dir = join(self.campaign_dir, 'orders')
        if not isdir(order_dir):
            mkdir(order_dir)

        # Write campaign spec to file (as a hard copy)
        order_json = join(order_dir, 'campaign.json');
        with open(order_json, mode='w', encoding='utf-8') as handle:
            json.dump(self._raw, handle, indent=True)

        self._hash = tool_room.hash_file(order_json)
        shutil.copyfile(order_json, self.order_file)

        self._data0_hash = tool_room.hash_dir(self.data0_dir)

    def working_directory(self, *args, **kwargs):
        """
        Return a context manager for switching into and out of the campaign directory.

        This will create the campaign directory if it doesn't already exist using
        :meth:`create_env`. Any arguments passed to this method will be forwarded there.
        """
        self.create_env(*args, **kwargs)
        return tool_room.WorkingDirectory(self.campaign_dir)

    @classmethod
    def from_json(cls, fname, *args, **kwargs):
        """
        Create a :class:`Campaign` from the contents of a JSON file.

        :param fname: path to the campain JSON file
        :type fname: str

        :return: a :class:`Campaign`
        :rtype: eleanor.eleanor.Campaign
        """
        with open(fname, 'r') as handle:
            data = json.load(handle)
            return cls(data, *args, **kwargs)
