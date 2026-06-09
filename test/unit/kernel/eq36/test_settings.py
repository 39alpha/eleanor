from unittest import TestCase

from eleanor.exceptions import EleanorException
from eleanor.kernel.eq36.settings import (
    EQ36_MODEL_EXTENSIONS,
    IODB_6,
    IOPG_1,
    IOPR_2,
    IOPT_2,
    IOPT_4,
    IOPT_19,
    Eq3Settings,
    Eq6Settings,
    Eq36Settings,
    get_setting,
)
from eleanor.kernel.exceptions import EleanorKernelException


class TestEq36Settings(TestCase):
    """
    Tests of the eleanor.kernel.eq36.settings module.
    """

    def test_get_setting_from_int_and_name(self) -> None:
        """
        Ensure get_setting resolves enum values from numeric and string forms.
        """
        self.assertEqual(get_setting({"iopt_2": 1}, IOPT_2), IOPT_2.TRUE_KINETICS)
        self.assertEqual(
            get_setting({"iopt_2": "TRUE_KINETICS"}, IOPT_2), IOPT_2.TRUE_KINETICS
        )

    def test_get_setting_required_and_invalid_raise(self) -> None:
        """
        Ensure get_setting raises for missing required values and unexpected values.
        """
        with self.assertRaises(EleanorKernelException):
            _ = get_setting({}, IOPT_2)

        with self.assertRaises(EleanorKernelException):
            _ = get_setting({"iopt_2": "NOT_A_MEMBER"}, IOPT_2)

    def test_eq3_config_properties_and_verbose_copy(self) -> None:
        """
        Ensure Eq3Settings index-array helpers and make_verbose behavior are correct.
        """
        cfg = Eq3Settings()
        self.assertEqual(len(cfg.iopt), 20)
        self.assertEqual(len(cfg.iopg), 20)
        self.assertEqual(len(cfg.iopr), 20)
        self.assertEqual(len(cfg.iodb), 20)

        verbose = cfg.make_verbose()
        self.assertIsNot(cfg, verbose)
        self.assertEqual(verbose.iopt_4, IOPT_4.PERMIT_SOLID_SOLUTIONS)
        self.assertEqual(verbose.iopr_2, IOPR_2.PRINT_RXNS_LOGK_DATA)
        self.assertEqual(verbose.iodb_6, IODB_6.DETAILED_AFFINITY_CALC)
        self.assertEqual(cfg.iopt_4, IOPT_4.IGNORE_SOLID_SOLUTIONS)

    def test_eq6_config_properties(self) -> None:
        """
        Ensure Eq6Settings index-array helpers produce the expected lengths.
        """
        cfg = Eq6Settings()
        self.assertEqual(len(cfg.iopt), 20)
        self.assertEqual(len(cfg.iopg), 20)
        self.assertEqual(len(cfg.iopr), 20)
        self.assertEqual(len(cfg.iodb), 20)

    def test_from_dict_success_with_eq6_and_string_model_extension(self) -> None:
        """
        Ensure Eq36Settings.from_dict parses valid configs and extension-based model aliases.
        """
        cfg = Eq36Settings.from_dict(
            {
                "model": "pit",
                "charge_balance": "Cl-",
                "timeout": 0,
                "track_path": True,
                "basis_map": {"Na+": "NaOH(aq)"},
                "redox_species": "pe",
                "eq3_config": {
                    "iopt_2": "TRUE_KINETICS",
                    "iopt_19": "SIXI_FLUID_1_AS_FLUID_MIX",
                    "iopr_2": 3,
                },
                "eq6_config": {
                    "jtemp": "CONSTANT_T",
                    "steps_print_interval": 77,
                    "iopt_2": 1,
                },
            }
        )

        self.assertEqual(cfg.model, IOPG_1.PITZER)
        self.assertEqual(cfg.charge_balance, "Cl-")
        self.assertIsNone(cfg.timeout)
        self.assertTrue(cfg.track_path)
        self.assertEqual(cfg.basis_map, {"Na+": "NaOH(aq)"})
        self.assertEqual(cfg.redox_species, "pe")
        eq6 = cfg.eq6_config
        self.assertIsNotNone(eq6)
        if eq6 is None:
            raise AssertionError("expected eq6_config to be present")
        self.assertEqual(eq6.steps_print_interval, 77)

    def test_from_dict_eq6_disabled(self) -> None:
        """
        Ensure explicitly false eq6_config disables Eq6Settings creation.
        """
        cfg = Eq36Settings.from_dict(
            {"model": "b-dot", "charge_balance": "Cl-", "eq6_config": False}
        )
        self.assertIsNone(cfg.eq6_config)

    def test_from_dict_model_as_int(self) -> None:
        """
        Ensure integer model values map through IOPG_1 enum conversion.
        """
        cfg = Eq36Settings.from_dict(
            {"model": int(IOPG_1.DAVIES), "charge_balance": "Cl-"}
        )
        self.assertEqual(cfg.model, IOPG_1.DAVIES)

    def test_from_dict_model_davies_string(self) -> None:
        """
        Ensure explicit davies model string maps to IOPG_1.DAVIES.
        """
        cfg = Eq36Settings.from_dict({"model": "davies", "charge_balance": "Cl-"})
        self.assertEqual(cfg.model, IOPG_1.DAVIES)

    def test_from_dict_model_hc_dh_string(self) -> None:
        """
        Ensure explicit hc_dh model string maps to IOPG_1.HC_DH.
        """
        cfg = Eq36Settings.from_dict({"model": "hc_dh", "charge_balance": "Cl-"})
        self.assertEqual(cfg.model, IOPG_1.HC_DH)

    def test_from_dict_model_validation(self) -> None:
        """
        Ensure invalid model types and values raise EleanorException.
        """
        with self.assertRaises(EleanorException):
            _ = Eq36Settings.from_dict(
                {"model": "unsupported", "charge_balance": "Cl-"}
            )

        with self.assertRaises(EleanorException):
            _ = Eq36Settings.from_dict({"model": object(), "charge_balance": "Cl-"})

    def test_from_dict_field_type_validations(self) -> None:
        """
        Ensure type checks for charge_balance, basis_map, redox_species, timeout, and track_path.
        """
        with self.assertRaises(EleanorException):
            _ = Eq36Settings.from_dict({"model": "b-dot", "charge_balance": 1})

        with self.assertRaises(EleanorException):
            _ = Eq36Settings.from_dict(
                {"model": "b-dot", "charge_balance": "Cl-", "basis_map": []}
            )

        with self.assertRaises(EleanorException):
            _ = Eq36Settings.from_dict(
                {"model": "b-dot", "charge_balance": "Cl-", "redox_species": 7}
            )

        with self.assertRaises(EleanorException):
            _ = Eq36Settings.from_dict(
                {"model": "b-dot", "charge_balance": "Cl-", "timeout": "10"}
            )

        with self.assertRaises(EleanorException):
            _ = Eq36Settings.from_dict(
                {"model": "b-dot", "charge_balance": "Cl-", "track_path": "yes"}
            )

    def test_from_dict_rejects_unsupported_eq3_iopt_19(self) -> None:
        """
        Ensure unsupported eq3_config iopt_19 values are rejected.
        """
        with self.assertRaises(EleanorException):
            _ = Eq36Settings.from_dict(
                {
                    "model": "b-dot",
                    "charge_balance": "Cl-",
                    "eq3_config": {"iopt_19": int(IOPT_19.NORMAL_PICKUP)},
                }
            )

    def test_model_extensions_registry_contains_expected_aliases(self) -> None:
        """
        Ensure common EQ36 model extensions map to valid model names.
        """
        self.assertEqual(EQ36_MODEL_EXTENSIONS["pit"], "pitzer")
        self.assertEqual(EQ36_MODEL_EXTENSIONS["dav"], "davies")
