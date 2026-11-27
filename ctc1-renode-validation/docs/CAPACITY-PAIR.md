# One versus two receive slots in Renode

The existing Renode STM32F4 fixture and the pinned NASA FARM operated in
closed loop with a native Yamcs peer at revision
`ee4c33f1650f9fae84d9a932bea4d57d6c9b2bbb`. Each matched pair received the
same 24 offered commands generated with seed 67. The model used
256 kbit/s for decoded TC frame serialization. Capacities were one and two
FDU slots, with independent emulator and peer processes for every run.

Both capacities ran once with the link intact and once with the first TC
frame discarded. The complete experiment was repeated with capacity two
first. The configured feedback timer was 100 ms throughout. It was not a
fixed CLCW cadence because the firmware also emits telemetry early when
261 bytes of replies are queued.

## Results

| Scenario | Slots | Exact replies | TC transmissions | Byte-identical repeats | Peak occupied slots | Worst virtual source-to-sink time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Intact | 1 | 24/24 | 14 | 0 | 1 | 301.186 ms |
| Intact | 2 | 24/24 | 14 | 0 | 1 | 301.186 ms |
| First TC frame erased | 1 | 24/24 | 16 | 4 | 1 | 434.244 ms |
| First TC frame erased | 2 | 24/24 | 16 | 4 | 1 | 434.244 ms |

All table values matched in the reverse-order repeat. No CLCW received by
the FOP indicated WAIT. One received CLCW indicated RETRANSMIT per loss run.
Each loss run logged three FARM results without a successful admission.
The count of repeats is the number of TC transmissions beyond the first
instance of each exact frame.

In the first intact pair, an identical CLCW was collected 5 ms apart while
the p95 source-to-sink time was equal. In the reverse-order intact pair,
the one-slot p95 was 291.929 ms and the two-slot p95 was 286.929 ms.
The host advances and collects emulator output in steps up to 5 ms.
This result does not resolve a repeatable capacity advantage at that scale.

The second slot never filled. This is a closed-loop functional comparison
under automatic release. It does not test a workload with overlapping
accepted frames or validate physical STM32 timing. The first-frame loss
control exercised retransmission. A capacity stress test would need to show
that a new admission is attempted while the first slot remains occupied
under otherwise matched conditions.

[First-order numeric trace summary](../evidence/capacity-pair/one-first.json) ·
[Reverse-order numeric trace summary](../evidence/capacity-pair/two-first.json)

## Reproduce

Use the Windows dependencies in the repository README and prepare the
pinned Yamcs classpath before running. A short checkout path can avoid
Windows command-line limits during the protobuf build.

```powershell
python tools/prepare_yamcs.py
python tests/run_capacity_pair.py
python tests/run_capacity_pair.py --reverse
python tests/summarize_capacity_pair.py RUN_DIRECTORY/work/capacity-pair
```

Each run prints its own run directory. Raw traces and per-case outcomes are
written there. The published summaries contain the selected events and SHA-256
identities of the original run files.
