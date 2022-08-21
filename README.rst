=======
Eleanor
=======

Eleanor is a package for large scale aqueous geochemical modelling. It is based on the thermodynamic modelling software
EQ3/6. Eleanor provides a means to generate huge volumes of simulated thermodynamic data by defining problems which
automatically deployed to EQ3/6. The goal of this tool is to allow users to focus on problem specification, 
collecting the underlying thermodynamic data and visualizing results, rather than on writing code to wrap EQ3/6.

Install
-------

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

With those dependencies install Eleanor can be installed by cloning 
`the repository <https://github.com/39alpha/eleanor>_`, and installing via pip::

    $ git clone https://github.com/39alpha/eleanor
    $ cd eleanor
    $ pip install .

Using Eleanor
=============

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
--------------------

``data0``
^^^^^^^^^
Description of data0 files, where they come from, what they mean, and how they change the outcomes.


``Campaign`` json files
^^^^^^^^^^^^^^^^^^^^^^^
Details of setting up a Campaign JSON 


Command line tools
------------------

With ``eleanor`` installed you can use a command line tool to run the standard workflow. 
Prepare your ``Campaign`` file and run ``data0`` files and then simply run ``eleanor`` anywhere 
on your machine as::

    $ eleanor -c CAMPAIGN_FILE.json -d PATH/TO/DATA0

where ``CAMPAIGN.json`` is your campaign json and ``PATH/TO/DAT0`` is the relative path from your 
current directory to your data0 files. 

Running the ``eleanor`` command will use the campaign file to run the ``Navigator`` which will generate 
points in a variable space to be simulated using ``EQ3/6``, once those points have been generated the
``Helmsman`` actually generates the required files and returns the equilibrium values.

If for some reason you want to run the ``Navigator`` or ``Helmsman`` independently, 
you can do that with a similar structure::

    $ navigator -c CAMPAIGN_FILE.json -d PATH/TO/DATA0
    $ helsman -c CAMPAIGN_FILE.json -d PATH/TO/DATA0

These command line tools have more functionality which is detailed in the document.

Scripting with the ``eleanor`` package
--------------------------------------



Documentation
-------------

Information and link to complete documentation

Building the Docs
^^^^^^^^^^^^^^^^^

If you would like to build the docs locally, you'll need to install
`sphinx <https://www.sphinx-doc.org/en/master/>`_ and the `bootstrap sphinx
theme <https://ryan-roemer.github.io/sphinx-bootstrap-theme/README.html>`_::

    $ pip install sphinx sphinx_bootstrap_theme


Once that's done, you can make the docs. Just run the following if you are on Linux of macOS::

    $ make -C docs html
