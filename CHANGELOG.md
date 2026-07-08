# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **eleanor.kernel.eq36.Eq36Settings.filter** allows the user to provide an EQL query with a limited
  set of conditions for filtering out generated `equilibrium_space.Point`s, e.g. with some specific
  aqueous species present below some limit.
- **`--[no-]indexes` / `--[no-]fks` / `--[no-]checks` flags** on `eleanor postgres bulkload
  drop/recreate` give granular control over which object classes are dropped and recreated around a
  bulk-load window (all on by default). `recreate` is now idempotent per class — it skips CHECK/FK
  constraints that are already present — so an asymmetric drop/recreate is safe rather than an error.

### Changed

- **Curated the PostgreSQL indexes.** The existing set of indexes didn't achieve the query
  performance we hoped for out of the box and ultimately just bloated the on-disc storage footprint.
  We spent some time profiling known, real-world queries and tried to balance the performance
  against storage size. These will probably be further refined in the future.
- **`eleanor postgres bulkload recreate` now packs rebuilt B-tree indexes at `fillfactor = 100`.**
  A recreate is a one-shot bulk build over write-once data, so the B-tree default of 90 -- which
  reserves ~10% of each page for in-place inserts that never happen -- only wasted disk. GIN/BRIN
  indexes are unaffected.
- **Renamed the bulk-load helpers** `drop_indexes` / `recreate_indexes` to `drop_bulk_load_objects` /
  `recreate_bulk_load_objects` (in `eleanor.output.postgres.persistence.schema` and its
  `repositories` wrappers). The new names reflect that they act on secondary indexes *and* FK / CHECK
  constraints. Update any code importing the old names.

### Fixed

- **Write error messages** from the `Runner` to the `PostgresSink` output. The `Runner` was
  overwriting the `Point.exception` property as `None` and the `PostgresSink` was drawing
  the error message from there. Instead the error message now comes from the `ComputeResult.error`
  property.

## [v0.19.0] - 2026-06-12

### Added

- **CHANGELOG.md** - this changelog
- **Pull request template** - a template for pull requests
- **Issue templates** - bug report and feature request templates
- **CONTRIBUTING.md** - guidelines for contributing to this project
- **CODE_OF_CONDUCT.md** - the Contributor Covenant Code of Conduct
- **Eleanor Query Language (EQL)** - a typed, consumer-agnostic query language for filtering and
  projecting simulation results; usable by any output sink (Postgres, CSV, memory, etc.) or
  navigator feedback logic.
- **Database migration system** - `eleanor postgres migrate` applies versioned schema migrations;
  migrations are applied automatically on each run.
- **CSV, Memory, and Null output sinks** - `csv`, `memory`, and `null` sink types are now built
  in alongside the existing `postgres` sink.
- **`eleanor doctor`** - new subcommand that prints install and plugin diagnostics.
- **`eleanor gen config|order`** - new subcommand that emits starter config and order templates in
  YAML, TOML, or JSON.
- **`eleanor postgres` subcommands** - `bulkload drop/recreate`, `schema verify/scratch`, and
  `migrate` are now grouped under `eleanor postgres`.
- **`--null-sink` flag** - bypasses configured output and discards all writes without editing the
  config file.
- **`--max-nav-attempts` flag** - controls how many times a navigator will retry a point before
  giving up.
- **`--(no-)bulk-load` flag** - enables/disables Postgres bulk-load mode (drops secondary
  indexes/constraints during ingestion and recreates them at finalize) for a single run.
- **`ELEANOR_EQ36_DATA1_DIR` environment variable** - allows the EQ3/6 data directory to be set
  without a config file.
- **Multiple tags per order** - an order can now carry more than one tag; tags are stored as a
  JSON array.
- **`--order-id` flag** - resumes or extends an existing order row in the database.
- **Navigator-owned batching** - navigators now control their own batch sizing; the
  `--max-nav-attempts` flag wires into the retry logic.
- **`LinearConstraint`** - a new built-in constraint type.
- **Simulation and output progress bars** - separate tqdm bars track kernel execution and output
  writes independently.
- **Plugin versioning** - plugins declare a version; Eleanor validates compatibility at load time.
- **Entry-point plugin registration** - executors, kernels, navigators, output sinks, and CLI
  commands are registered via `pyproject.toml` entry points rather than hard-coded imports.
