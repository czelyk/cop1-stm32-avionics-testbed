# Receive-slot pressure with a delayed consumer

The [automatic-release baseline](CAPACITY-PAIR.md) never used the second
receive slot. This experiment asked whether controlled overlap in that same
closed loop changes receiver admissions and the native Yamcs sender's
response. The prespecified comparisons for this probe were the same offered
commands at both capacities, a zero-delay control, direct evidence of a
full-pool rejection at the smaller capacity, and successful admission of
the corresponding frame at the larger capacity.

## Setup

An opt-in Renode build delays the release of the oldest FDU by 0, 5, or
15 firmware SysTick increments from the start of its service. Each new
FIFO head starts its own interval. The profile configures a nominal
one-millisecond guest tick. Output collection uses virtual time in
steps up to 5 ms. These delays model ownership in a serialized consumer.
There is no calibrated workload, physical STM32 timing, radio loss, or
RTOS scheduling in this test. Each case uses the same build and verifies
the configured delay before traffic starts.

Each matched pair offers the same 24 commands from seed 67 at a modeled
256 kbit/s decoded-frame serialization rate. The emulated processor is
configured for 100 MIPS. The feedback timer is set to 100 ms, with early
telemetry when the queued reply data reaches 261 bytes. Every case has
fresh Renode 1.17.0 and Yamcs peer processes. The second set repeats the
comparisons with the two-slot case first to check order sensitivity.
Yamcs and NASA FARM revisions are in the
[third-party notices](../THIRD_PARTY_NOTICES.md). The firmware ELF SHA-256
in both sets was
`dd72ce1aaf230d99496b54cc7a365fc20867abab87bae9e76b7c4b46d7e5c84f`.

## Measurements

Cells with a slash show one slot first and two slots second. The table
values were identical in both run orders.

| Guest hold (ticks) | Exact replies | Peak occupied slots | Full-pool rejections | TC transmissions | Byte-identical repeats | Worst virtual source-to-sink time (ms) |
| ---: | --- | --- | --- | --- | --- | --- |
| 0 | 24/24 each | 1 / 1 | 0 / 0 | 14 / 14 | 0 / 0 | 301.186 / 301.186 |
| 5 | 24/24 each | 1 / 1 | 0 / 0 | 14 / 14 | 0 / 0 | 306.186 / 306.186 |
| 15 | 24/24 each | 1 / 2 | 2 / 0 | 17 / 14 | 4 / 0 | 410.810 / 316.583 |

The first admission matched in both capacities. The second offered frame
had sequence 0 and identical bytes, with host injection logged at 3.037 ms
in every 15-tick run. The collected FARM result (at 21.226 ms) showed
`-1`, a one-slot pool at capacity, and local WAIT and RETRANSMIT flags
(`0x18`). The two-slot FARM accepted a 14-byte FDU and occupied both
slots. The reported host injection and output collection markers bound
when the guest response was observed.

No CLCW received by the sender carried WAIT in any of the 12 runs.
At 15 ticks, two received CLCWs carried RETRANSMIT with one slot and
zero with two. A byte-identical repeat is each transmission after the
first instance of the same exact frame. The one-slot run sent three more
frames in total and contained four repeats. These are separate counts
because the subsequent stream can be packed differently after feedback.

At 15 ticks the worst command time was 94.227 ms shorter with two slots
in both run orders. The single-slot p95 was 390.886 or 395.886 ms, and
the two-slot p95 was 311.065 ms. The 5 ms shift across run orders is at
the output collection scale. All delays are virtual. The admission
witness and retransmission counts are the primary evidence.

## Interpretation

This replay demonstrated a capacity effect once the first FDU stayed
owned during the next admission. The tested 0- and 5-tick settings
showed no difference in admission or retransmission counts. The study
used one offered command sequence, one link profile and three synthetic
hold values. A precise threshold, frequency of such overlap in a real
command path, and a deployable slot-sizing decision remain unresolved.
A decision-changing follow-up would measure or otherwise justify a
service-time range for a representative command consumer, then replay
that range against a separate offered command trace with feedback
settings fixed before running.

## Reproduce

Use the Windows dependencies in the README and prepare the pinned Yamcs
classpath. Each execution prints its own run directory.

```powershell
python tools/prepare_yamcs.py
python tests/run_capacity_pair.py --service-screen
python tests/run_capacity_pair.py --service-screen --reverse
python tests/summarize_capacity_pair.py RUN_DIRECTORY/work/capacity-pair --service-screen
```

[Raw case outputs](../evidence/capacity-service/raw-runs.zip) contain the
unchanged JSON and JSONL files from the two executions. The summary
script can also read either extracted order directory.
[One slot first](../evidence/capacity-service/one-first.json) and
[two slots first](../evidence/capacity-service/two-first.json) give the
matched admissions, event times, and individual raw-file hashes.
