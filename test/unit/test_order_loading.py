"""Loading orders from paths and streams, with the format chosen explicitly, by extension, or by content."""

import yaml
import tomllib
import io
import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from eleanor.cli.gen import FORMATS, _load_template
from eleanor.exceptions import EleanorError
from eleanor.order import Order, OrderFormat, detect_format, load_order

BOM = "﻿"


def template(fmt: str) -> str:
    content = _load_template("order", fmt)
    assert content is not None
    return content


def write(path: Path, content: str) -> Path:
    _ = path.write_text(content, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("fname", "expected"),
    [
        ("o.yaml", "yaml"),
        ("o.yml", "yaml"),
        ("o.toml", "toml"),
        ("o.json", "json"),
        ("O.YAML", "yaml"),
        ("O.Toml", "toml"),
        (Path("dir/o.json"), "json"),
    ],
)
def test_detect_format_prefers_a_known_extension(fname: str | Path, expected: OrderFormat) -> None:
    assert detect_format('{"name": "o"}\n[kernel]\n', fname=fname) == expected


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        pytest.param('{"name": "o"}', "json", id="json-object"),
        pytest.param("  {\n", "json", id="json-indented"),
        pytest.param("[kernel]\nkind = 'eq36'\n", "toml", id="toml-table"),
        pytest.param("[[reactants]]\n", "toml", id="toml-array-of-tables"),
        pytest.param('name = "o"\n', "toml", id="toml-key-value"),
        pytest.param('"name" = "o"\n', "toml", id="toml-quoted-key"),
        pytest.param("kernel.kind = 'eq36'\n", "toml", id="toml-dotted-key"),
        pytest.param("name: o\n", "yaml", id="yaml-mapping"),
        pytest.param("---\nname: o\n", "yaml", id="yaml-document-start"),
        pytest.param("- a\n", "yaml", id="yaml-sequence"),
        pytest.param("# comment\n\n   \nname = 'o'\n", "toml", id="skips-comments-and-blanks"),
        pytest.param("", "yaml", id="empty"),
        pytest.param("# only a comment\n", "yaml", id="only-comments"),
    ],
)
def test_detect_format_sniffs_content_without_a_known_extension(content: str, expected: OrderFormat) -> None:
    assert detect_format(content) == expected
    assert detect_format(content, fname="order.txt") == expected
    assert detect_format(content, fname="/dev/fd/63") == expected
    assert detect_format(content, fname="<stdin>") == expected


@pytest.mark.parametrize("fmt", FORMATS)
def test_from_file_loads_each_format_from_a_path(tmp_path: Path, fmt: str) -> None:
    path = write(tmp_path / f"order.{fmt}", template(fmt))

    assert Order.from_file(path).name == "My Order"
    assert Order.from_file(str(path)).name == "My Order"


@pytest.mark.parametrize("fmt", FORMATS)
def test_from_file_detects_the_format_of_a_path_without_an_extension(tmp_path: Path, fmt: str) -> None:
    path = write(tmp_path / "order", template(fmt))

    assert Order.from_file(path).name == "My Order"


@pytest.mark.parametrize("fmt", FORMATS)
def test_from_file_loads_each_format_from_a_text_stream(fmt: str) -> None:
    assert Order.from_file(io.StringIO(template(fmt))).name == "My Order"


@pytest.mark.parametrize("fmt", FORMATS)
def test_from_file_loads_each_format_from_a_bytes_stream(fmt: str) -> None:
    assert Order.from_file(io.BytesIO(template(fmt).encode())).name == "My Order"


@pytest.mark.parametrize("fmt", FORMATS)
def test_from_file_strips_a_byte_order_mark(tmp_path: Path, fmt: str) -> None:
    content = BOM + template(fmt)
    path = write(tmp_path / f"order.{fmt}", content)

    assert Order.from_file(path).name == "My Order"
    assert Order.from_file(io.StringIO(content)).name == "My Order"
    assert Order.from_file(io.BytesIO(content.encode())).name == "My Order"


def test_from_file_reads_a_stream_named_by_a_file_descriptor() -> None:
    read_fd, write_fd = os.pipe()
    _ = os.write(write_fd, template("toml").encode())
    os.close(write_fd)

    with os.fdopen(read_fd) as stream:
        assert isinstance(stream.name, int)
        assert Order.from_file(stream).name == "My Order"


def test_from_file_does_not_close_a_caller_stream() -> None:
    stream = io.StringIO(template("yaml"))

    _ = Order.from_file(stream)

    assert not stream.closed


