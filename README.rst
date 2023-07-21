=======
Eleanor
=======
Eleanor is a package for large scale aqueous geochemical modelling. It is based
on the thermodynamic modelling software EQ3/6. Eleanor provides a means to
generate huge volumes of simulated thermodynamic data by defining a specific
type of problems that are automatically deployed to EQ3/6. The goal of this
tool is to allow users to focus on problem specification. Notably, Eleanor is
only designed to employ specific subsets of the eq36 family, and is not
suitable for handling some EQ3/6 functionality. The example problem that
deploys with Eleanor describes and exemplifies the type of geochemical problem
Eleanor was built to evaluate.


Dependencies
^^^^^^^^^^^^
Eleanor requires Python3, pip, and EQ3/6 as dependencies. Eleanor is only
supported on macOS and Unix systems. Windows users are encouraged to checkout
the Windows Subsystem for Linux to use Eleanor.

Eleanor requires the version of `EQ3/6 hosted by 39 Alpha
<https://github.com/39alpha/eq3_6>`_. which has been slightly modified to
handle input/output files slightly differently, but is otherwise identical to
v8.0 released by Lawrence Livermore National Lab. That version can be found on
github here, it requires ``gfortran`` to build.

* macOS or Unix
* Python 3.8 (or later)
* ``pip``
* ``gfortran`` (v9.3.0 or later)
* `EQ3/6 <https://github.com/39alpha/eq3_6>`_ 


Install
^^^^^^^
With those dependencies installed Eleanor can be installed by cloning `the
repository <https://github.com/39alpha/eleanor>`_, and installing via pip::

    $ git clone https://github.com/39alpha/eleanor
    $ cd eleanor
    $ pip install .


User Notes
^^^^^^^^^^
Eleanor is designed to use specific (and limited) functionality within EQ3/6 to
inform on a specific type of geochemical problem. We wanted to know, what are
all of the fluid compositions that are consistent with very limited
environmental signals, specific if we know that a given mineral or mineral/s is
equilibrium with the fluid. Eleanor allows a user to consider uncertainty in
unknown variables by setting them to ranges, instead of leaving them out or
setting them to arbitrary values. We walk through an example use case in
Example_0 provided with Eleanor where we explore the fluids the care derived
from calcite and aragonite on the seafloor, when the water column sets ranges
on total element abundances for example, instead of picking a specific values
for a basis species. As such, a large number of user controls in EQ3/6 do not
port though to Eleanor.

A few notable limitation, for those familiar with EQ3/6:

1. Eleanor does not allow you to set basis species to homogeneous or
   heterogeneous equilibrium (except for fO2).
2. Special basis switching is enabled, but general basis switching is not.
3. Ion exchangers are not used.
4. Special reactants are not allowed in EQ6, only minerals and gases for the
   time being.
5. Fluid mixing is not currently enabled.
6. In EQ6, Eleanor only populates the SQL database with the data from the last
   Xi step in the 6o file, the final step in the reaction path. Therefore the
   SQL databases associated with a given campaign contain the initial
   constraints (VS, or variable space table), the data retrieved from the 3o
   files (ES3, or Equilibrium Space 3o table), and the data retrieved form the
   last Xi step in the 6o files (ES6, or, Equilibrium Space 6o table).
