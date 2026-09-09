# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [v0.21.0] - 2026-09-09

### Added

- **A run can drive several output sinks at once.** `output` accepts a list of sink blocks as well
  as a single one, each with an optional `name` defaulting to its `kind`; every sink receives every
  computed point.
- **`--timing` flag on `eleanor run`** prints a wall-clock attribution of the dispatch loop to
  stderr when the run finishes.
- **`id_columns` on the `csv` sink** emits the sink's own identity columns -- `order_id` and/or
  `point_id` -- ahead of the query's columns. Identity is not part of the object graph EQL projects,
  so it is declared in settings rather than as a query path.

### Changed

- **`Eleanor.run` returns `dict[str, object]`** -- each sink's allocated id, keyed by sink name.
- **`Eleanor(output_sink=...)` and `Eleanor.run(output_sink=...)` accept a mapping of name to
  sink** as well as a single sink.
- **`Config.output` is a `list[OutputSinkConfig]`**, empty rather than `None` when no sink is
  configured.
- **`--order-id` is repeatable and takes `SINK=ID`** when more than one is given.
- **Output sinks own the run id, and it need not be an integer.** `begin_run` takes a keyword-only
  `requested_id: str | None` and `Eleanor.run` a matching `resume_id: str | None`, carrying the raw
  `--order-id` token for the sink to interpret in its own id space -- an integer for `postgres`,
  `memory` and `null`, a UUID for `csv`. One contract now applies to every sink: no token allocates
  a fresh id, a token naming a run the sink holds resumes it, and a malformed or unknown token
  raises `EleanorError`. Previously the PostgreSQL sink silently inserted a *new* order when the
  requested id matched no row.
- **`AbstractOutputSink` is generic in the id type it issues**, as `AbstractOutputSink[IdT]`.
- **`CsvSink` issues UUIDs rather than `max(seen) + 1` integers**, so two runs appending to one file
  cannot collide. Its `_schema.yaml` sidecar keys `vs_points_seen` and `order_versions` by the
  string form of the id, and binary-asset filenames embed the UUID.
- **`AbstractOutputSink.write_batch` is replaced by `prepare_batch` + `commit_batch`.**
  `prepare_batch` runs in a worker process, with the full compute graph available, and reduces it
  to a compact payload; `commit_batch` durably persists that payload, in the worker when
  `supports_worker_commit()` is `True` and in the parent otherwise. Every sink must now be picklable
  *and* importable by name. See `docs/plugins.qmd` for the migration shape.
- **`supports_worker_writes()` is renamed `supports_worker_commit()`**, and the
  `support_worker_writes` setting on the null and memory sinks becomes `support_worker_commit`.
- **Sinks that commit in the parent do so on a dedicated writer thread**, so writing no longer
  blocks the dispatch loop.
- **The dispatch loop keeps a bounded window of chunks in flight** rather than draining each
  navigator batch to empty before generating the next. Point generation, compute and output overlap
  continuously, so a small `--batch-size` no longer idles the worker pool. Chunk size is still
  derived from `batch_size` and `chunks_per_worker` keeps its meaning, so existing configurations
  are unaffected.

### Removed

- **`Order.id`.** An order describes what to compute; the identity of a *run* of it belongs to
  whichever sink persists that run. Resumption is now `--order-id` / `resume_id` (above). An `id`
  key in an order file is **rejected** rather than ignored, since silently dropping it would change
  an existing file's meaning. No migration: `orders.id` was always the authority.
- **`order.id` from the canonical EQL `run_metadata` preset** and from spec §10.3. `order.id` no
  longer compiles and `{splat: order}` no longer includes it. This is a breaking preset change; use
  `id_columns` instead.
- **`vs_point.@index` support in the `csv` sink**, now **rejected** at construction with a pointer
  to `id_columns: [point_id]`. The sink evaluates one VS point at a time against a one-element
  `vs_points`, so the path could only ever yield `0`.
- **`variable_space.Point.order_id`**, written by every sink and read nowhere. The database column
  and its foreign key are unchanged, so no migration is needed. EQL queries selecting
  `vs_point.order_id`, and `{splat: vs}` projections that included it, must be updated.
- **The `order_id` keyword argument to `AbstractNavigator.navigate`** and the `order_id` parameter
  of `PointBuilder.generate_vs`. Nothing downstream of point generation needs the id.
- **`Eq3Settings.id` and `Eq6Settings.id`.** Both were always `None`, read nowhere, and unreachable
  from `Eq36Settings.from_dict`.

### Fixed

- **Special basis switches are now reflected in the aqueous basis species block of the EQ3 input.**
  A `kernel.basis_map` entry reached the `* Special basis switches` section, but
  `* Aqueous basis species` still named the element's original strict basis species.
- **A failing point no longer discards its chunk.** A query-evaluation error in `CsvSink` used to
  propagate out, losing the rows of every healthy point in the batch and skipping the sidecar
  flush. It is now recorded on that point's outcome.
- **`OutputParser3` tolerates EQ3 output files that omit the hypothetical solid solutions and
  fugacities sections.** The two are optional but always appear together, hypothetical solid
  solutions first, so the parser probes for the leading section and skips both when it is absent
  rather than raising a `PARSER_ERROR`.

## [v0.20.0] - 2026-07-13

### Added

- **eleanor.kernel.eq36.Eq36Settings.filter** allows the user to provide an EQL query with a limited
  set of conditions for filtering out generated `equilibrium_space.Point`s, e.g. with some specific
  aqueous species present below some limit.
- **`--[no-]indexes` / `--[no-]fks` / `--[no-]checks` flags** on `eleanor postgres bulkload
  drop/recreate` give granular control over which object classes are dropped and recreated around a
  bulk-load window (all on by default). `recreate` is now idempotent per class — it skips CHECK/FK
  constraints that are already present — so an asymmetric drop/recreate is safe rather than an error.

### Changed

- **Widened the `equilibrium_*` identity primary keys from `INTEGER` to `BIGINT`.** The
  per-equilibrium-point tables accumulate one row per species/solid/gas/reactant per point, so
  their `int4` identity range was the first thing to overflow on large runs. The foreign-key columns
  that store these ids (`equilibrium_space_id`, `equilibrium_solid_solution_id`) are widened to match.
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
