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

Eleanor requires `python>=3.14` and two external runtime dependencies:

1. A slightly modified version of EQ3/6 found at [39alpha/eq3_6](https://github.com/39alpha/eq3_6). Future versions will
likely add other kernels based on other speciation tools, but EQ3/6 is what we have now.

A [PostgreSQL](https://www.postgresql.org/) server is required only if you use the `postgres` output sink (recommended
for large-scale runs).

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
- `eleanor postgres schema|scratch|bulkload|migrate` — postgres-specific helper commands.

### `eleanor run`

```bash
eleanor run [OPTIONS] ORDER SIMULATION_SIZE
```

Common options:

- `-c, --config` / `-d, --database`: select config and optionally override the postgres database name.
- `-n, --num-workers`: worker count for the selected executor backend.
- `--executor KIND`: override the executor kind from config (built-ins: `serial`, `multiprocessing`; plugins may add
  more, e.g. `mpi`).
- `--chunks-per-worker`: override `executor.chunks_per_worker` from config.
- `--batch-size`: navigator batch size passed into `navigate(...)`.
- `--max-nav-attempts`: maximum attempts per navigation point before giving up.
- `--order-id`: resume/extend an existing run, as `SINK=ID`. Repeat once per output sink; the bare `ID` form is accepted
  when only one sink is configured. The id format is the output sink's own (an integer for `postgres`, a UUID for `csv`).
- `--tag`: override the order tag loaded from the order file.
- `--null-sink`: bypass every configured output sink and discard writes via `NullSink`.
- `--bulk-load` / `--no-bulk-load`: enable/disable postgres bulk-load optimization for this run, on every configured
  postgres sink.
- `-p, --progress`: show progress bars (disabled automatically by `--verbose`).
- `-v, --verbose`: verbose output.
- `-s, --scratch`: persist scratch artifacts for all simulations regardless of error status.

### Built-in output sinks

Built-in output sink types are:

- `postgres`
- `csv`
- `memory`
- `null`

Select a sink in your config under `output.kind`, with sink-specific settings as flat keys alongside `kind`.
For one-off dry runs, `--null-sink` on `eleanor run` overrides config output without editing files.

#### Writing to several sinks at once

`output` also accepts a **list**, in which case the run drives every sink in it.
The kernel still runs once per point — the compute graph is fanned out to the
sinks inside the worker — so N sinks cost far less than N runs:

```yaml
output:
  - kind: postgres
    database: {host: localhost, database: eleanor_db, username: alice}
  - kind: csv
    name: export
    filename: summary.csv
    id_columns: [order_id, point_id]
    query:
      row_scope: vs_points[*]
      columns:
        - {path: vs_point.exit_code, name: exit_code}
```

Each sink is addressed by `name`, which defaults to its `kind`. Two sinks of
the same kind — two CSVs writing different projections to different files — are
fine as long as you name them, and duplicate names are rejected. The name is
what `--order-id` keys on, what labels the sink's progress bar, and what
`Eleanor.run` keys its returned ids by.

Every sink keeps its own id space, its own progress bar, and its own resume
token. Three consequences worth knowing:

- **There is no cross-sink atomicity.** An interrupt, or any sink failing, can
  leave one sink holding a chunk the others do not. A failure in any sink
  aborts the whole run rather than continuing with the survivors.
- **Rows from different sinks cannot be joined.** The `csv` sink's `point_id`
  counter and the `postgres` sink's `vs_point` sequence are unrelated.
- **Cost scales with the sink count.** Each serial sink adds a writer thread
  and a bounded queue, and the Postgres subtransaction pressure described below
  applies per postgres sink.

#### Identity columns on the `csv` sink

The `csv` sink projects each result through an EQL `query`, but identity is the
sink's own, not part of the object graph the query walks — so ids are requested
in settings rather than as query paths. `id_columns` accepts `order_id` (the
run's UUID) and `point_id` (a per-run VS-point counter), and prepends them to
the header in the order given:

```yaml
output:
  kind: csv
  filename: rows.csv
  id_columns: [order_id, point_id]
  query:
    row_scope: vs_points[*]
    columns:
      - order.name
      - vs_point.temperature
      - vs_point.exit_code
# header: order_id,point_id,name,temperature,exit_code
```

Omit `id_columns` for a file with no identity columns. Every row of one VS point
shares its `point_id`, so a query emitting several rows per point repeats the
value — `point_id` identifies the point, not the row.

### Resume / extend a run with `--order-id`

Use `--order-id` to append new variable-space/equilibrium results to an existing run:

```bash
# postgres: the orders.id of the run to extend
eleanor run --order-id 42 -c config.yaml -d eleanor_db order.yaml 50000

# csv: the UUID the earlier run printed / recorded in its sidecar
eleanor run --order-id 3f2b8c9e-... -c config.yaml order.yaml 50000

# several sinks: one token each, keyed by sink name
eleanor run --order-id postgres=42 --order-id export=3f2b8c9e-... \
  -c config.yaml order.yaml 50000
```

Behavior:

- Ids belong to the output sink, not to the order, so an order file must not declare one. Which ids are valid depends on the configured sink: `postgres` uses its `orders.id` sequence, `csv` uses UUIDs recorded in its `_schema.yaml` sidecar.
- With several sinks configured, **every** sink must be given a token. Resuming some while silently starting the others fresh would split one run's output across two ids with nothing recording that they differ. A sink reporting `supports_resume() == False` — one with nothing to resume, such as a live-plotting sink — is exempt, and aiming a token at one is an error rather than a no-op.
- A bare `--order-id ID` is only accepted when exactly one sink is configured; with several, the id spaces differ and there is nothing to infer from.
- If the id names a run the sink holds, Eleanor extends it.
- If the id is malformed for that sink, or names no run it holds, the run is **rejected**. Resuming is an explicit request, so Eleanor will not quietly start a new run instead.
- The `eleanor_version` must match when extending an existing run. If your order file declares a different version, the run is rejected.
- Omit `--order-id` to start a new run; the sink allocates the id and `eleanor run -v` prints it.

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
