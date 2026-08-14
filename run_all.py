"""Run the whole pipeline in order and report pass/fail. See README.md."""
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PY = sys.executable

# Run order: data first, then hazard, exposure, vulnerability, deployment.
STEPS = [
    ("src/00_harmonisation.py",       "STAGE 1 DATA: harmonise BER + reference-curve family"),
    ("src/01_hazard_coastal.py",      "STAGE 2 HAZARD: coastal flood, method comparison"),
    ("src/02_hazard_fluvial.py",      "STAGE 2 HAZARD: fluvial flood + river distance (needs internet)"),
    ("src/03_exposure_classifier.py", "STAGE 3 EXPOSURE: dwelling-type classifier"),
    ("src/04_vulnerability_model.py", "STAGE 4 VULNERABILITY: trained depth-damage models"),
    ("src/05_deployment_dublin.py",   "STAGE 5 DEPLOY: apply curve to Dublin, euro band"),
    ("src/06_report.py",              "STAGE 6 REPORT: collect headline results into a summary"),
]


def preflight() -> bool:
    """Refuse to start unless the data layout is complete (reuses prepare_data.validate)."""
    try:
        from prepare_data import validate
        return validate(verbose=True)
    except Exception:
        import config
        needed = [config.BER_CSV, config.JRC_XLSX, config.MIDDLESEX_CSV]
        missing = [p for p in needed if not p.exists()]
        for p in missing:
            print(f"  MISSING: {p}")
        return not missing


def main() -> int:
    print("=" * 78 + "\nPREFLIGHT: checking data layout\n" + "=" * 78)
    if not preflight():
        print("\nData incomplete. See docs/01_data_sources.md and run prepare_data.py. Stopping.")
        return 1
    results = []
    for i, (script, purpose) in enumerate(STEPS, 1):
        print("\n" + "=" * 78 + f"\n[{i}/{len(STEPS)}] {script}\n      {purpose}\n" + "=" * 78)
        t0 = time.time()
        rc = subprocess.run([PY, str(HERE / script)]).returncode
        results.append((script, "OK" if rc == 0 else f"FAILED ({rc})", time.time() - t0))
        if rc != 0:
            # Stop rather than run later stages on stale or missing outputs from this one.
            print(f"\n{script} failed (exit {rc}). Stopping so later stages do not run on stale "
                  f"data. Fix the issue above and re-run; finished stages are cached where possible.")
            break
    print("\n" + "=" * 78 + "\nRUN SUMMARY\n" + "=" * 78)
    for script, status, secs in results:
        print(f"  {status:<12} {secs:6.1f}s  {script}")
    ran = {s for s, _, _ in results}
    for script, _ in STEPS:
        if script not in ran:
            print(f"  {'SKIPPED':<12} {'':6}  {script}")

    all_ok = len(ran) == len(STEPS) and all(s == "OK" for _, s, _ in results)
    if all_ok:
        # Every stage passed, so the artifacts are complete; draw the report figures from them.
        print("\n" + "=" * 78 + "\nREPORT FIGURES\n" + "=" * 78)
        subprocess.run([PY, str(HERE / "scripts/make_report_figures.py")])
    else:
        print("\nPipeline did not finish, so report figures were not generated. Fix the stage "
              "above and re-run, then run: python scripts/make_report_figures.py")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
