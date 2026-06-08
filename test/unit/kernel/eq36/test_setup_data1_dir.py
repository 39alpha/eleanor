import contextlib
from pathlib import Path

from pytest_mock import MockerFixture

from eleanor.config.kernel import KernelConfig
from eleanor.kernel.eq36.kernel import Eq36Kernel
from eleanor.kernel.eq36.settings import IOPG_1, Eq3Settings, Eq6Settings, Eq36Settings
from eleanor.order import Order
from eleanor.parameters import Parameter


def _make_order(mocker: MockerFixture) -> Order:
    order = mocker.create_autospec(Order, instance=True)
    order.kernel = KernelConfig(
        kind="eq36",
        settings=Eq36Settings(
            model=IOPG_1.B_DOT,
            charge_balance="Cl-",
            eq3_config=Eq3Settings(),
            eq6_config=Eq6Settings(),
        ),
    )
    order.temperature = Parameter.load({"min": 1.0, "max": 2.0})
    order.pressure = Parameter.load({"min": 3.0, "max": 4.0})
    return order  # type: ignore[return-value]


def test_setup_uses_absolute_data1_dir_directly_ignoring_env_var(mocker: MockerFixture) -> None:
    """Absolute paths are passed straight to WorkingDirectory; the env var is never consulted."""
    order = _make_order(mocker)
    wd_mock = mocker.patch(
        "eleanor.kernel.eq36.kernel.tool_room.WorkingDirectory",
        return_value=contextlib.nullcontext(),
    )
    _ = mocker.patch("eleanor.kernel.eq36.kernel.tool_room.find_files", return_value=([], []))
    mocker.patch.dict("os.environ", {"ELEANOR_EQ36_DATA1_DIR": "/global/data1"})

    Eq36Kernel().setup(order, data1_dir="/absolute/path")

    wd_mock.assert_called_once_with(Path("/absolute/path"))


def test_setup_uses_relative_data1_dir_when_it_exists_locally(mocker: MockerFixture) -> None:
    """A relative path that exists locally is used as-is, even when the env var is set."""
    order = _make_order(mocker)
    wd_mock = mocker.patch(
        "eleanor.kernel.eq36.kernel.tool_room.WorkingDirectory",
        return_value=contextlib.nullcontext(),
    )
    _ = mocker.patch("eleanor.kernel.eq36.kernel.tool_room.find_files", return_value=([], []))
    _ = mocker.patch.object(Path, "exists", return_value=True)
    mocker.patch.dict("os.environ", {"ELEANOR_EQ36_DATA1_DIR": "/global/data1"}, clear=True)

    Eq36Kernel().setup(order, data1_dir="local/data1")

    wd_mock.assert_called_once_with(Path("local/data1"))


def test_setup_falls_back_to_env_var_when_relative_path_does_not_exist(mocker: MockerFixture) -> None:
    """A missing relative path is prefixed with ELEANOR_EQ36_DATA1_DIR when the env var is set."""
    order = _make_order(mocker)
    wd_mock = mocker.patch(
        "eleanor.kernel.eq36.kernel.tool_room.WorkingDirectory",
        return_value=contextlib.nullcontext(),
    )
    _ = mocker.patch("eleanor.kernel.eq36.kernel.tool_room.find_files", return_value=([], []))
    _ = mocker.patch.object(Path, "exists", return_value=False)
    mocker.patch.dict("os.environ", {"ELEANOR_EQ36_DATA1_DIR": "/global/data1"}, clear=True)

    Eq36Kernel().setup(order, data1_dir="relative/data1")

    wd_mock.assert_called_once_with(Path("/global/data1") / Path("relative/data1"))


def test_setup_uses_relative_data1_dir_as_is_when_env_var_is_unset(mocker: MockerFixture) -> None:
    """A missing relative path is left unchanged when ELEANOR_EQ36_DATA1_DIR is not set."""
    order = _make_order(mocker)
    wd_mock = mocker.patch(
        "eleanor.kernel.eq36.kernel.tool_room.WorkingDirectory",
        return_value=contextlib.nullcontext(),
    )
    _ = mocker.patch("eleanor.kernel.eq36.kernel.tool_room.find_files", return_value=([], []))
    _ = mocker.patch.object(Path, "exists", return_value=False)
    mocker.patch.dict("os.environ", {}, clear=True)

    Eq36Kernel().setup(order, data1_dir="relative/data1")

    wd_mock.assert_called_once_with(Path("relative/data1"))
