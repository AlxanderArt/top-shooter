import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools" / "verify_orchestration_foundation.py"


def run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, check=False, capture_output=True, text=True)


class RepositoryGuardTests(unittest.TestCase):
    def test_binds_manifest_to_external_baseline_and_rejects_self_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(run("git", "init", "-b", "main", cwd=root).returncode, 0)
            self.assertEqual(run("git", "config", "user.name", "Test", cwd=root).returncode, 0)
            self.assertEqual(
                run("git", "config", "user.email", "test@example.invalid", cwd=root).returncode,
                0,
            )

            protected = root / "legacy.txt"
            protected.write_text("frozen\n", encoding="utf-8")
            self.assertEqual(run("git", "add", "legacy.txt", cwd=root).returncode, 0)
            self.assertEqual(run("git", "commit", "-m", "baseline", cwd=root).returncode, 0)
            baseline = run("git", "rev-parse", "HEAD", cwd=root).stdout.strip()
            digest = hashlib.sha256(protected.read_bytes()).hexdigest()
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "baseline_commit": baseline,
                        "protected_files": {"legacy.txt": digest},
                    }
                ),
                encoding="utf-8",
            )

            accepted = run(
                sys.executable,
                str(SCRIPT),
                "--root",
                str(root),
                "--manifest",
                str(manifest),
                "--expected-baseline",
                baseline,
                cwd=root,
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)

            protected.write_text("mutated\n", encoding="utf-8")
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document["protected_files"]["legacy.txt"] = hashlib.sha256(
                protected.read_bytes()
            ).hexdigest()
            manifest.write_text(json.dumps(document), encoding="utf-8")

            rejected = run(
                sys.executable,
                str(SCRIPT),
                "--root",
                str(root),
                "--manifest",
                str(manifest),
                "--expected-baseline",
                baseline,
                cwd=root,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("baseline hash mismatch", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
