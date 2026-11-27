"""Pair externally captured GPIO pulses to CRC-checked STM32 UART traffic."""

import argparse
import binascii
import csv
from hashlib import sha256
import json
from math import isfinite
from statistics import median
from pathlib import Path

from run_timing import CLOCKS, frame, packet, require


def read_capture(path):
    pulses = []
    uart = {"rx": [], "tx": []}
    level = None
    previous = float("-inf")
    rise = None
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = csv.DictReader(source)
        require(rows.fieldnames == ["time_s", "signal", "value"], "Wrong capture CSV header")
        for row in rows:
            seconds = float(row["time_s"])
            require(isfinite(seconds) and seconds >= previous, f"Invalid time at row {rows.line_num}")
            previous = seconds
            if row["signal"] == "pd12":
                value = row["value"]
                require(value in ("0", "1") and value != level, "Expected initial low and PD12 transitions")
                if level is None:
                    require(value == "0" and not any(uart.values()), "Start the CSV at a low PD12 level before UART traffic")
                elif value == "1":
                    rise = seconds
                else:
                    require(rise < seconds, "Zero-width PD12 pulse")
                    pulses.append((rise, seconds))
                level = value
            else:
                signal = row["signal"]
                require(signal in uart and level is not None, f"Unexpected signal at row {rows.line_num}")
                channel = uart[signal]
                require(not channel or seconds > channel[-1][0], f"UART {signal} byte times must strictly increase")
                byte = bytes.fromhex(row["value"])
                require(len(byte) == 1, "Expected one hexadecimal byte per UART row")
                channel.append((seconds, byte[0]))
    require(level == "0" and all(uart.values()), "Capture must include RX and TX and end with PD12 low")
    return pulses, uart


def decode_requests(rx):
    raw = bytes(byte for _, byte in rx)
    requests = []
    offset = 0
    while offset < len(raw):
        header = raw[offset:offset + 6]
        require(len(header) == 6 and header[:2] == b"\xa5\x5a", f"Invalid RX header at byte {offset}")
        end = offset + 8 + int.from_bytes(header[4:6], "big")
        require(end <= len(raw), f"Incomplete RX request at byte {offset}")
        require(binascii.crc_hqx(raw[offset + 2:end - 2], 0xffff) == int.from_bytes(raw[end - 2:end], "big"),
                f"Invalid RX CRC at byte {offset}")
        # RX timestamps mark stop-bit samples, so the last byte bounds admission.
        requests.append((header[2], header[3], raw[offset + 6:end - 2], rx[end - 1][0]))
        offset = end
    return requests


def match_uart(path, uart, digest):
    raw = path.read_bytes()
    require(sha256(raw).hexdigest() == digest, "UART log does not match the holding report hash")
    captured = bytes(byte for _, byte in uart)
    records = []
    offset = 0
    for line in raw.splitlines():
        item = json.loads(line)
        wire = bytes.fromhex(item["record_hex"])
        require(len(wire) >= 8 and wire[:2] == b"\x5a\xa5"
                and int.from_bytes(wire[4:6], "big") == len(wire) - 8
                and binascii.crc_hqx(wire[2:-2], 0xffff) == int.from_bytes(wire[-2:], "big"),
                f"Invalid recorded UART frame at byte {offset}")
        end = offset + len(wire)
        require(captured[offset:end] == wire, f"Captured UART differs from the host log at record offset {offset}")
        records.append((wire[2], wire[3], wire[6:-2], uart[offset][0]))
        offset = end
    require(offset == len(captured), "Unexpected UART bytes after the host log")
    return records