- **`Kernel.get_molar_mass` and `Kernel.get_atomic_weight`** - new kernel interface methods
  allowing plugins to expose molar masses and atomic weights.
- **`Order.volume`** property and **`water_mass`** order field.
- **Graceful SIGINT/SIGTERM shutdown** - Eleanor flushes in-flight results and exits cleanly on
  interrupt.
- **`CombinedReactant`** - new reactant type with optional fraction-proportional rate support,
  replacing `GlassReactants`.
- **`min_log_activity` / `min_log_molality` / `write_unformed` settings** for the Postgres sink.
- **`error` column** in the `variable_space` table - stores exception information for failed
  simulation points.
- **Database indices** - a comprehensive set of indices added to the Postgres schema to speed up
  common queries.
- **`EleanorWarning`** - base class for non-fatal warnings raised during a run.
- Backtraces are now always printed in `eleanor run` when an error occurs.
- Reactant fractions can now be `ValueParameter` instances.
- Reactant fraction sums that are within floating-point tolerance of 1.0 are now accepted.
- `@config_options` decorator is now parameterizable with `required`.

### Changed

- **All `*Exception` classes renamed to `*Error`** to align with Python naming conventions (e.g.
  `EleanorException` → `EleanorError`, `Eq36Exception` → `Eq36Error`).
- **Postgres sink reimplemented with psycopg3** - replaces the previous psycopg2-based
  implementation; one outer transaction per batch, one savepoint per variable-space point.
- **`Sailor` renamed to `Runner`**; **`Boatswain` renamed to `PointBuilder`**.
- **Eleanor is now an optional context manager** - resources (executor, progress manager, output
  sink) are reused across multiple `run` calls inside a `with` block; single-shot usage works
  without one.
- **CLI transitioned to Click** - all commands and flags now use Click; shell completion is
  available via `_ELEANOR_COMPLETE`.
- **Plugin system refactored to use Python entry points** - all built-in and third-party plugins
  register via `project.entry-points` in `pyproject.toml`.
- `ConstraintConfig`, `NavigatorConfig`, and `OutputConfig` each moved to dedicated modules within
  their respective subsystems.
- `Config` refactored; per-subsystem config classes are now loaded independently.
- **Reactant dataclasses are now replaceable** via `dataclasses.replace`.
- **All `Eleanor.__init__` arguments are now keyword-only.**
- `data1_dir` now accepts `str | Path` (previously required `str`).
- Obscure equilibrium-space scalar properties moved from top-level columns into a
  `custom_properties` JSONB column.
- Transitioned to `np.float64` throughout the kernel layer.
- scipy imports are now deferred to improve startup time.
- **Executor lifecycle is now caller-owned** - Eleanor no longer manages executor teardown when an
  executor is passed in at construction time.
- Stoichiometric ionic asymmetry is now stored in place of `log_activity` / `log_molality` values.
- Switched to absolute imports throughout the codebase.
- `TypedDict`s at interface boundaries replaced with typed `**kwargs` (`Unpack`).
- `load_executor`, `load_navigator`, and `load_output_sink` interfaces redesigned for consistency.
- `Eleanor.run` now accepts kernel arguments directly rather than via a wrapper.
- Multiprocessing executor replaced busy-polling loop with a proper queue-draining implementation.
- `Order` and reactant construction made more flexible; programmatic construction requires fewer
  arguments.
- `Parameter.name` property retired; names are now managed at the `VariableSpace` level.

### Removed

- **Suborder feature** - suborders are no longer supported; use separate orders instead.
- **Huffer** - removed entirely.
- **`GlassReactantEmbedder`** - superseded by `CombinedReactant`.
- **Order Transformers feature** - removed entirely.
- **Success-sampling support** - removed.
- **`Parameter.type`** property.
- **`parallel` kwarg** from `Eleanor.run`.
- **Per-run executor support** - the executor is now session-scoped; pass it at construction time.
- **IDs from core dataclasses** - `id` fields moved out of `Order`, `VariableSpace`, and
  `EquilibriumSpace` dataclasses and into the output layer.
- mypy, pylsp-mypy, and maccabe removed as dev dependencies; replaced by basedpyright.

### Fixed

- Always-true condition in kernel model-type check silently accepting invalid states.
- Infinite recursion in certain kernel code paths.
- Incorrect exit code detected in runner when kernel returned a soft-exit code.