def test_from_file_explicit_format_overrides_extension_and_content(tmp_path: Path, mocker: MockerFixture) -> None:
    path = write(tmp_path / "order.yaml", template("json"))
    from_jsons = mocker.spy(Order, "from_jsons")

    order = Order.from_file(path, file_format="json")

    assert order.name == "My Order"
    from_jsons.assert_called_once()


def test_from_file_extension_overrides_content(tmp_path: Path, mocker: MockerFixture) -> None:
    path = write(tmp_path / "order.yaml", template("json"))
    from_yamls = mocker.spy(Order, "from_yamls")
    from_jsons = mocker.spy(Order, "from_jsons")

    _ = Order.from_file(path)

    from_yamls.assert_called_once()
    from_jsons.assert_not_called()


def test_from_file_uses_the_extension_of_a_named_stream(tmp_path: Path, mocker: MockerFixture) -> None:
    path = write(tmp_path / "order.yaml", template("json"))
    from_yamls = mocker.spy(Order, "from_yamls")

    with path.open("rb") as stream:
        _ = Order.from_file(stream)

    from_yamls.assert_called_once()


def test_from_file_fname_overrides_the_stream_name(mocker: MockerFixture) -> None:
    from_tomls = mocker.spy(Order, "from_tomls")
    stream = io.StringIO(template("toml"))
    stream.name = "order.yaml"

    _ = Order.from_file(stream, fname="order.toml")

    from_tomls.assert_called_once()


@pytest.mark.parametrize(
    ("fmt", "content", "exception_type"),
    [
        ("yaml", "name: [o\n", yaml.parser.ParserError),
        ("toml", "[kernel]\nkind = \n", tomllib.TOMLDecodeError),
        ("json", '{"name": }', json.decoder.JSONDecodeError),
    ],
)
def test_from_file_parse_errors_raise_library_errors(
    tmp_path: Path,
    fmt: str,
    content: str,
    exception_type: type[Exception],
) -> None:
    path = write(tmp_path / f"order.{fmt}", content)

    with pytest.raises(exception_type):
        _ = Order.from_file(path)


@pytest.mark.parametrize("name", ["<stdin>", None], ids=["named", "unnamed"])
def test_from_file_stream_parse_errors_raise_library_errors(name: str | None) -> None:
    stream = io.StringIO("[kernel]\nkind = \n")
    if name is not None:
        stream.name = name

    with pytest.raises(tomllib.TOMLDecodeError):
        _ = Order.from_file(stream)


def test_from_file_undecodable_bytes_raise_a_decode_error() -> None:
    with pytest.raises(UnicodeDecodeError):
        _ = Order.from_file(io.BytesIO(b"name: \xff\xfe\n"))


def test_from_file_reports_validation_errors_unchanged(tmp_path: Path) -> None:
    path = write(tmp_path / "order.yaml", "name: o\n")

    with pytest.raises(EleanorError, match="creator must be a string") as excinfo:
        _ = Order.from_file(path)

    assert "failed to parse" not in str(excinfo.value)


@pytest.mark.parametrize(
    ("loader", "content"),
    [
        pytest.param(Order.from_yamls, "- a\n", id="yaml-sequence"),
        pytest.param(Order.from_yamls, "just a string\n", id="yaml-scalar"),
        pytest.param(Order.from_yamls, "null\n", id="yaml-null"),
        pytest.param(Order.from_jsons, "[1]", id="json-array"),
        pytest.param(Order.from_jsons, "null", id="json-null"),
        pytest.param(Order.from_jsons, '"order"', id="json-string"),
    ],
)
def test_string_loaders_reject_documents_that_are_not_mappings(loader: Callable[[str], Order], content: str) -> None:
    with pytest.raises(EleanorError, match="order must be a dictionary"):
        _ = loader(content)


@pytest.mark.parametrize(
    ("loader", "content"),
    [
        pytest.param(Order.from_yamls, "{}", id="yaml"),
        pytest.param(Order.from_tomls, "", id="toml"),
        pytest.param(Order.from_jsons, "{}", id="json"),
    ],
)
def test_string_loaders_reject_an_empty_mapping(loader: Callable[[str], Order], content: str) -> None:
    with pytest.raises(EleanorError, match="order is empty"):
        _ = loader(content)


@pytest.mark.parametrize("content", ["", "\n", "# nothing here\n", BOM])
def test_empty_input_is_reported_as_an_empty_order(content: str) -> None:
    with pytest.raises(EleanorError, match="order is empty"):
        _ = Order.from_file(io.StringIO(content))


