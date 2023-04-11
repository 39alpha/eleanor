=======
Eleanor
=======

Eleanor is a package for large scale aqueous geochemical modelling. It is based on the thermodynamic modelling software
EQ3/6. Eleanor provides a means to generate huge volumes of simulated thermodynamic data by defining a specific 
type of problems that are automatically deployed to EQ3/6. The goal of this tool is to allow users to focus 
on problem specification. Notably, eleanor is only designed to employ specific sbsets of the eq36 family, 
and is not suitable for handling some EQ3/6 functionality. The example problem that deploys with eleanor descirbes and exemplifies the type of geocehmical problem eleanor was built to evaluate.


Dependencies
^^^^^^^^^^^^
Eleanor requires Python3, pip, and EQ3/6 as dependencies. Eleanor is only supported on macOS and Unix systems. 
Windows users are encouraged to checkout the Windows Subsystem for Linux to use Eleanor. 

Eleanor requires the version of `EQ3/6 hosted by 39 Alpha <https://github.com/39alpha/eq3_6>`_.
which has been slightly modified to handle input/output files slightly differently, but is otherwise
identical to v8.0 released by Lawrence Livermore National Lab. That version can be found on github here,
it requires ``gfortran`` to build.

* macOS or Unix
* Python 3.8 (or later)
* ``pip``
* ``gfortran`` (v9.3.0 or later)
* `EQ3/6 <https://github.com/39alpha/eq3_6>`_ 


Install
^^^^^^^
With those dependencies installed Eleanor can be installed by cloning 
`the repository <https://github.com/39alpha/eleanor>`_, and installing via pip::

    $ git clone https://github.com/39alpha/eleanor
    $ cd eleanor
    $ pip install .


User Notes
^^^^^^^^^^
Eleanor (version 1) is designed to use specfic (and limited) functionality within EQ3/6 to infomr on a specific type of geochemical problem. We wanted to know, what are all of the fluid compositions that are consitent with very limited environemntal signals, specific if we know that a given mineral or mineral/s  is equilibroium with the fluid. Eleanor allows a user to consider uncertianty in unknown vairables by setting them to ranges, intstead of leaveing them out or setting them to arbitrary values. We walk through an exmapl use case in Example_0 provided with elenore where we explore the fluids the care dervied from calcite and arragonite on the seafloor, when the water column 

set ranges on total element anudnaces for exmaple, instead of pickign a specific values for a basis species. As such, a large number of user controls in EQ3/6 do not port though to Eleanor. 

This suits the porposes of the types of problems that we designed version 1 eleanor to operate on. Additinally functionality will come with fiuture versions.


What eleanore does with EQ3/6



A few notabl limitation, for those framiliar with EQ3/6:
	(1) Eleanor does not allow you to set basis species to homogeneous or heterogeneous equilibriam (except for fO2).
	(2) Special basis swithcing is enabled, but general basis switching is not.
	(3) Ion exchangers are not used.
	(4) Special reactactants are not allowed in EQ6, only minerals and gases for the time being.
	(5) fluid mixing is not currently enabled.
	(6) In EQ6, eleanor only populates her sql databases with the data from the last Xi step in the 6o file, the final step in the reaction path. Therefore the sql databases associated with a given campaign contain the initial constrants (VS, or variable space table), the data retrieved from the 3o files (ES3, or Equilirium Space 3o table), and the data retrieved form the last Xi step in the 6o files (ES6, or, Equilirium Sapce 6o table). 




