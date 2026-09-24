#!/usr/bin/env python3
"""Verify legacy Top Shooter surfaces remain byte-for-byte frozen."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import NoReturn

SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_OBJECT_ID = re.compile(r"^[0-9a-f]{40,64}$")


def fail(message: str) -> NoReturn:
    print(f"repository guard failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("orchestration/protected-files.json"),
    )
    parser.add_argument("--expected-baseline")
    return parser.parse_args()


def resolve_inside(root: Path, relative: str) -> Path:
    candidate = PurePosixPath(relative)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        fail(f"unsafe protected path: {relative!r}")
    resolved = (root / Path(*candidate.parts)).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        fail(f"protected path escapes root: {relative!r}")
    return resolved


def main() -> int:
    args = parse_args()
    root = args.root.resolve(strict=True)
    manifest_path = args.manifest
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"cannot read manifest: {error}")

    if set(document) != {"schema_version", "baseline_commit", "protected_files"}:
        fail("manifest keys are not exact")
    if document["schema_version"] != 2:
        fail("unsupported manifest schema")
    baseline = document["baseline_commit"]
    if not isinstance(baseline, str) or not GIT_OBJECT_ID.fullmatch(baseline):
        fail("baseline_commit is invalid")
    if args.expected_baseline is not None and baseline != args.expected_baseline:
        fail("manifest baseline does not match the externally supplied baseline")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", baseline, "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if ancestor.returncode != 0:
        fail("baseline_commit is not an ancestor of HEAD")
    protected = document["protected_files"]
    if not isinstance(protected, dict) or not protected:
        fail("protected_files must be a non-empty object")

    for relative, expected in sorted(protected.items()):
        if not isinstance(relative, str) or not isinstance(expected, str) or not SHA256.fullmatch(expected):
            fail("manifest path/hash entry is invalid")
        target = resolve_inside(root, relative)
        if target.is_symlink() or not target.is_file():
            fail(f"protected file is missing or not regular: {relative}")
        observed = hashlib.sha256(target.read_bytes()).hexdigest()
        if observed != expected:
            fail(f"hash mismatch for {relative}: expected {expected}, observed {observed}")
        baseline_blob = subprocess.run(
            ["git", "show", f"{baseline}:{relative}"],
            cwd=root,
            check=False,
            capture_output=True,
        )
        if baseline_blob.returncode != 0:
            fail(f"protected file is absent from baseline: {relative}")
        baseline_hash = hashlib.sha256(baseline_blob.stdout).hexdigest()
        if baseline_hash != expected:
            fail(
                f"baseline hash mismatch for {relative}: expected {expected}, observed {baseline_hash}"
            )

    print(f"repository guard passed: {len(protected)} protected files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
