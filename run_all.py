"""Top-level entrypoint — runs the full pipeline for all tabs."""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(description="Run all pipelines")
    parser.add_argument("--skip-pull", action="store_true", help="Skip Metabase pull")
    parser.add_argument("--month", type=str, default=None, help="Override close month (YYYY-MM)")
    parser.add_argument("--tab", choices=["recon", "experiments", "all"], default="all",
                        help="Which tab pipeline to run (default: all)")
    args = parser.parse_args()

    if args.tab in ("recon", "all"):
        from recon import run as recon_run
        sys.argv = [sys.argv[0]]
        if args.skip_pull:
            sys.argv.append("--skip-pull")
        if args.month:
            sys.argv += ["--month", args.month]
        recon_run.main()

    if args.tab in ("experiments", "all"):
        from experiments import run as experiments_run
        experiments_run.main()


if __name__ == "__main__":
    main()
