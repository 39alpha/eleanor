=======
Eleanor
=======

Eleanor is a package for large scale aqueous geochemical modelling. It is based on the thermodynamic modelling software
EQ3/6. Eleanor provides a means to generate huge volumes of simulated thermodynamic data by defining problems which
automatically deployed to EQ3/6. The goal of this tool is to allow users to focus on problem specification, 
collecting the underlying thermodynamic data and visualizing results, rather than on writing code to wrap EQ3/6.


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
