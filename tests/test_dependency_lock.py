"""Offline lock/launcher contract checks; not a substitute for Windows execution."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DependencyLockTests(unittest.TestCase):
    def test_runtime_closure_has_exact_pins_and_sha256_hashes(self):
        text = (ROOT / 'requirements.txt').read_text()
        logical = text.replace('\\\n', ' ')
        entries = [line.strip() for line in logical.splitlines()
                   if line.strip() and not line.lstrip().startswith('#')]
        names = set()
        for entry in entries:
            self.assertRegex(entry, r"^[\w-]+==[^\s]+(?: ; python_full_version (?:<|>=) '3.14')?(?:\s+--hash=sha256:[a-f0-9]{64})+$")
            names.add(entry.split('==')[0])
        self.assertTrue({'pandas', 'pyarrow', 'duckdb', 'openpyxl', 'defusedxml',
                         'numpy', 'python-dateutil', 'pytz', 'tzdata', 'et-xmlfile'} <= names)

    def test_original_direct_pins_preserved(self):
        source = (ROOT / 'requirements.in').read_text().splitlines()
        for pin in ('pandas==2.3.3', 'pyarrow==24.0.0', 'duckdb==1.5.3',
                    'openpyxl==3.1.5', 'defusedxml==0.7.1'):
            self.assertIn(pin, source)

    def test_launchers_fail_closed_before_python_if_lock_missing(self):
        for name in ('Run-ETL.ps1', 'Run-Query.ps1'):
            with self.subTest(launcher=name):
                text = (ROOT / name).read_text()
                guard = text.index('if (-not (Test-Path -LiteralPath $ReqFile -PathType Leaf))')
                end = text.index('\n}', guard)
                self.assertIn('exit 1', text[guard:end])
                self.assertIn('Restore it from Git or re-clone', text[guard:end])
                self.assertLess(end, text.index('foreach ($candidate'))
                installs = re.findall(r'^.*\bpip install\b.*$', text, re.M)
                self.assertEqual(len(installs), 1)
                self.assertIn('--require-hashes --only-binary=:all: -r $ReqFile', installs[0])
                install_end = text.index('if ($LASTEXITCODE -ne 0)', text.index(installs[0]))
                self.assertIn('exit 1', text[install_end:text.index('\n}', install_end)])
                self.assertNotIn('unpinned fallback', text)
                self.assertNotIn('pip install $pkg', text)


if __name__ == '__main__':
    unittest.main()
