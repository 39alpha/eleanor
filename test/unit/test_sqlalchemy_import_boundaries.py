import re
from pathlib import Path

from .common import TestCase


SQLALCHEMY_IMPORT_PATTERN = re.compile(r'^\s*(?:from|import)\s+sqlalchemy\b')


class TestSqlalchemyImportBoundaries(TestCase):
    """
    Tests that SQLAlchemy imports stay isolated to sink-owned persistence modules.
    """

    def test_sqlalchemy_imports_only_exist_under_output_postgres(self):
        """
        Ensure non-sink modules do not import SQLAlchemy directly.
        """
        project_root = Path(__file__).resolve().parents[2]
        package_root = project_root / 'eleanor'
        offenders: list[str] = []

        for py_file in package_root.rglob('*.py'):
            relative = py_file.relative_to(package_root).as_posix()
            if relative.startswith('output/postgres/'):
                continue

            for line in py_file.read_text(encoding='utf-8').splitlines():
                if SQLALCHEMY_IMPORT_PATTERN.match(line):
                    offenders.append(relative)
                    break

        self.assertEqual(
            offenders,
            [],
            msg='SQLAlchemy imports must be isolated under eleanor/output/postgres/: '
            + ', '.join(sorted(offenders)),
        )
