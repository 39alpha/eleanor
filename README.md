# Eleanor

A package for large scale aqueous geochemical modeling.


## Install

Install is as simple as

```pip install elanor```

### Environment Variable

You can specify where you want Eleanor to look for data0 files. The easiest thing to do 
is to modify your computer environment to set that globally
```$ export DATA0DIR=/path/to/db ```


## A warning

The goal of this code is to make running geochemical models at scale easier. Running those models
and getting an answer without an error does not mean you've set up a physically meaningful model.
This software is not a substitute for a principled understanding of the underlying chemistry.
While we hope other scientists can use this software to help answer questions about their system of
interest, we also recognize that there are likely more ways to use this software incorrectly than
correctly. We aim to protect against these cases but that attempt will always be incomplete.

All of this is to say - we hope this project helps you do science faster. But faster doesn't mean
correct.

## Dependencies

### EQ3/6

The easist way to understand what Eleanor is doing is to understand that its helping
you run geochemical simulations by calling `EQ3/6`. Naturally that means `EQ3/6`
is a required dependency. The original code is hosted by [Lawerence Livermore National
Lab](https://www-gs.llnl.gov/energy-homeland-security/geochemistry) but we have made a version
we host on [github](https://github.com/39alpha/eq3_6) , which we recommend. The only differences
between the code distributed by LLNL and the code we've put on git is in the way input/output data
is processed. We used continuous integration to ensure the "geochemistry" hasn't been affected by
our changes. See the docs on [github](https://github.com/39alpha/eq3_6) for more information.

### Other Python dependencies

NA

## data0 files

Description of data0 files, where they come from, what they mean, and how they change the outcomes.

## Documentation

Information and link to complete documentation

### Building the Docs

If you would like to build the docs locally, you'll need to install
[sphinx](https://www.sphinx-doc.org/en/master/) and the [bootstrap sphinx
theme](https://ryan-roemer.github.io/sphinx-bootstrap-theme/README.html).

```shell
$ pip install sphinx sphinx_bootstrap_theme
```

Once that's done, you can make the docs. Just run the following if you are on Linux of macOS

```shell
$ make -C docs html
```

or

```shell
$ cd docs
$ make.bat html
```
on Windows.

## Contributing the Eleanor

Some suggestions
