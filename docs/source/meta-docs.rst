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


Contributing to ``eleanor``
---------------------------
If you run into an issue we hope you can diagnose the problem using the documentation.
If you've found a bug, please submit an issue on our `github repository <https://github.com/39alpha/eleanor>`_, and 
if you have a proposed resolution to the bug please submit a pull request. We aim to write `PEP8 <https://pep8.org/>`_ 
complaint code, but if you've fixed a bug for us we'll handle the linting in code review.
