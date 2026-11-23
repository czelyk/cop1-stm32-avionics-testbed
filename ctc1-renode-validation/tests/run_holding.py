"""Compare COP-1 ownership semantics with inline and deferred UART diagnostics."""

import argparse
from hashlib import sha256
from pathlib import Path
import json
import re
import struct
import time

from run_timing import Board, build_timing, frame, new_run, packet, require, timing_renode, verify_tm


GPIOD_ODR = 0x40020C14
PD12 = 1 << 12


def exchange(target, op, kinds, data=b""):
    seq = target.send(op, data)
    records = []
    if isinstance(target, Board):
        deadline = time.monotonic() + 5
        records = [target.receive(deadline) for _ in kinds]
    else:
        for _ in range(30):
            records.extend(target.run(1_000))
            if len(records) >= len(kinds):
                break
    require([row["kind"] for row in records] == kinds, f"op {op} sequence {seq}: unexpected reply types")
    require(all(row["sequence"] == (0 if row["kind"] in (0x81, 0x82) else seq) for row in records),
          f"op {op}: mismatched sequence")
    return [bytes.fromhex(row["payload_hex"]) for row in records]


def reset(target, initial, mode):
    config = struct.pack(">BBBH", 1, initial, mode, 60_000)
    [status] = exchange(target, 0, [0x80], config)
    fields = struct.unpack("<24I", status)
    require(fields[3] == 0 and fields[9] == 1 and fields[20] == mode, "Wrong initial fixture state")


def read_hold(target):
    raw, status = exchange(target, 6, [0x85, 0x80])
    fields = struct.unpack("<8I", raw)
    require(fields[0] == 1 and fields[1] in (0, 1) and fields[6] == 0, "Invalid hold probe response")
    return fields, struct.unpack("<24I", status)


def read_uart_errors(target):
    raw, _ = exchange(target, 5, [0x84, 0x80])
    fields = struct.unpack("<12I", raw)
    clock = 16_000_000 if isinstance(target, Board) else 72_000_000
    require(fields[:2] == (1, clock), "Unexpected fixture timing profile")
    return fields[3:5]


def read_pin(target):
    reply = target.cmd(f"sysbus ReadDoubleWord {GPIOD_ODR:#x}")
    match = re.search(r"(?im)^\s*(0x[0-9a-f]+)\s*$", reply)
    require(match is not None, f"GPIO readback unavailable: {reply!r}")
    return bool(int(match.group(1), 16) & PD12)


def manual_control(target):
    reset(target, 252, 0)
    initial, _ = read_hold(target)
    packet_bytes = packet(31)
    accepted, _ = exchange(target, 1, [0x83, 0x80], frame(252, packet_bytes))
    require(struct.unpack("<10I", accepted)[3] == 1, "Manual control failed to accept TC")
    occupied, _ = read_hold(target)
    pin_high = read_pin(target) if not isinstance(target, Board) else None
    committed, _ = exchange(target, 2, [0x81, 0x80])
    empty, _ = read_hold(target)
    pin_low = not read_pin(target) if not isinstance(target, Board) else None
    require(initial[2:4] == (0, 0) and occupied[2:4] == (1, 0) and empty[2:4] == (1, 1),
          "Ownership marker transitions do not match acceptance and commit")
    require(committed == packet_bytes and pin_high is not False and pin_low is not False,
          "Manual commit or GPIO readback mismatch")
    [tm, _] = exchange(target, 4, [0x82, 0x80])
    verify_tm(tm, [packet_bytes], 253)
    return dict(marker_counts=[initial[2:4], occupied[2:4], empty[2:4]], gpio_high_then_low=[pin_high, pin_low])


def paired_case(target, mode, repeats):
    initial = 252
    reset(target, initial, mode)
    initial_hold, initial_status = read_hold(target)
    initial_errors = read_uart_errors(target)
    expected_starts = 0
    attempts = 0
    results = []
    for index in range(repeats):
        seq = (initial + index) % 256
        tc = packet(index + 1)
        payload = frame(seq, tc)
        result, status, committed = exchange(target, 1, [0x83, 0x80, 0x81], payload)
        attempts += 1
        expected_starts += 1
        result_fields = struct.unpack("<10I", result)
        status_fields = struct.unpack("<24I", status)
        require(result_fields[0] == len(tc) and result_fields[3] == status_fields[3] == 1
              and committed == tc, "Incorrect admission, staged status or commit")
        [tm, _] = exchange(target, 4, [0x82, 0x80])
        verify_tm(tm, [tc], (seq + 1) % 256)
        hold, current_status = read_hold(target)
        require(hold[2:4] == (expected_starts, expected_starts) and current_status[3] == 0,
              "Automatic release did not end the ownership interval")
        require(hold[5] == 152 * attempts, "Wrong diagnostic staging volume")
        require(not hold[1] or hold[4] > 0, "Working DWT reported a zero duration")
        outcome = dict(tc_sequence=seq, report=tm[277], command_uid=index + 1,
                       result_hex=result.hex(), state_hex=status[:40].hex(),
                       committed_hex=committed.hex(), tm_sha256=sha256(tm).hexdigest())
        record = dict(outcome=outcome, dwt_cycles=hold[4] if hold[1] else None)
        if index in (1, 4):
            duplicate, status = exchange(target, 1, [0x83, 0x80], payload)
            attempts += 1
            hold, current_status = read_hold(target)
            require(hold[2:4] == (expected_starts, expected_starts) and current_status[3] == 0,
                  "Duplicate TC changed ownership or reached the sink")
            require(hold[5] == 152 * attempts, "Wrong duplicate diagnostic staging volume")
            record["outcome"]["duplicate"] = [duplicate.hex(), status[:40].hex()]
        results.append(record)
    end, final_status = read_hold(target)
    for index in (13, 14, 18):
        require(final_status[index] == initial_status[index], f"Unexpected increase in status field {index}")
    require(final_status[5] == repeats and end[2] == end[3] == repeats, "Incorrect final ownership or commit count")
    final_errors = read_uart_errors(target)
    require(final_errors == initial_errors, "UART errors or overruns increased")
    return dict(mode=mode, dwt_available=bool(initial_hold[1]), tc_attempts=attempts,
                exact_unique_commits=repeats, diagnostic_bytes_staged=end[5],
                uart_overruns_and_errors=final_errors, records=results)


