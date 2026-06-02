> **AGU25 Attendees:** We're not naming names (**cough** Doug **cough**), but someone copied the wrong example order
> into their poster. If you would like to see the correct version, you can find it here:
>
> [$H_2$ Generation from Olvine, Ortho and Clino](https://github.com/39alpha/eleanor/blob/main/demo/01-h2-generation.yaml)

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

Eleanor requires `python>=3.14` an two external runtime dependencies:

1. A slightly modified version of EQ3/6 found at [39alpha/eq3_6](https://github.com/39alpha/eq3_6). Future versions will
likely add other kernels based on other speciation tools, but EQ3/6 is what we have now.
2. A [PostgreSQL](https://www.postgresql.org/) server. This is honestly the most odious dependency to install, but the
PostgreSQL docs are pretty good.

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

## CLI overview

Top-level commands:

- `eleanor run` — run a simulation workload from an order file.
- `eleanor doctor` — print install and plugin diagnostics.
- `eleanor gen config|order` — emit starter config/order templates.
- `eleanor postgres schema|scratch|bulkload` — postgres-specific helper commands.

### `eleanor run`

```bash
eleanor run [OPTIONS] ORDER SIMULATION_SIZE
```

Common options:

- `-c, --config` / `-d, --database`: select config and optionally override the postgres database name.
- `-n, --num-procs`: worker count for the selected executor backend.
- `--parallel BACKEND`: override `parallel.backend` from config (built-ins: `serial`, `multiprocessing`; plugins may add more, e.g. `mpi`).
- `--chunks-per-worker`: override `parallel.chunks_per_worker`.
- `--batch-size`: navigator batch size passed into `navigate(...)`.
- `--max-nav-attempts`: maximum attempts per navigation point before giving up.
- `--order-id`: resume/extend an existing order id.
- `--tag`: override the order tag loaded from the order file.
- `--null-sink`: bypass configured output and discard writes via `NullSink`.
- `--bulk-load` / `--no-bulk-load`: enable/disable postgres bulk-load optimization for this run.
- `-p, --progress`: show progress bars (disabled automatically by `--verbose`).
- `-v, --verbose`: verbose output.
- `-s, --scratch`: persist scratch artifacts for all simulations regardless of error status.

### Built-in output sinks

Built-in output sink types are:

- `postgres`
- `csv`
- `memory`
- `null`

Select a sink in your config under `output.type`, with sink-specific settings in `output.args`.
For one-off dry runs, `--null-sink` on `eleanor run` overrides config output without editing files.

### Resume / extend orders with `--order-id`

Use `--order-id` to append new variable-space/equilibrium results to an existing order row:

```bash
eleanor run --order-id 42 -c config.yaml -d eleanor_db order.yaml 50000
```

Behavior:

- If order `42` already exists, Eleanor extends that order.
- If `42` does not exist, Eleanor creates a new order and continues normally.
- The `eleanor_version` must match when extending an existing order. If your order file declares a different version, the run is rejected.
- If the order file leaves `eleanor_version` unset, Eleanor reuses the stored version from the existing row.

### Parallelism, batch size, and Postgres subtransaction pressure

The postgres sink uses one outer transaction per batch plus one savepoint per variable-space point.
With multiprocessing, each worker has its own connection and can hold up to `batch_size` in-flight savepoints.
Operationally, subtransaction pressure scales roughly with:

`batch_size × num_workers`

At sufficiently high values this can trigger Postgres `SubtransSLRULock` contention.
If you see this, reduce `--batch-size`, reduce worker count (`-n` / backend configuration), or both.

### Bulk-load controls

For postgres outputs, bulk-load mode drops secondary indexes/constraints during ingestion and recreates them at finalize:

```bash
eleanor run --bulk-load -c config.yaml -d eleanor_db order.yaml 200000
```

You can also control this window explicitly:

```bash
eleanor postgres bulkload drop -y -c config.yaml -d eleanor_db
eleanor postgres bulkload recreate -c config.yaml -d eleanor_db
```

If a bulk-load run is interrupted before finalize, use `eleanor postgres bulkload recreate` to restore constraints/indexes.

## Shell Completion

### Bash

```bash
eval "$(_ELEANOR_COMPLETE=bash_source eleanor)"
```

### Zsh

```bash
eval "$(_ELEANOR_COMPLETE=zsh_source eleanor)"
```

### Fish

```bash
_ELEANOR_COMPLETE=fish_source eleanor | source
```

## MPI backend (optional)

MPI support is provided by the separately-distributed `eleanor_mpi` plugin package. Installing it registers the `mpi` backend with Eleanor's executor registry; no configuration changes are required.

```bash
pip install eleanor_mpi
```

See the `eleanor_mpi` README for launcher details, worker-count semantics, and progress-reporting caveats.
