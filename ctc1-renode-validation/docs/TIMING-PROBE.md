# STM32F407 service timing probe

The timed build separates work that used to be visible only as a combined
serial transaction. It reports sample counts and the largest observed DWT
cycle delta for three phases.

- FARM step covers adapter checks, slot selection and the pinned NASA FARM call.
  It includes the adapter's per-step slot guard check.
- Commit step covers extraction and ownership release, including the same guard
  check. It ends before emitting the command record or queuing its reply.
- TM build and write covers frame assembly, its CRC and blocking UART writes
  through the last data-register write. It does not wait for the final stop bit.

These are instrumented elapsed core-cycle observations. They can include
interrupts, probe overhead and, for the TM path, waits on UART TXE.
They provide neither isolated NASA function costs nor a worst-case bound.
Counts and maxima reset when the fixture is initialized by operation 0.
UART hardware overrun, framing/noise/parity indications and ring high water are
separate counters since boot. Software ring drops and parser errors remain in
the ordinary status. A counter that cannot be enabled and observed advancing
produces null cycle fields.

Diagnostic operation 5 returns a CRC-protected record of type 0x84 followed
by the ordinary status. Its payload is twelve little-endian uint32 words.
In order these are version 1, nominal core clock, DWT availability, overrun
indications, other receive-error indications, ring high water, then count/max
pairs for FARM, commit and TM. The fixture reads these fields after paced
traffic, when RX interrupts should be quiet. Hardware errors count
indications and do not identify the exact number of lost bytes.

## Software controls

The [recorded Renode run](../evidence/timing-probe/renode.json) passed at
capacities 1, 2, 4 and 8. It checked 15 exact accepted and committed
command packets, five TM CRCs and payload/CLCW fields, phase call counts
and pool occupancy. Renode's cycle counter did not advance in this
profile. The result checks functionality only. The
[board build record](../evidence/timing-probe/board-build.json) records the
cross-compiled image hash. Arm GNU Toolchain 15.2.Rel1 built both profiles.
No STM32 board was flashed or measured for this record.

## Run

From `ctc1-renode-validation` with Python and Arm GNU Toolchain available:

```powershell
python tests/test_timing_wire.py
python tests/run_timing.py --renode
python tests/run_timing.py --board-image
```

The last command emits `work/stm32_farm.elf` inside the reported run
directory. It fetches the pinned NASA files without needing Renode. The
timed model uses the existing 72 MHz profile. The physical image requires a
hardware-reset STM32F407 with HSI and undivided AHB/APB1 at nominal 16 MHz.
Its SysTick reload follows that clock. The clock field is configuration, not a
frequency measurement. Flash the ELF with the board's normal programmer and
reset the device. Use USART2 PA2 (TX) and PA3 (RX) with a 3.3 V TTL UART adapter
and common ground. Connect TX to RX in each direction. Then run:

```powershell
python -m pip install pyserial==3.5
python tests/run_timing.py --port COMx
```

Replace COMx with the actual adapter port. UART is 115200, 8N1.
The script records CRC-checked UART replies and a summary in a fresh run.
It uses manual send/commit/TM requests to check measurement boundaries.
The timings therefore do not establish a buffer capacity or CLCW cadence
for a continuous link. A later coupled run needs controlled arrival bursts,
a recorded clock and interrupt load, and a comparison with the same host FOP
under alternative feedback intervals.

[ST RM0090 reference manual](https://www.st.com/resource/en/reference_manual/dm00031020-stm32f405415xx-stm32f407417xx-stm32f427437xx-and-stm32f429439xx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf)
