"""Summarize paired COP-1 event logs without changing the underlying evidence."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys


def run_data(folder, name):
    summary_bytes = (folder / f"{name}.json").read_bytes()
    trace_bytes = (folder / f"{name}.jsonl").read_bytes()
    summary = json.loads(summary_bytes)
    raw = [json.loads(row) for row in trace_bytes.splitlines()]
    events = []
    sent = Counter()
    clcws = []
    occupancies = []
    for row in raw:
        kind = row["event"]
        if kind == "farm_result":
            result, seq, _, owned = row["fields"][:4]
            occupancies.append(owned)
            kind = "accept" if 0 < result <= 256 else "rejected"
            detail = f"Doluluk {owned} Â· V(R) {seq} Â· FARM {result if result < (1<<31) else result-(1<<32)}"
        elif kind == "handler_commit":
            kind = "commit"
            detail = f"Komut {int(row['uid'][-8:], 16)}"
        elif kind == "tm_arrival":
            control = bytes.fromhex(row["clcw"])
            wait, retry = bool(control[2] & 16), bool(control[2] & 8)
            clcws.append((wait, retry))
            kind = "clcw"
            detail = f"N(R) {control[3]} Â· WAIT {int(wait)} Â· RETRANSMIT {int(retry)}"
        elif kind == "tc_departure":
            wire = row["hex"]
            sent[wire] += 1
            if sent[wire] == 1:
                continue
            kind = "retry"
            detail = f"TC sÄ±ra {row['sequence']}"
        elif kind == "declared_first_frame_loss":
            kind = "loss"
            detail = "Ä°lk Ã§erÃ§eve deney gereÄŸi silindi"
        else:
            continue
        events.append(dict(t=row["virtual_us"], kind=kind, detail=detail))
    assert sum(sent.values()) == summary["tc_instances"], name
    assert max(occupancies) == summary["max_owned_fdu"], name
    assert any(k == "loss" for k in [e["kind"] for e in events]) == summary["case"]["drop_first"], name
    assert summary["complete"] and summary["guards_ok"] and not summary["physical_measurements"], name
    return dict(capacity=summary["case"]["capacity"], events=events, peak=summary["max_owned_fdu"],
                summary_sha256=sha256(summary_bytes).hexdigest(), trace_sha256=sha256(trace_bytes).hexdigest(),
                p95_source_to_sink_virtual_us=summary["p95_quantized_source_to_sink_virtual_us"],
                max_source_to_sink_virtual_us=summary["max_quantized_source_to_sink_virtual_us"],
                sink=summary["exact_sink_count"], frames=summary["tc_instances"],
                retries=sum(count - 1 for count in sent.values()), source=summary["source"],
                clcw_wait=sum(wait for wait, _ in clcws), clcw_retry=sum(retry for _, retry in clcws),
                elapsed_us=summary["elapsed_virtual_us"], time_quantum_bound_us=summary["output_collection_quantum_max_us"])


def summarize(folder):
    scenarios = {}
    for slug in ("nominal", "first-loss"):
        first, second = [run_data(folder, f"{slug}-n{n}") for n in (1, 2)]
        source = first.pop("source")
        assert source == second.pop("source"), slug
        source_sha256 = sha256(json.dumps(source, sort_keys=True).encode("utf-8")).hexdigest()
        delta = next(((a, b) for a, b in zip(first["events"], second["events"]) if a != b), None)
        different = delta is not None or len(first["events"]) != len(second["events"])
        focus = min(a["t"] for a in delta) if delta else next(
            (event["t"] for event in first["events"] if event["kind"] in {"retry", "accept"}), 0)
        scenarios[slug] = dict(runs=[first, second], max=max(first["elapsed_us"], second["elapsed_us"]),
                               focus=focus, events_differ=different, source_sha256=source_sha256,
                               comparison=("Ä°lk farklÄ± olay zamana iÅŸaretlendi." if delta else
                                           "Ä°ki koÅŸuda gÃ¶sterilen olaylar ve zamanlarÄ± aynÄ±." if not different else
                                           "Ortak olay sÄ±rasÄ± aynÄ±. KoÅŸulardan birinde daha fazla olay var."))
    return scenarios


if __name__ == "__main__":
    print(json.dumps(summarize(Path(sys.argv[1])), ensure_ascii=True, indent=2))
