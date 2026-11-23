# COP-1 receiver buffer holding-time pilot

The timing fixture compares diagnostic transmission before and after releasing
an accepted telecommand's receiver buffer. This control checks whether the
test bench's own UART traffic would distort the physical holding-time
measurement used for later buffer studies.

Both modes form the same 152 diagnostic bytes in the same staging buffer.
Inline mode transmits the resulting records before automatic release.
Deferred mode releases the buffer before transmitting those records.
Each mode emits the same reply types in the same order. The fixture has one
FDU slot and receives one paced request at a time. It uses the existing
pinned NASA FARM and TCTF implementations.

PD12 rises after the adapter enqueues an accepted frame and falls after the
sink copy completes and empties the pool. With one slot the pulse represents
one accepted frame. With multiple slots it represents a nonempty pool.
The optional DWT count brackets the same transition inside the two GPIO
writes. The marker ends before CLCW Wait is cleared and measures a local
adapter interval. It does not include ground reception or feedback latency.

Diagnostic operation 6 returns record 0x85, followed by the ordinary status.
Its payload is eight little-endian 32-bit words in this order.

1. Format version (1)
2. DWT available flag
3. Ownership start count
4. Ownership end count
5. Last completed interval in cycles, or zero when the counter is unavailable
6. Diagnostic bytes staged since operation 0
7. Diagnostic staging overflow count
8. Automatic-mode setting

## Reproduce on Windows

From the validation folder with Python and Arm GNU Toolchain available:

```powershell
python tests/run_holding.py --renode
python tests/run_timing.py --board-image
```

The Renode runner checks both execution orders and the GPIO/UART register
write ordering. Each mode accepts eight distinct commands across sequence
wrap and rejects two duplicate frames without adding another commit.
It checks complete committed bytes, CLCW report values and all eight TM CRCs.
A separate manual control checks the GPIO level before and after release.
Logs and a JSON report go to a fresh ignored run folder. The register trace
checks event order. It does not measure elapsed time or establish the cost
of physical USART waits. [Renode tracing documentation](https://renode.readthedocs.io/en/latest/execution-tracing/execution-tracing.html)

## Recorded software result

Two fresh Renode runs produced identical reports. Each execution order
preserved the expected commands, CLCW values, telemetry CRCs and 1,520
staged diagnostic bytes per mode. The manual marker was high while the
slot was owned and low after commit. The DWT counter did not advance in
this Renode profile.

| Mode | UART data-register writes before release | Writes after release |
| --- | ---: | ---: |
| Inline | 152 | 72 |
| Deferred | 0 | 224 |

These counts are from one traced admission per mode. Both totals include
the 72-byte commit record. See the [paired Renode results](../evidence/holding-pilot/renode.json)
and the [cross-compiled board image record](../evidence/holding-pilot/board-build.json).

## Run the physical pilot

Flash the ELF created by the board-image command and hardware-reset the
STM32F407 to the nominal 16 MHz profile. Connect a 3.3 V UART adapter to USART2
with crossed TX/RX and common ground. On the Discovery board, confirm the
board revision and pin assignments in the ST manual. In the documented
P1 mapping PA2 (TX) is pin 14, PA3 (RX) is pin 13 and PD12 is pin 44.
Capture PD12 and the target TX line using a common logic-analyzer clock.
[STM32F407 Discovery manual, Table 7](https://www.st.com/resource/en/user_manual/um1472-stm32f4-discovery-stmicroelectronics.pdf)

```powershell
python -m pip install pyserial==3.5
python tests/run_holding.py --port COMx
```

Replace COMx with the connected adapter. UART uses 115200 baud, 8N1.
The runner executes both orders in one invocation and retains the raw
UART replies. Compare paired PD12 pulse widths and DWT counts, noting the
actual baud, timebase resolution and UART/ring errors. The first pulse in
each paired comparison is the manual control and should be excluded from
the paired timing results. A failed transport or functional check invalidates
the affected comparison.

### Pair the external capture with the board log

Start the capture after reset traffic has finished, while PD12 is low and
before starting the Python board runner. Stop after the runner finishes.
Export PD12 transitions and decoded target TX bytes on the **same analyzer
timebase**. Normalize both exports to one chronological CSV with header
`time_s,signal,value`. The first row gives the initial low PD12 level.
For `pd12` rows use `0` or `1`. For `tx` rows use one two-digit hexadecimal
byte and timestamp its start bit. Keep all UART records between the start
and end of the invocation. Capture TX in the same direction as seen by the
host.

Run the following with the actual logic-analyzer sample period in microseconds.
The paths below stand for the two files from **one** board run and its
corresponding capture.

```powershell
python tests/analyze_holding_capture.py holding.json board_uart.jsonl capture.csv --resolution-us 0.1
```

The analyzer matches the entire decoded TX stream byte for byte against the
hash-bound UART log, validates record CRCs and pairs each of the 34 complete
PD12 pulses with its expected command commit. It excludes one manual control
per execution order. It reports 16 paired differences, grouped by order, plus
the DWT reading when available. The DWT conversion uses the nominal 16 MHz
board configuration. Compare raw cycles separately if the real clock rate is
measured.

Near-coincident diagnostic and release edges are flagged as ambiguous at the
supplied sample resolution. The reported four-sample bound covers only
conservative timestamp quantization of the four edges in a paired difference.
Clock accuracy, channel skew and UART decoder uncertainty are separate.
The analyzer does not decide whether a timing difference is operationally
material. Retain the original logic-analyzer capture, the CSV and both runner
files so a different analysis can reproduce the measurement.

The synthetic alignment and rejection checks can run without a board.

```powershell
python tests/test_holding_capture.py
```

The planned hardware check is a prerequisite for a timed receiver model.
Physical holding times and any effect on buffer or feedback selection remain
unmeasured.
