# When can extra FDU holding change the one-slot decision?

The screen uses the 16 one-slot cases from the original 64-case CTC1
software validation. It holds successful FARM admission times fixed and
adds the same integer delay to each recorded commit/release time. It asks
when two recorded successful admissions first overlap. A release at the
same timestamp as an admission is processed first. A peak of two
means one slot cannot preserve that exact schedule.

The script verifies original admission/release pairs and recomputes peak
occupancy both at the last one-slot point and one microsecond later. FARM
results that did not admit a frame are counted separately. These include
some arrivals while the slot was already occupied. The screen therefore
covers the timing of recorded successful admissions and cannot establish
that every offered frame would be immediately admitted.

## Executed result

| Assumed decoded TC rate | Archived cases | First uniform extra delay that creates overlap |
| --- | ---: | --- |
| 4 kbit/s | 8 | 37,973 µs in four cases and 137,934 µs in four |
| 256 kbit/s | 8 | 486 µs in two cases, 524 µs in four and 567 µs in two |

Repeated cases share experiment settings and sometimes the same timings.
They do not represent independent mission observations. The exact
witness admission and release timestamps, checked peaks and input hashes
are in the [numeric result](../evidence/holding-sensitivity/summary.json).

## What the result means for the pilot

A physical delay would have to be used in a model that matches the
measurement boundary and workload. This screen only gives a scale to
compare against. For the recorded 4 kbit/s successful-admission schedules,
a uniform extra hold below 37,973 µs leaves the one-slot peak unchanged.
Some 256 kbit/s schedules are more sensitive. The existing 115,200 baud
fixture cannot reproduce those high-rate arrivals, so it cannot test that
case as configured.

The pilot measures what the fixture's diagnostics do to the observed
interval. It does not supply a physical correction to the archived
schedule until the timing bases and workload are validated. The screen
does not rerun the peer, replan arrivals or measure retransmissions,
queuing, CLCW feedback, or actual physical holding time. A forced
overlap is a trigger for a closed-loop test of the two capacities when
the transport is qualified. It is not an allocation recommendation.

## Reproduce from the original local archive

```powershell
python tests/screen_holding_sensitivity.py ORIGINAL_VALIDATION_TRACE_DIRECTORY --check
```

Use the local validation trace directory from the original 64-case CTC1
campaign. The public repository contains the numeric summaries and hashes.
The source JSONL and command payload bytes are outside this public package.
