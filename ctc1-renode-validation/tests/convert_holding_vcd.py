"""Convert scalar logic-analyzer VCD into the COP-1 holding analyzer's event CSV."""

import argparse
from bisect import bisect_right
import csv
from io import StringIO
from math import isfinite
from pathlib import Path
import re

from run_timing import require


TIME_UNITS = {"s": 1, "ms": 1e-3, "us": 1e-6, "ns": 1e-9, "ps": 1e-12, "fs": 1e-15}


def read_vcd(source, names):
    header = []
    for line in source:
        header.append(line)
        if "$enddefinitions" in line:
            break
    declarations = "".join(header)
    require("$enddefinitions" in declarations, "Missing VCD enddefinitions")
    scale = re.search(r"\$timescale\s+(1|10|100)\s*(s|ms|us|ns|ps|fs)\s+\$end", declarations)
    require(scale is not None, "Unsupported VCD timescale")
    tick_seconds = int(scale[1]) * TIME_UNITS[scale[2]]
    selected = {}
    for width, identifier, name in re.findall(r"\$var\s+\S+\s+(\d+)\s+(\S+)\s+(\S+)[^$]*\$end", declarations):
        if name in names:
            require(width == "1" and name not in selected.values() and identifier not in selected,
                    f"VCD channel must be a unique scalar: {name}")
            selected[identifier] = name
    require(set(selected.values()) == set(names), "One or more requested VCD channels are missing")

    edges = {name: [] for name in names}
    tick = 0
    skip = False
    for line in source:
        for token in line.split():
            if token == "$end":
                skip = False
                continue
            if skip:
                continue
            if token.startswith("$"):
                require(token in {"$comment", "$dumpvars", "$dumpall"}, f"Unsupported VCD directive: {token}")
                skip = token == "$comment"
            elif token.startswith("#"):
                new_tick = int(token[1:])
                require(new_tick >= tick, "VCD timestamps decrease")
                tick = new_tick
            elif token[1:] in selected and token[0] in "01xXzZ":
                require(token[0] in "01", "Unknown level on a requested VCD channel")
                values = edges[selected[token[1:]]]
                level = int(token[0])
                if not values or level != values[-1][1]:
                    require(not values or tick > values[-1][0], "Multiple changes at one tick on a channel")
                    values.append((tick, level))

    require(all(values and values[0][0] == 0 for values in edges.values()),
            "Requested channels must all have a defined initial value at time zero")
    return tick_seconds, tick, edges


def decode_uart(edges, end_tick, bit_ticks, channel):
    require(edges[0][1] == edges[-1][1] == 1, f"{channel} must start and end idle high")
    times = [tick for tick, _ in edges]

    def level(tick):
        return edges[bisect_right(times, tick) - 1][1]

    ready = 0
    decoded = []
    for start, value in edges[1:]:
        if value != 0 or start < ready:
            continue
        stop = start + 9.5 * bit_ticks
        require(stop <= end_tick and level(start + .5 * bit_ticks) == 0 and level(stop) == 1,
                f"{channel} framing error or truncated byte at VCD tick {start}")
        byte = sum(level(start + (1.5 + bit) * bit_ticks) << bit for bit in range(8))
        decoded.append((stop if channel == "rx" else start, channel, f"{byte:02x}"))
        ready = stop
    require(decoded, f"No UART bytes on {channel}")
    return decoded


def convert(source, target, pin, rx, tx, rx_baud, tx_baud):
    require(len({pin, rx, tx}) == 3, "PD12, RX and TX must select different channels")
    require(all(isfinite(baud) and baud > 0 for baud in (rx_baud, tx_baud)), "Baud must be positive")
    tick_seconds, end, edges = read_vcd(source, (pin, rx, tx))
    require(edges[pin][0][1] == edges[pin][-1][1] == 0, "PD12 must start and end low")
    rows = [(tick, "pd12", str(level)) for tick, level in edges[pin]]
    for signal, name, baud in (("rx", rx, rx_baud), ("tx", tx, tx_baud)):
        rows.extend(decode_uart(edges[name], end, 1 / (baud * tick_seconds), signal))
    writer = csv.writer(target)
    writer.writerow(("time_s", "signal", "value"))
    writer.writerows((f"{tick * tick_seconds:.15g}", signal, value) for tick, signal, value in sorted(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_vcd", type=Path)
    parser.add_argument("output_csv", type=Path, help="New file. Existing files are preserved.")
    for flag in ("pd12", "rx", "tx"):
        parser.add_argument(f"--{flag}", required=True, help=f"VCD channel name for {flag}")
    parser.add_argument("--rx-baud", type=float, required=True)
    parser.add_argument("--tx-baud", type=float, required=True)
    args = parser.parse_args()
    try:
        # Complete decoding before creating the output so a failed decode leaves no partial file.
        output = StringIO(newline="")
        with args.input_vcd.open(encoding="utf-8-sig") as source:
            convert(source, output, args.pd12, args.rx, args.tx, args.rx_baud, args.tx_baud)
        with args.output_csv.open("x", encoding="utf-8", newline="") as target:
            target.write(output.getvalue())
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f"Invalid capture: {exc}\n")


if __name__ == "__main__":
    main()
