Using Eleanor
-------------

A warning
^^^^^^^^^
The goal of this code is to make running geochemical models at scale easier. Running those models
and getting an answer without an error does not mean you've set up a physically meaningful model.
This software is not a substitute for a principled understanding of the underlying chemistry.
While we hope other scientists can use this software to help answer questions about their system of
interest, we also recognize that there are likely more ways to use this software incorrectly than
correctly. We aim to protect against these cases but that attempt will always be incomplete.

All of this is to say - we hope this project helps you do science faster. But faster doesn't mean
correct.

Setting up a problem
^^^^^^^^^^^^^^^^^^^^

``data0``
^^^^^^^^^
@TUCKER NEEDS TO DESCRIBE DATA0 FILES


``Campaign`` json files
^^^^^^^^^^^^^^^^^^^^^^^
Details of setting up a Campaign JSON


Command line tools
^^^^^^^^^^^^^^^^^^

With ``eleanor`` installed you can use a command line tool to run the standard workflow.
Prepare your ``Campaign`` file and run ``data0`` files and then simply run ``eleanor`` anywhere
on your machine as::

    $ eleanor -c CAMPAIGN_FILE.json -d PATH/TO/DATA0

where ``CAMPAIGN.json`` is your campaign json and ``PATH/TO/DAT0`` is the relative path from your
current directory to your data0 files.

If for some reason you want to run the ``Navigator`` or ``Helmsman`` independently,
you can do that with a similar structure::

    $ navigator -c CAMPAIGN_FILE.json -d PATH/TO/DATA0
    $ helmsman -c CAMPAIGN_FILE.json -d PATH/TO/DATA0

These command line tools have more functionality which is detailed in the documentation.

Understanding the outputs
^^^^^^^^^^^^^^^^^^^^^^^^^

When you run ``eleanor`` (or the ``Helmsman``) will make a new folder in your current directory with
the same name provided in the ``Campaign`` file. Initially this folder will have the following contents::

    campaign_name/
    |-- huffer/
    |----- test.3i
    |----- test.3o
    |----- test.3p
    |-- figs/
    |-- order_1/
    |----- 0/
    |-------- 0.3i
    |-------- 0.3o
    |-------- 0.3p
    |-------- 0.6i
    |-------- 0.6o
    |-------- 0.6p
    |----- 1/
    |----- 2/
    |----- ...
    |-- orders/
    |----- campaign.json
    |----- '[HASH]'.json
    |-- campaign.sql

All the simulation data is stored in the ``campaign.sql`` database (which is always named
``campaign.sql`` regardless of the campaign name). The database can be easily queried using ``sqlite3``
which is a standard library in Python 3, there are also some command line tools below to access the data.

The ``orders`` folder contains copy of the most recently order run, and a copy of all unique orders, which are
named by the hash of the order. These exist to ensure reproducibility of all runs. Any data can be recreated by
running eleanor again with a copy of the original ``Campaign`` file.

The other folders contain raw input/output files for the EQ3/6 runs which can be useful as a diagnostic tool for
understanding the outputs. Each folder in ``order_1`` is a single point in the equilibrium space. Not all calculations
are saved only a handful are saved for diagnostic purposes. This can be changed (see docs) # TODO

Running the ``eleanor`` command will use the campaign file to run the ``Navigator`` which will generate
points in a variable space to be simulated using ``EQ3/6``, once those points have been generated the
``Helmsman`` actually generates the required files and returns the equilibrium values.

If you don't know what a 3i, 3o, 3p, 6i or 6o file are, you should consult the documentation of EQ3/6.

``campaign.sql``
^^^^^^^^^^^^^^^^
For a variety of reasons ``eleanor`` saves data in a ``SQLite3`` database. This can be queried directly using
``sqlite3`` for example if you wanted to know the pH, and temperature of the equilibrium values, you can do this::

    $ sqlite3 campaign_name/campaign.sql
    sqlite3> SELECT -"H+", T_cel FROM es;
    -"H+"|T_cel
    6.2891|5.27
    6.3239|5.91
    7.4735|5.82
    6.7629|5.59
    7.2042|5.38
    ...

The tables in the ``campaign.sql`` database are ``vs``, ``es6``, and ``orders``. They store different information about
the campaign calculations.

The ``vs`` table is created by the ``Navigator`` functionality. It's a list of initial
conditions to be simulated. After the simulations are run the ``vs`` table is updated with an exit code that records any
errors and successful runs.

The ``es6`` table records the result of the equilibrium calculations, it contains the activities of all the components of
the equilibrium system.
