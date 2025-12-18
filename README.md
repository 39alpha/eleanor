# Eleanor

Aqueous speciation modeling has historically focused on specific, well defined systems, and is ideal for laboratory
settings or the study of a small number of real-world systems. Standard tools such as Geochemist's Workbench and EQ3/6
exist to fill this niche, alongside more recent additions such as the WORM Portal. However, existing tools are not ideal
for the study of systems that are underspecified (e.g. have incomplete composition), have high degrees of uncertainty
(e.g. imprecise characterization), or for understanding the broader equilibrium landscape of systems of interest (e.g.
serpentinizing systems in general). Eleanor is a powerful open-source modeling framework based on EQ3/6 which fills
this gap, providing the process and data orchestration features necessary to facilitate large-scale aqueous speciation
modeling. Eleanor includes a standalone executable which accepts a problem specification in YAML, TOML or JSON format,
samples fully-defined systems for speciation via the EQ3/6-based "kernel", validates the results, and stores the data
in a Postgres. Eleanor’s modular design allows the user to swap the EQ3/6-based kernel with one of their own.

## Dependencies

> **NOTE**: We support both Linux and MacOS systems. You might have some luck using the Linux Subsystem for Windows, but
> we don't pretend to support it.

Eleanor requires `python>=3.11` an two external runtime dependencies:

1. A slightly modified version of EQ3/6 found at [39alpha/eq3_6](https://github.com/39alpha/eq3_6). Future versions will
likely add other kernels based on other speciation tools, but EQ3/6 is what we have now.
2. A [PostgreSQL](https://www.postgresql.org/) server. This is honestly the most odious dependency to install, but the PostgreSQL docs are pretty good.

There are two dev dependencies required for installation:

1. [`gfortran`](https://fortran-lang.org/learn/os_setup/install_gfortran/) - you should be able to install `gfortran`
with your system's package manager (e.g. homebrew)
2. [`meson`](https://mesonbuild.com/) - I recommend installing this via `uv`. See [Install](#install) below.

## Install

I highly recommend using [`uv`](https://docs.astral.sh/uv/) to install eleanor:

```bash
uv tool install meson # If you haven't installed meson already
```

```bash
uv tool install git+https://github.com/39alpha/eleanor
```