def align(report, pulses, requests, records, resolution_s, rx_stop_error_s):
    rx_order_bound = resolution_s + rx_stop_error_s
    comparisons = report["comparisons"]
    require([case["mode_order"] for case in comparisons] == [[1, 2], [2, 1]],
            "Expected one comparison in each execution order")
    commits = [index for index, row in enumerate(records) if row[0] == 0x81]
    require(len(commits) == len(pulses) == 34, "Expected 34 commit records and 34 complete PD12 pulses")
    positions = iter(zip(commits, pulses, strict=True))
    previous_commit = float("-inf")

    def next_commit(expected):
        nonlocal previous_commit
        index, (rise, fall) = next(positions)
        kind, sequence, payload, tx_start = records[index]
        require((kind, sequence, payload) == (0x81, 0, expected), "Commit sequence or payload differs")
        require(previous_commit < rise and fall <= tx_start + resolution_s,
                "PD12 pulse is outside its commit interval")
        previous_commit = tx_start
        return index, rise, fall

    result = []
    for case in comparisons:
        require(case["paired_protocol_outcomes_identical"], "Firmware runner did not verify paired outcomes")
        _, rise, fall = next_commit(packet(31))
        manual = (fall - rise) * 1e6
        modes = {}
        for mode in case["mode_order"]:
            name = "inline" if mode == 1 else "deferred"
            outcomes = case[name]["records"]
            require(len(outcomes) == 8, "Expected eight accepted commands per mode")
            rows = []
            for uid, entry in enumerate(outcomes, start=1):
                outcome = entry["outcome"]
                require(outcome["command_uid"] == uid, "Unexpected command ID in the mode report")
                commit_payload = bytes.fromhex(outcome["committed_hex"])
                lower_bound = previous_commit
                index, rise, fall = next_commit(commit_payload)
                require(index >= 2, "Missing admission records before commit")
                diag, status = records[index - 2:index]
                require(diag[0] == 0x83 and status[0] == 0x80 and diag[1] == status[1]
                        and diag[2] == bytes.fromhex(outcome["result_hex"])
                        and status[2].startswith(bytes.fromhex(outcome["state_hex"])),
                        "Admission records before commit differ from the report")
                first_tx = diag[3]
                expected_tc = frame(outcome["tc_sequence"], commit_payload)
                matching = [end for op, sequence, payload, end in requests
                            if (op, sequence, payload) == (1, diag[1], expected_tc)
                            and lower_bound < end <= first_tx + rx_order_bound]
                require(len(matching) == 1, f"{name} command {uid} has no unique matching RX request")
                admission_delay = rise - matching[0]
                require(admission_delay >= -rx_order_bound,
                        f"{name} command {uid} PD12 rises before the RX request is complete")
                require(first_tx >= rise - resolution_s, "Admission UART starts before PD12 rises")
                separation = first_tx - fall
                ambiguous = abs(separation) <= resolution_s
                require(ambiguous or ((separation < 0) == (mode == 1)),
                        f"{name} command {uid} diagnostic starts on the wrong side of the release edge")
                cycles = entry["dwt_cycles"]
                rows.append(dict(command_uid=uid, gpio_us=(fall - rise) * 1e6,
                                 rx_complete_to_gpio_us=admission_delay * 1e6,
                                 rx_to_gpio_order_ambiguous=abs(admission_delay) <= rx_order_bound,
                                 first_diagnostic_tx_minus_release_us=separation * 1e6,
                                 diagnostic_order_ambiguous=ambiguous, dwt_cycles=cycles,
                                 dwt_nominal_us=cycles * 1e6 / CLOCKS["board"] if cycles is not None else None))
            modes[name] = rows
        deltas = [first["gpio_us"] - second["gpio_us"]
                  for first, second in zip(modes["inline"], modes["deferred"], strict=True)]
        result.append(dict(mode_order=case["mode_order"], manual_control_us=manual, modes=modes,
                           paired_inline_minus_deferred_us=deltas,
                           median_inline_minus_deferred_us=median(deltas)))
    return result


def analyze(summary, uart_log, capture, resolution_us, rx_stop_error_us=0):
    require(isfinite(resolution_us) and resolution_us > 0, "Capture resolution must be positive")
    require(isfinite(rx_stop_error_us) and rx_stop_error_us >= 0, "RX stop-bit error bound must be nonnegative")
    report = json.loads(summary.read_text(encoding="utf-8"))
    require(report["mode"] == "board", "Analyze a board run, not a Renode report")
    pulses, uart = read_capture(capture)
    requests = decode_requests(uart["rx"])
    records = match_uart(uart_log, uart["tx"], report["uart_sha256"])
    return dict(resolution_us=resolution_us, rx_stop_error_bound_us=rx_stop_error_us,
                rx_order_bound_us=resolution_us + rx_stop_error_us,
                paired_delta_quantization_bound_us=4 * resolution_us,
                comparisons=align(report, pulses, requests, records,
                                  resolution_us / 1e6, rx_stop_error_us / 1e6))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("holding_json", type=Path)
    parser.add_argument("board_uart_jsonl", type=Path)
    parser.add_argument("capture_csv", type=Path)
    parser.add_argument("--resolution-us", type=float, required=True, help="Logic analyzer sample period in microseconds")
    parser.add_argument("--rx-stop-error-us", type=float, default=0,
                        help="Additional RX stop-bit timestamp error bound, excluding sample quantization")
    args = parser.parse_args()
    try:
        result = analyze(args.holding_json, args.board_uart_jsonl, args.capture_csv, args.resolution_us, args.rx_stop_error_us)
    except (RuntimeError, ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"Invalid capture: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
