from dataclasses import dataclass

import eleanor.variable_space as core_vs

from ....connection import DatabaseConfig
from ....order import Order
from . import mappers, models
from .registry import postgres_registry
from .session import PostgresSession


@dataclass(frozen=True, slots=True)
class ScratchEntry(object):
    variable_space_id: int
    exit_code: int
    zip: bytes


def setup_schema(config: DatabaseConfig, verbose: bool = False) -> None:
    with PostgresSession(config, verbose=verbose) as session:
        postgres_registry.metadata.create_all(session.engine)


def get_order(config: DatabaseConfig, order_id: int, verbose: bool = False) -> models.OrderModel | None:
    with PostgresSession(config, verbose=verbose) as session:
        return session.get(models.OrderModel, order_id)


def insert_order(config: DatabaseConfig, order: Order, verbose: bool = False) -> models.OrderModel:
    model = mappers.to_order_model(order)
    with PostgresSession(config, verbose=verbose) as session:
        session.add(model)
        session.commit()
        session.refresh(model)
    return model


def insert_point(
    session: PostgresSession,
    order_id: int,
    point: core_vs.Point,
) -> models.VSPointModel:
    """Insert ``point`` through an already-open session and return the refreshed model.

    The session is supplied by the caller so a whole batch can share a single
    engine/session pair; per-point error handling (rolling back on failure,
    collecting :class:`~eleanor.output.interface.WriteOutcome` values, etc.)
    stays at the sink layer where the batch loop lives.
    """
    model = mappers.to_vs_point_model(point, order_id=order_id)
    session.add(model)
    session.commit()
    session.refresh(model)
    return model


def get_scratch_entry(
    config: DatabaseConfig,
    variable_space_id: int,
    verbose: bool = False,
) -> ScratchEntry | None:
    """Fetch a persisted scratch payload for a variable-space point.

    Returns ``None`` when the variable-space point does not exist. Raises
    :class:`LookupError` with ``'scratch'`` when the point exists but has no
    scratch row, so CLI callers can distinguish the two cases and preserve
    the historical error messages.
    """
    with PostgresSession(config, verbose=verbose) as session:
        model = session.get(models.VSPointModel, variable_space_id)
        if model is None or model.id is None:
            return None
        if model.scratch is None:
            raise LookupError("scratch")
        return ScratchEntry(
            variable_space_id=model.id,
            exit_code=model.exit_code,
            zip=model.scratch.zip,
        )
