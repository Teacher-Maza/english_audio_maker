from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from _rc_bootstrap import V2_ROOT


REPORT = V2_ROOT / "temp" / "rc_validation" / "suite.json"


def main() -> int:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    results = []
    for test in sorted((V2_ROOT / "tests").glob("test_*.py")):
        started = time.perf_counter()
        completed = subprocess.run(
            [sys.executable, "-B", str(test)],
            cwd=V2_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        result = {
            "test": test.name,
            "status": "passed" if completed.returncode == 0 else "failed",
            "seconds": round(time.perf_counter() - started, 3),
        }
        if completed.returncode != 0:
            result["returncode"] = completed.returncode
            result["stdout"] = completed.stdout
            result["stderr"] = completed.stderr
        results.append(result)
    report = {"root": str(V2_ROOT), "tests": results, "passed": sum(x["status"] == "passed" for x in results), "failed": sum(x["status"] != "passed" for x in results)}
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if not report["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
