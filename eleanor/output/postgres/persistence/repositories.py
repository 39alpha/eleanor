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


def write_point(
    config: DatabaseConfig,
    order_id: int,
    point: core_vs.Point,
    verbose: bool = False,
) -> models.VSPointModel:
    model = mappers.to_vs_point_model(point, order_id=order_id)
    with PostgresSession(config, verbose=verbose) as session:
        session.add(model)
        session.commit()
        session.refresh(model)
        mappers.copy_vs_model_ids_back(point, model)
    return model


def load_point(config: DatabaseConfig, point_id: int, verbose: bool = False) -> core_vs.Point | None:
    with PostgresSession(config, verbose=verbose) as session:
        model = session.get(models.VSPointModel, point_id)
        if model is None:
            return None
        return mappers.from_vs_point_model(model)


def get_scratch_entry(
    config: DatabaseConfig,
    variable_space_id: int,
    verbose: bool = False,
) -> ScratchEntry | None:
    with PostgresSession(config, verbose=verbose) as session:
        model = session.get(models.VSPointModel, variable_space_id)
        if model is None or model.scratch is None or model.id is None:
            return None
        return ScratchEntry(
            variable_space_id=model.id,
            exit_code=model.exit_code,
            zip=model.scratch.zip,
        )