STRING_LOADERS: dict[str, Callable[[str | bytes], Order]] = {
    "yaml": Order.from_yamls,
    "toml": Order.from_tomls,
    "json": Order.from_jsons,
}

STREAM_LOADERS: dict[str, Callable[..., Order]] = {
    "yaml": Order.from_yaml,
    "toml": Order.from_toml,
    "json": Order.from_json,
}


@pytest.mark.parametrize("content", ["", "\n", "# nothing here\n"])
@pytest.mark.parametrize("as_bytes", [False, True], ids=["str", "bytes"])
@pytest.mark.parametrize("fmt", FORMATS)
def test_string_loaders_report_blank_input_as_an_empty_order(fmt: str, as_bytes: bool, content: str) -> None:
    if fmt == "json" and content.startswith("#"):
        pytest.skip("JSON has no comment syntax")
    loader = STRING_LOADERS[fmt]

    with pytest.raises(EleanorError, match="order is empty"):
        _ = loader(content.encode() if as_bytes else content)


@pytest.mark.parametrize("fmt", FORMATS)
def test_from_file_reports_an_empty_file_as_an_empty_order(tmp_path: Path, fmt: str) -> None:
    path = write(tmp_path / f"order.{fmt}", "")

    with pytest.raises(EleanorError, match="order is empty"):
        _ = Order.from_file(path)


@pytest.mark.parametrize("fmt", FORMATS)
def test_stream_loaders_report_undecodable_bytes(fmt: str) -> None:
    with pytest.raises(UnicodeDecodeError):
        _ = STREAM_LOADERS[fmt](io.BytesIO(b"\xff\xfe\xfd"))


@pytest.mark.parametrize("source", ["path", "text-stream", "bytes-stream"])
@pytest.mark.parametrize("fmt", FORMATS)
def test_stream_loaders_apply_overrides(tmp_path: Path, fmt: str, source: str) -> None:
    content = template(fmt)
    path = write(tmp_path / f"order.{fmt}", content)
    inputs: dict[str, object] = {
        "path": path,
        "text-stream": io.StringIO(content),
        "bytes-stream": io.BytesIO(content.encode()),
    }
    seed = 7

    order = STREAM_LOADERS[fmt](inputs[source], seed=seed, tags=["override"])

    assert order.seed == seed
    assert order.tags == ["override"]


@pytest.mark.parametrize("fmt", FORMATS)
def test_string_loaders_apply_overrides(fmt: str) -> None:
    seed = 7

    order = STRING_LOADERS[fmt](template(fmt), seed=seed, tags=["override"])  # pyrefly: ignore[unexpected-keyword]

    assert order.seed == seed
    assert order.tags == ["override"]


@pytest.mark.parametrize("fmt", FORMATS)
def test_string_loaders_accept_bytes(fmt: str) -> None:
    loader = {"yaml": Order.from_yamls, "toml": Order.from_tomls, "json": Order.from_jsons}[fmt]

    assert loader(template(fmt).encode()).name == "My Order"


@pytest.mark.parametrize("fmt", FORMATS)
def test_stream_loaders_accept_paths_and_both_stream_kinds(tmp_path: Path, fmt: str) -> None:
    loader = {"yaml": Order.from_yaml, "toml": Order.from_toml, "json": Order.from_json}[fmt]
    content = template(fmt)
    path = write(tmp_path / f"order.{fmt}", content)

    assert loader(path).name == "My Order"
    assert loader(str(path)).name == "My Order"
    assert loader(io.StringIO(content)).name == "My Order"
    assert loader(io.BytesIO(content.encode())).name == "My Order"


def test_from_toml_decodes_a_text_stream_in_any_encoding() -> None:
    content = template("toml").replace('creator = "', 'creator = "é')
    stream = io.TextIOWrapper(io.BytesIO(content.encode("latin-1")), encoding="latin-1")

    assert Order.from_toml(stream).creator.startswith("é")


@pytest.mark.parametrize("fmt", FORMATS)
def test_load_order_reads_a_stream(fmt: str) -> None:
    assert load_order(io.StringIO(template(fmt))).name == "My Order"


def test_load_order_applies_overrides_to_a_stream() -> None:
    seed = 7
    order = load_order(io.StringIO(template("yaml")), seed=seed, tags=["piped"])

    assert order.seed == seed
    assert order.tags == ["piped"]


def test_load_order_detects_the_format_of_a_path_without_an_extension(tmp_path: Path) -> None:
    path = write(tmp_path / "order", json.dumps(json.loads(template("json"))))

    assert load_order(path).name == "My Order"