ACCESS = re.compile(
    r"(gpioPortD|usart2): \[cpu: [^\]]+\] Write(?:UInt32|DoubleWord) "
    r"to (0x[0-9A-Fa-f]+).*?value (0x[0-9A-Fa-f]+)"
)


def count_writes(text):
    windows = []
    current = None
    for match in ACCESS.finditer(text):
        peripheral, offset, value = match.groups()
        register = int(offset, 16)
        written = int(value, 16)
        if peripheral == "gpioPortD" and register == 0x18:
            if written == 1 << 12:
                require(current is None or current["closed"], "Duplicate start before release")
                current = dict(before_release=0, after_release=0, closed=False)
                windows.append(current)
            elif written == 1 << 28:
                require(current is not None and not current["closed"], "Release without start")
                current["closed"] = True
        if peripheral == "usart2" and register == 4:
            require(current is not None, "Unexpected UART TX before admission")
            current["after_release" if current["closed"] else "before_release"] += 1
    require(len(windows) == 2 and all(w["closed"] for w in windows), "Missing traced ownership intervals")
    return windows


def compare(target, mode_order):
    manual = manual_control(target)
    cases = {mode: paired_case(target, mode, 8) for mode in mode_order}
    inline, deferred = cases[1], cases[2]
    require([r["outcome"] for r in inline["records"]] == [r["outcome"] for r in deferred["records"]],
            "Moving diagnostics changed protocol-visible semantics")
    return dict(manual=manual, mode_order=mode_order, inline=inline, deferred=deferred,
                paired_protocol_outcomes_identical=True)


def trace_order(target):
    peripherals = ("gpioPortD", "usart2")
    for mode in (1, 2):
        reset(target, 252, mode)
        for name in peripherals:
            target.cmd(f"sysbus LogPeripheralAccess sysbus.{name} true")
        payload = packet(1)
        _, _, committed = exchange(target, 1, [0x83, 0x80, 0x81], frame(252, payload))
        require(committed == payload, "Traced command commit changed")
        for name in peripherals:
            target.cmd(f"sysbus LogPeripheralAccess sysbus.{name} false")
    return Path(target.log.name)


def verify_trace(log):
    observed = count_writes(log.read_text(encoding="utf-8"))
    expected = [dict(before_release=152, after_release=72, closed=True),
                dict(before_release=0, after_release=224, closed=True)]
    require(observed == expected, f"Unexpected ownership and UART ordering: {observed}")
    return dict(inline=observed[0], deferred=observed[1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--renode", action="store_true")
    mode.add_argument("--port", help="STM32 fixture serial port after flashing the 16 MHz timing image")
    args = parser.parse_args()
    run, work = new_run("holding")
    if args.renode:
        digest = build_timing(work, "renode-timing")
        with timing_renode(work, "holding_pilot") as target:
            comparisons = [compare(target, order) for order in ((1, 2), (2, 1))]
            trace_log = trace_order(target)
        ordering = verify_trace(trace_log)
        result = dict(mode="renode", physical_measurements=False, elf_sha256=digest,
                      comparisons=comparisons, register_write_order=ordering)
    else:
        uart_log = run / "board_uart.jsonl"
        with uart_log.open("x", encoding="utf-8") as log:
            target = Board(args.port, log)
            try:
                # Consume a possible startup status while waiting for the first explicit status.
                target.request(3)
                comparisons = [compare(target, order) for order in ((1, 2), (2, 1))]
            finally:
                target.close()
        result = dict(mode="board", comparisons=comparisons,
                      uart_sha256=sha256(uart_log.read_bytes()).hexdigest())
    (run / "holding.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(run / "holding.json")


if __name__ == "__main__":
    main()
