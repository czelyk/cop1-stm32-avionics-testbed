"""Synthetic checks for capture alignment and rejection without a board."""

import binascii
import csv
from hashlib import sha256
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest

from analyze_holding_capture import analyze
from run_timing import frame, packet


class CaptureTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        self.capture = root / "capture.csv"
        self.log = root / "uart.jsonl"
        self.report = root / "holding.json"
        self.events = [(0.0, "pd12", "0")]
        self.log_lines = []
        self.next_time = 1000
        comparisons = []
        for order in ([1, 2], [2, 1]):
            self.add_case(packet(31), width=200, diagnostic_offset=20, tc_sequence=252)
            comparison = dict(mode_order=order, paired_protocol_outcomes_identical=True)
            for mode in order:
                records = []
                for uid in range(1, 9):
                    data = packet(uid)
                    tc_sequence = (251 + uid) % 256
                    self.add_case(data, width=900 if mode == 1 else 100,
                                  tc_sequence=tc_sequence,
                                  diagnostic_offset=20 if mode == 1 else 110)
                    records.append(dict(outcome=dict(command_uid=uid, tc_sequence=tc_sequence,
                                                     committed_hex=data.hex(),
                                                     result_hex="01", state_hex="02"),
                                        dwt_cycles=1200 if mode == 2 else None))
                comparison["inline" if mode == 1 else "deferred"] = dict(records=records)
            comparisons.append(comparison)
        self.log.write_text("\n".join(self.log_lines) + "\n", encoding="utf-8")
        self.report.write_text(json.dumps(dict(mode="board", comparisons=comparisons,
                                               uart_sha256=sha256(self.log.read_bytes()).hexdigest())),
                               encoding="utf-8")

    def add_uart(self, start, kind, seq, data):
        frame = struct.pack(">BBH", kind, seq, len(data)) + data
        wire = b"\x5a\xa5" + frame + struct.pack(">H", binascii.crc_hqx(frame, 0xffff))
        self.log_lines.append(json.dumps(dict(record_hex=wire.hex())))
        for index, byte in enumerate(wire):
            self.events.append(((start + 87 * index) / 1e6, "tx", f"{byte:02x}"))
        return start + 87 * len(wire)

    def add_case(self, data, width, diagnostic_offset, tc_sequence):
        request = frame(tc_sequence, data)
        body = struct.pack(">BBH", 1, 7, len(request)) + request
        wire = b"\xa5\x5a" + body + struct.pack(">H", binascii.crc_hqx(body, 0xffff))
        for index, byte in enumerate(wire):
            self.events.append(((self.next_time + index * 87) / 1e6, "rx", f"{byte:02x}"))
        rise = self.next_time + (len(wire) - 1) * 87 + 40
        self.events.extend([(rise / 1e6, "pd12", "1"), ((rise + width) / 1e6, "pd12", "0")])
        end = self.add_uart(rise + diagnostic_offset, 0x83, 7, b"\x01")
        end = self.add_uart(end, 0x80, 7, b"\x02")
        end = self.add_uart(max(end, rise + width + 10), 0x81, 0, data)
        self.next_time = end + 1000

    def run_capture(self):
        with self.capture.open("w", encoding="utf-8", newline="") as target:
            out = csv.writer(target)
            out.writerow(("time_s", "signal", "value"))
            out.writerows(sorted(self.events))
        return analyze(self.report, self.log, self.capture, resolution_us=1)

    def test_aligns_both_orders_and_excludes_manual_controls(self):
        data = self.run_capture()
        self.assertEqual(data["paired_delta_quantization_bound_us"], 4)
        for case in data["comparisons"]:
            self.assertAlmostEqual(case["manual_control_us"], 200)
            self.assertEqual(len(case["paired_inline_minus_deferred_us"]), 8)
            self.assertAlmostEqual(case["median_inline_minus_deferred_us"], 800)
            self.assertEqual(case["modes"]["deferred"][0]["dwt_nominal_us"], 75)
            self.assertIsNone(case["modes"]["inline"][0]["dwt_nominal_us"])
            self.assertAlmostEqual(case["modes"]["inline"][0]["rx_complete_to_gpio_us"], 40)

    def test_rejects_a_missing_pulse(self):
        first_rise = self.events.index(next(row for row in self.events if row[1:] == ("pd12", "1")))
        del self.events[first_rise:first_rise + 2]
        with self.assertRaisesRegex(RuntimeError, "34 complete"):
            self.run_capture()

    def test_rejects_a_different_uart_byte(self):
        index = next(i for i, (_, signal, _) in enumerate(self.events) if signal == "tx")
        stamp, signal, _ = self.events[index]
        self.events[index] = (stamp, signal, "00")
        with self.assertRaisesRegex(RuntimeError, "differs from the host log"):
            self.run_capture()

    def test_rejects_the_300_us_early_gpio_edge(self):
        edges = [i for i, event in enumerate(self.events) if event[1:] == ("pd12", "1")]
        index = edges[1]
        stamp, signal, value = self.events[index]
        self.events[index] = (stamp - 300e-6, signal, value)
        with self.assertRaisesRegex(RuntimeError, "before the RX request is complete"):
            self.run_capture()

    def test_rejects_a_corrupted_rx_request(self):
        index = next(i for i, (_, signal, _) in enumerate(self.events) if signal == "rx") + 2
        stamp, signal, _ = self.events[index]
        self.events[index] = (stamp, signal, "02")
        with self.assertRaisesRegex(RuntimeError, "Invalid RX CRC"):
            self.run_capture()

    def test_rejects_a_different_uart_session(self):
        with self.log.open("a", encoding="utf-8") as target:
            target.write("\n")
        with self.assertRaisesRegex(RuntimeError, "holding report hash"):
            self.run_capture()


if __name__ == "__main__":
    unittest.main()
