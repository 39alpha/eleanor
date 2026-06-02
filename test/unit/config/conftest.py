import json
from pathlib import Path

import pytest
import tomli_w
import yaml


class Helpers:
    @staticmethod
    def write_config(data: dict[str, object], tmp_path: Path, fmt: str) -> Path:
        path = tmp_path / f"config.{fmt}"

        match fmt:
            case "yaml" | "yml":
                with open(path, "w") as f:
                    yaml.dump(data, f)
            case "toml":
                with open(path, "wb") as f:
                    tomli_w.dump(data, f)
            case "json":
                with open(path, "w") as f:
                    json.dump(data, f)
            case _:
                pytest.fail("unexpected config format")

        return path


@pytest.fixture
def helpers() -> type[Helpers]:
    return Helpers
