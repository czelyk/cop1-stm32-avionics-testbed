"""Run a matched COP-1 capacity comparison using the existing native peers."""
import argparse
from pathlib import Path
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from bootstrap import bootstrap
from lab import execute, find_tool, new_run


def run_in_workdir(run, reverse, service_screen):
    from coupled_renode import Fop, Renode, run_case

    outputs = []
    scenarios = ([(f"hold-{ticks:02d}", False, ticks) for ticks in (0, 5, 15)]
                 if service_screen else [("nominal", False, None), ("first-loss", True, None)])
    for slug, dropped, hold in scenarios:
        for capacity in ((2, 1) if reverse else (1, 2)):
            # Independent resets and processes keep the only paired change at capacity.
            case = dict(id=f"{slug}-n{capacity}", rate_bps=256000, feedback_ms=100, seed=67,
                        capacity=capacity, drop_first=dropped, initial_sequence=255, mips=100)
            if hold is not None:
                case["service_hold_ticks"] = hold
            target = Renode(case["id"])
            try:
                peer = Fop(case["id"])
                try:
                    outputs.append(run_case(target, peer, case, "capacity-pair"))
                finally:
                    peer.close()
            finally:
                target.close()
            result = outputs[-1]
            print(json.dumps({key: result[key] for key in
                              ("case", "complete", "exact_sink_count", "max_owned_fdu", "tc_instances")}), flush=True)
            if not result["complete"]:
                raise RuntimeError("Incomplete case retained in " + str(run))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reverse", action="store_true", help="Run two slots before one in each matched pair")
    parser.add_argument("--service-screen", action="store_true", help="Run the no-loss service-pressure pairs")
    args = parser.parse_args()
    run, work = new_run("capacity_service" if args.service_screen else "capacity_pair")
    print(run, flush=True)
    env = dict(os.environ)
    env["ARM_GCC"] = str(find_tool("arm-none-eabi-gcc", "ARM_GCC"))
    env["CTC_NASA_DIR"] = str(bootstrap("nasa") / "nasa")
    env["RENODE_HOME"] = str(bootstrap("renode") / "renode/renode_1.17.0-portable")
    env["JAVA"] = str(find_tool("java", "JAVA"))
    classpath = ROOT / ".deps" / "yamcs-dependencies.jar"
    if not classpath.is_file():
        parser.error("Prepare the pinned Yamcs classpath with tools/prepare_yamcs.py first.")
    env["YAMCS_CLASSPATH"] = str(classpath)
    profile = "renode-service" if args.service_screen else "legacy"
    execute([sys.executable, work / "build_firmware.py", "--profile", profile], work, "build.log", env)
    execute([sys.executable, ROOT / "tools" / "compile_peer.py", work], ROOT, run / "peer-build.log", env)
    worker = [sys.executable, Path(__file__).resolve(), "--work", work, run]
    if args.reverse:
        worker.append("--reverse")
    if args.service_screen:
        worker.append("--service-screen")
    execute(worker, work, "capacity-cases.log", env)
    print((work / "capacity-cases.log").read_text(encoding="utf-8"), end="")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--work":
        sys.path.insert(0, sys.argv[2])
        run_in_workdir(Path(sys.argv[3]), "--reverse" in sys.argv[4:], "--service-screen" in sys.argv[4:])
    else:
        main()
