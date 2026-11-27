"""Screen fixed CTC1 admissions for sensitivity to delayed FDU release."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re

from run_timing import require


CASE = re.compile(r"r(4000|256000)_(none|periodic_10pct)_(fast_high|slow_low)_n1_s(11|29)")
RECORDED = Path(__file__).resolve().parents[1] / "evidence/holding-sensitivity/summary.json"


def read_intervals(path):
    raw = path.read_bytes()
    intervals = []
    admitted = None
    previous = -1
    rejected = Counter()
    for line in raw.splitlines():
        event = json.loads(line)
        now = event["virtual_us"]
        require(type(now) is int and now >= previous, f"Nonmonotonic or noninteger time in {path.name}")
        previous = now
        kind = event["event"]
        if kind == "farm" and event["ret"] > 0:
            require(admitted is None and event["occupancy"] == 1, f"Overlapping original admission in {path.name}")
            admitted = now
        elif kind == "farm":
            rejected[event["occupancy"]] += 1
        elif kind == "commit_release":
            require(event["occupancy"] == 0 and admitted is not None and now > admitted,
                    f"Unmatched original release in {path.name}")
            intervals.append((admitted, now))
            admitted = None
    require(admitted is None and len(intervals) >= 2, f"Incomplete occupancy trace in {path.name}")
    return intervals, rejected, sha256(raw).hexdigest()


def occupancy(intervals, delay):
    # At equal timestamps the release is processed first.
    events = sorted([(start, 1) for start, _ in intervals] +
                    [(end + delay, -1) for _, end in intervals])
    active = peak = 0
    for _, change in events:
        active += change
        peak = max(peak, active)
    return peak


def screen(path, match):
    rate, loss, feedback, seed = match.groups()
    intervals, rejected, digest = read_intervals(path)
    margins = [(start - previous_end, previous_start, previous_end, start)
               for (previous_start, previous_end), (start, _) in zip(intervals, intervals[1:])]
    slack, before_start, before_end, next_start = min(margins)
    require(slack >= 0, f"One-slot reference already overlaps in {path.name}")
    threshold = slack + 1
    at_boundary = occupancy(intervals, slack)
    after_boundary = occupancy(intervals, threshold)
    require((at_boundary, after_boundary) == (1, 2), f"Boundary does not reproduce in {path.name}")
    return dict(trace=path.name, sha256=digest, rate_bps=int(rate), loss=loss, feedback=feedback, seed=int(seed),
                successful_admissions=len(intervals), other_farm_results_by_occupancy=dict(sorted(rejected.items())),
                original_longest_hold_us=max(end - start for start, end in intervals),
                minimum_slack_us=slack, first_extra_delay_requiring_overlap_us=threshold,
                peak_at_slack=at_boundary, peak_at_first_overlap=after_boundary,
                witness=dict(earlier_admission_us=before_start, earlier_release_us=before_end,
                             later_admission_us=next_start))


def audit(trace_dir):
    cases = []
    for path in sorted(trace_dir.rglob("*_n1_*.jsonl")):
        match = CASE.fullmatch(path.stem)
        if match:
            cases.append(screen(path, match))
    require(len(cases) == len({case["trace"] for case in cases}) == 16,
            "Expected exactly 16 unique original one-FDU traces")
    rates = {}
    for rate in (4000, 256000):
        group = [case for case in cases if case["rate_bps"] == rate]
        require(len(group) == 8, f"Unexpected number of traces at {rate}")
        thresholds = [case["first_extra_delay_requiring_overlap_us"] for case in group]
        rates[str(rate)] = dict(traces=len(group), minimum_first_overlap_us=min(thresholds),
                                maximum_first_overlap_us=max(thresholds),
                                threshold_counts=dict(sorted(Counter(thresholds).items())))
    return dict(physical_measurements=False, model="fixed successful admissions, uniform extra release delay",
                cases=cases, by_rate=rates)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_dir", type=Path, help="Directory containing the local archived CTC1 validation traces")
    parser.add_argument("--check", action="store_true", help="Compare with the published numeric summary")
    args = parser.parse_args()
    data = audit(args.trace_dir)
    if args.check:
        saved = json.loads(RECORDED.read_text(encoding="utf-8"))
        require(json.loads(json.dumps(data)) == saved, "Archived holding-sensitivity summary differs")
        print("Verified the 16 fixed-trace occupancy boundaries.")
    else:
        print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
