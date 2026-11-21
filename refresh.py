# One command to bring all market data up to date:
#   .\.venv\Scripts\python.exe refresh.py
#
# Runs, in order: check the events file, download prices, download earnings dates,
# recalculate event reactions, then redraw the static charts. Stops at the first failure.

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent

STEPS = [
    ("Check events file", "check_events.py"),
    ("Download prices", "download_prices.py"),
    ("Download earnings dates", "download_earnings.py"),
    ("Recalculate event reactions", "calculate_reactions.py"),
    ("Redraw charts", "make_charts.py"),
]


def refresh_market_data(quiet=False):
    """Run every step. Returns True if all succeeded. Used by the news pipeline too."""
    for name, script in STEPS:
        started = time.time()
        result = subprocess.run(
            [sys.executable, "-W", "ignore", script], cwd=ROOT, capture_output=True, text=True,
        )
        took = time.time() - started
        failed = result.returncode != 0 or "problem(s)" in result.stdout  # check_events reports problems in stdout
        if not quiet or failed:
            print(f"{'FAILED' if failed else 'ok':>6}  {name} ({took:.1f}s)")
        if failed:
            print(result.stdout[-2000:], result.stderr[-2000:], sep="\n")
            return False
    return True


if __name__ == "__main__":
    ok = refresh_market_data()
    print("All data refreshed." if ok else "Refresh stopped early, see the error above.")
    sys.exit(0 if ok else 1)
