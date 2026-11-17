"""Compare a bounded loop in Mini-C, C, C-generated IR, and Rust."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


LAB = Path(__file__).resolve().parent
ROOT = LAB.parents[1]
CASES = ((-2, 0), (0, 0), (1, 1), (4, 10), (8, 36))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clang", default="clang", help="Clang executable name or path")
    parser.add_argument("--rustc", default="rustc", help="Rust compiler executable name or path")
    arguments = parser.parse_args()
    clang = shutil.which(arguments.clang)
    rustc = shutil.which(arguments.rustc)
    if clang is None or rustc is None:
        missing = arguments.clang if clang is None else arguments.rustc
        parser.error(f"Cannot find the executable {missing!r}. Install it or supply its path.")

    output = ROOT / "build" / "loop-ir"
    output.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="run-", dir=output))
    print(f"Lab files: {work}", flush=True)
    report = {"status": "running", "commands": [], "results": []}
    environment = os.environ.copy()

    def run(label, command, expected=None):
        command = [str(part) for part in command]
        try:
            result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, timeout=30)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"{label}: the command exceeded 30 seconds.") from None
        report["commands"].append({
            "label": label, "arguments": command, "exit_status": result.returncode,
            "stdout": result.stdout.decode("utf-8", errors="replace"),
            "stderr": result.stderr.decode("utf-8", errors="replace"),
        })
        if result.returncode != 0 or result.stderr or (expected is not None and result.stdout != expected):
            raise RuntimeError(
                f"{label}: received status {result.returncode}, stdout {result.stdout!r}, "
                f"and stderr {result.stderr!r}. Expected status 0, empty stderr, "
                + (f"and stdout {expected!r}." if expected is not None else "and command output.")
            )
        return result.stdout

    try:
        if sys.platform == "darwin":
            if not environment.get("SDKROOT"):
                sdk = run("macOS SDK", ["xcrun", "--sdk", "macosx", "--show-sdk-path"])
                environment["SDKROOT"] = sdk.decode("utf-8").strip()
            report["SDKROOT"] = environment["SDKROOT"]
        for label, command, filename in (
            ("Python version", [sys.executable, "--version"], "python-version.txt"),
            ("Clang version", [clang, "--version"], "clang-version.txt"),
            ("Rust version", [rustc, "-Vv"], "rustc-version.txt"),
        ):
            (work / filename).write_bytes(run(label, command))

        minic = [sys.executable, "-m", "minic"]
        for mode, filename in (("--bytecode", "sum.bytecode"), ("--bytecode-opt", "sum.opt.bytecode")):
            (work / filename).write_bytes(run(mode, [*minic, mode, LAB / "sum.mc"]))

        native = []
        suffix = ".exe" if os.name == "nt" else ""
        for level in (0, 1):
            ir = work / f"sum.c.O{level}.ll"
            c_binary = work / f"sum.c.O{level}{suffix}"
            ir_binary = work / f"sum.ir.O{level}{suffix}"
            rust_binary = work / f"sum.rust.O{level}{suffix}"
            c_flags = [clang, "-std=c17", "-Wall", "-Wextra", "-Wpedantic", f"-O{level}"]
            run(f"C IR O{level}", [*c_flags, "-S", "-emit-llvm", "-fno-discard-value-names",
                                   LAB / "sum.c", "-o", ir], b"")
            run(f"C build O{level}", [*c_flags, LAB / "sum.c", LAB / "driver.c", "-o", c_binary], b"")
            run(f"IR build O{level}", [*c_flags, ir, LAB / "driver.c", "-o", ir_binary], b"")
            rust_ir = work / f"sum.rust.O{level}.ll"
            run(f"Rust build O{level}", [rustc, "--edition=2021", "--crate-name", "loop_sum",
                                        "-C", f"opt-level={level}", "-C", "overflow-checks=yes",
                                        f"--emit=llvm-ir={rust_ir},link={rust_binary}", LAB / "sum.rs"], b"")
            native.extend(((f"C O{level}", c_binary), (f"IR O{level}", ir_binary),
                           (f"Rust O{level}", rust_binary)))

        source = (LAB / "sum.mc").read_text(encoding="ascii")
        for limit, total in CASES:
            case = work / f"limit-{limit}.mc"
            case.write_text(f"{source}\nint main() {{ return sum_next({limit}); }}\n", encoding="ascii")
            expected = f"{total}\n".encode("ascii")
            commands = [(mode, [*minic, mode, case]) for mode in ("--run", "--run-vm", "--run-vm-opt")]
            commands.extend((name, [binary, str(limit)]) for name, binary in native)
            for name, command in commands:
                run(f"{name}, limit {limit}", command, expected)
                report["results"].append({"path": name, "limit": limit, "result": total})
            print(f"limit {limit}: all nine paths returned {total}", flush=True)
        report["status"] = "passed"
        print(f"All {len(report['results'])} execution checks passed.")
        return 0
    except (OSError, RuntimeError) as error:
        report["status"] = "failed"
        report["error"] = str(error)
        print(f"error: {error}", file=sys.stderr)
        return 1
    finally:
        (work / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
