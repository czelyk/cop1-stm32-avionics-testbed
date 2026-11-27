"""Summarize paired COP-1 event logs without changing the underlying evidence."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path


def run_data(folder, name):
    summary_bytes = (folder / f"{name}.json").read_bytes()
    trace_bytes = (folder / f"{name}.jsonl").read_bytes()
    summary = json.loads(summary_bytes)
    raw = [json.loads(row) for row in trace_bytes.splitlines()]
    events = []
    sent = Counter()
    clcws = []
    occupancies = []
    arrivals, admissions, failed_while_full = [], [], []
    for row in raw:
        kind = row["event"]
        if kind == "tc_ingress_message":
            arrivals.append(row)
            continue
        if kind == "farm_result":
            result, seq, flags, owned = row["fields"][:4]
            occupancies.append(owned)
            signed = result - (1 << 32) if result >= (1 << 31) else result
            admissions.append((row["virtual_us"], signed, flags, owned))
            kind = "accept" if 0 < signed <= 256 else "rejected"
            detail = f"Doluluk {owned} \u00b7 V(R) {seq} \u00b7 FARM {signed}"
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
    assert len(arrivals) == len(admissions) > 0, name
    assert len(arrivals) + int(summary["case"]["drop_first"]) == summary["tc_instances"], name
    assert max(occupancies) == summary["max_owned_fdu"], name
    assert any(k == "loss" for k in [e["kind"] for e in events]) == summary["case"]["drop_first"], name
    assert summary["complete"] and summary["guards_ok"] and not summary["physical_measurements"], name
    capacity = summary["case"]["capacity"]
    for ingress, (collected_us, result, flags, owned) in zip(arrivals, admissions, strict=True):
        assert ingress["virtual_us"] <= collected_us, name
        if result == -1 and owned == capacity and flags & 0x10:
            failed_while_full.append(dict(ingress_us=ingress["virtual_us"], collected_us=collected_us,
                                          sequence=ingress["sequence"],
                                          frame_sha256=sha256(bytes.fromhex(ingress["hex"])).hexdigest()))
    return dict(capacity=capacity, events=events, peak=summary["max_owned_fdu"],
                configured_hold_ticks=summary["case"].get("service_hold_ticks", 0),
                blocked_full_count=len(failed_while_full), first_blocked_full=next(iter(failed_while_full), None),
                admission_results=[dict(sequence=ingress["sequence"], ingress_us=ingress["virtual_us"],
                                        frame_sha256=sha256(bytes.fromhex(ingress["hex"])).hexdigest(),
                                        collected_us=collected_us, farm_result=result, flags=flags, owned=owned)
                                   for ingress, (collected_us, result, flags, owned)
                                   in zip(arrivals, admissions, strict=True)],
                summary_sha256=sha256(summary_bytes).hexdigest(), trace_sha256=sha256(trace_bytes).hexdigest(),
                p95_source_to_sink_virtual_us=summary["p95_quantized_source_to_sink_virtual_us"],
                max_source_to_sink_virtual_us=summary["max_quantized_source_to_sink_virtual_us"],
                sink=summary["exact_sink_count"], frames=summary["tc_instances"],
                retries=sum(count - 1 for count in sent.values()), source=summary["source"],
                clcw_wait=sum(wait for wait, _ in clcws), clcw_retry=sum(retry for _, retry in clcws),
                elapsed_us=summary["elapsed_virtual_us"], time_quantum_bound_us=summary["output_collection_quantum_max_us"])


def summarize(folder, service_screen=False):
    scenarios = {}
    slugs = ("hold-00", "hold-05", "hold-15") if service_screen else ("nominal", "first-loss")
    for slug in slugs:
        first, second = [run_data(folder, f"{slug}-n{n}") for n in (1, 2)]
        source = first.pop("source")
        assert source == second.pop("source"), slug
        source_sha256 = sha256(json.dumps(source, sort_keys=True).encode("utf-8")).hexdigest()
        delta = next(((a, b) for a, b in zip(first["events"], second["events"]) if a != b), None)
        different = delta is not None or len(first["events"]) != len(second["events"])
        if service_screen:
            hold = int(slug.split("-")[1])
            assert first["configured_hold_ticks"] == second["configured_hold_ticks"] == hold
        else:
            hold = 0
        first_full = first["first_blocked_full"]
        shared = None
        if first_full:
            shared = next((row for row in second["admission_results"]
                           if row["frame_sha256"] == first_full["frame_sha256"]), None)
        focus = min(a["t"] for a in delta) if delta else next(
            (event["t"] for event in first["events"] if event["kind"] in {"retry", "accept"}), 0)
        if first_full:
            focus = first_full["collected_us"]
        scenarios[slug] = dict(runs=[first, second], max=max(first["elapsed_us"], second["elapsed_us"]),
                               focus=focus, configured_hold_ticks=hold, events_differ=different,
                               source_sha256=source_sha256, corresponding_frame_two_slots=shared,
                               comparison=("Ä°lk farklÄ± olay zamana iÅŸaretlendi." if delta else
                                           "Ä°ki koÅŸuda gÃ¶sterilen olaylar ve zamanlarÄ± aynÄ±." if not different else
                                           "Ortak olay sÄ±rasÄ± aynÄ±. KoÅŸulardan birinde daha fazla olay var."))
    return scenarios


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--service-screen", action="store_true")
    args = parser.parse_args()
    print(json.dumps(summarize(args.folder, args.service_screen), ensure_ascii=True, indent=2))
