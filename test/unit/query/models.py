from dataclasses import dataclass


@dataclass
class Mineral:
    name: str
    amount: float


@dataclass
class Chemistry:
    ph: float
    pe: float


@dataclass
class Point:
    index: int
    chemistry: Chemistry | None
    minerals: list[Mineral]


@dataclass
class Sample:
    point: Point
    points: list[Point]
    point_map: dict[str, Point]


@dataclass
class SimpleSample:
    points: list[Point]


def make_sample() -> Sample:
    return Sample(
        point=Point(index=0, chemistry=Chemistry(ph=6.8, pe=2.7), minerals=[Mineral(name="calcite", amount=0.2)]),
        points=[
            Point(index=1, chemistry=Chemistry(ph=7.1, pe=4.2), minerals=[Mineral(name="calcite", amount=0.3)]),
            Point(index=2, chemistry=None, minerals=[Mineral(name="quartz", amount=0.1)]),
        ],
        point_map={
            "a": Point(index=1, chemistry=Chemistry(ph=7.0, pe=3.1), minerals=[]),
            "b": Point(index=1, chemistry=Chemistry(ph=7.2, pe=3.3), minerals=[]),
            "c": Point(index=3, chemistry=Chemistry(ph=7.4, pe=3.6), minerals=[]),
        },
    )
