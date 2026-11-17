"""Compare generated Mini-C programs across the three implementations."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

if __package__:
    from .generated_cases import DEFAULT_ROUNDS, DEFAULT_SEED, Case, generate_cases
else:
    from generated_cases import DEFAULT_ROUNDS, DEFAULT_SEED, Case, generate_cases


ROOT = Path(__file__).resolve().parents[1]
MODES = ("--run", "--run-vm", "--run-vm-opt")


def reference_path(relative: str) -> Path:
    for parent in ROOT.parents:
        candidate = parent / relative
        if candidate.is_file():
            return candidate
    return ROOT.parent / relative


def expected_result(case: Case, path: Path) -> tuple[int, bytes, bytes]:
    if case.error is not None:
        error = case.error
        suffix = f":{error.line}:{error.column}: error: {error.message}\n".encode("ascii")
        return 1, b"", os.fsencode(path) + suffix
    if case.value is None:
        output = b""
    elif type(case.value) is bool:
        output = b"true\n" if case.value else b"false\n"
    else:
        output = f"{case.value}\n".encode("ascii")
    return 0, output, b""


def _result_record(result):
    status, output, error = result
    return {"status": status, "stdout_hex": output.hex(), "stderr_hex": error.hex()}


def validate(cases, commands, output: Path, seed: int, rounds: int, timeout: int) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix=f"seed-{seed}-", dir=output)).resolve()
    record = {"seed": seed, "rounds": rounds, "cases": len(cases), "comparisons": 0,
              "categories": dict(sorted(Counter(case.category for case in cases).items())),
              "commands": commands, "timeout_seconds": timeout}
    print(f"Validation files: {run}", flush=True)
    with tempfile.TemporaryDirectory(prefix="inputs-", dir=run) as directory:
        for case in cases:
            path = Path(directory) / (case.name + ".mc")
            path.write_text(case.source, encoding="ascii")
            expected = expected_result(case, path)
            for language, command in commands:
                for mode in MODES:
                    arguments = [*command, mode, str(path)]
                    try:
                        process = subprocess.run(arguments, cwd=ROOT, capture_output=True, timeout=timeout)
                        actual = process.returncode, process.stdout, process.stderr
                        detail = None if actual == expected else _result_record(actual)
                    except (OSError, subprocess.TimeoutExpired) as error:
                        detail = {"process_error": str(error)}
                    record["comparisons"] += 1
                    if detail is not None:
                        (run / "failure.mc").write_text(case.source, encoding="ascii")
                        record["failure"] = {"case": case.name, "language": language, "mode": mode,
                                             "command": arguments, "expected": _result_record(expected),
                                             "actual": detail}
                        (run / "report.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
                        raise ValueError(f"{case.name}: {language} {mode} differs. Read {run / 'report.json'}.")
    (run / "report.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"Passed {len(cases)} cases and {record['comparisons']} command comparisons with seed {seed}.")
    return run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    parser.add_argument("--limit", type=int, help="Stop after this number of cases.")
    parser.add_argument("--timeout", type=int, default=10, help="Maximum seconds for each process.")
    parser.add_argument("--output", type=Path, default=ROOT / "build/validation")
    parser.add_argument("--cpp", type=Path, default=reference_path("compiler-mini-c/build/minic"))
    parser.add_argument("--rust", type=Path, default=reference_path("compiler-mini-rust/target/debug/compiler-mini-rust"))
    args = parser.parse_args()
    if args.rounds <= 0 or args.timeout <= 0 or (args.limit is not None and args.limit <= 0):
        parser.error("Rounds, timeout, and limit must be greater than zero.")
    cases = generate_cases(args.seed, args.rounds)
    if args.limit is not None:
        cases = cases[:args.limit]
    commands = [("C++", [str(args.cpp.resolve())]), ("Rust", [str(args.rust.resolve())]),
                ("Python", [sys.executable, "-m", "minic"])]
    try:
        validate(cases, commands, args.output, args.seed, args.rounds, args.timeout)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
