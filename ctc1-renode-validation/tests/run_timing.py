"""Build the timing fixture and verify its diagnostic UART records."""
import argparse
import binascii
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from bootstrap import bootstrap
from lab import execute, find_tool, new_run

CLOCKS = {'renode': 72_000_000, 'board': 16_000_000}
PHASES = ('farm_step', 'commit_step', 'tm_build_and_write')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def packet(uid):
    length = 64
    return struct.pack('>HHHQ', 0x1042, 0xc000, length - 7, uid) + bytes([uid & 255]) * (length - 14)


def frame(sequence, payload):
    n = len(payload) + 4
    return bytes([0, 42, 4 | (n >> 8), n & 255, sequence]) + payload


def unique_payload(records, kind):
    payloads = [bytes.fromhex(record['payload_hex']) for record in records if record['kind'] == kind]
    require(len(payloads) == 1, f'Expected one UART record of kind {kind:#x}, got {len(payloads)}')
    return payloads[0]


def timing(target, mode):
    status, records = target.request(5)
    fields = struct.unpack('<12I', unique_payload(records, 0x84))
    version, core_hz, ready, overruns, errors, rx_peak = fields[:6]
    require(version == 1 and core_hz == CLOCKS[mode] and ready in (0, 1), 'Unexpected timing profile')
    phases = {phase: dict(calls=fields[6 + 2 * i],
                          max_cycles=fields[7 + 2 * i] if ready else None)
              for i, phase in enumerate(PHASES)}
    return dict(counter_available=bool(ready), configured_core_hz=core_hz, uart_overruns=overruns,
                uart_errors=errors, rx_ring_peak_since_boot=rx_peak, phases=phases,
                ring_drops=status[13], protocol_errors=status[14], reply_errors=status[18],
                pool_peak=status[16])


def verify_tm(raw, packets, report):
    require(len(raw) == 280, 'Unexpected TM length')
    require(binascii.crc_hqx(raw[:-2], 0xffff) == int.from_bytes(raw[-2:], 'big'), 'TM CRC mismatch')
    payload = b''.join(bytes([data[0] & ~0x10]) + data[1:] for data in packets)
    require(raw[6:6 + len(payload)] == payload and raw[277] == report, 'TM payload/CLCW mismatch')


def measure(target, mode):
    results = []
    for capacity in (1, 2, 4, 8):
        target.request(0, bytes([capacity, 0, 0, 0, 100]))
        start = timing(target, mode)
        for name in PHASES:
            require(start['phases'][name]['calls'] == 0, 'Phase counter did not reset')
        packets = [packet(capacity * 256 + index) for index in range(capacity)]
        for index, data in enumerate(packets):
            state, records = target.request(1, frame(index, data))
            result = struct.unpack('<10I', unique_payload(records, 0x83))
            require(result[0] == len(data) and state[3] == index + 1, 'FARM acceptance mismatch')
        for index, data in enumerate(packets):
            state, records = target.request(2)
            require(state[3] == capacity - index - 1 and unique_payload(records, 0x81) == data,
                    'Commit record or ownership mismatch')
        tm_count = 0
        for offset in range(0, capacity, 4):
            _, records = target.request(4)
            verify_tm(unique_payload(records, 0x82), packets[offset:offset + 4], capacity)
            tm_count += 1
        end = timing(target, mode)
        require(end['pool_peak'] == capacity, 'Unexpected FDU occupancy')
        for phase, calls in zip(PHASES, (capacity, capacity, tm_count), strict=True):
            require(end['phases'][phase]['calls'] == calls, f'Unexpected {phase} call count')
            if end['counter_available']:
                require(end['phases'][phase]['max_cycles'] > 0, f'Cycle counter did not advance for {phase}')
        for field in ('uart_overruns', 'uart_errors', 'ring_drops', 'protocol_errors', 'reply_errors'):
            require(start[field] == end[field], f'{field} increased during paced bench, capacity {capacity}')
        require(0 < end['rx_ring_peak_since_boot'] < 2048, 'RX ring high-water mark out of range')
        results.append(dict(capacity=capacity, exact_commands=capacity, exact_tm_frames=tm_count, **end))
    return results


class Board:
    def __init__(self, port, log):
        import serial
        self.uart = serial.Serial(port, 115200, timeout=0.15, write_timeout=1)
        self.sequence = 0
        self.log = log

    def read_exact(self, length, deadline):
        data = bytearray()
        while len(data) < length:
            if time.monotonic() >= deadline:
                raise TimeoutError('Incomplete UART reply; reset the board and check wiring/baud')
            data.extend(self.uart.read(length - len(data)))
        return bytes(data)

    def request(self, op, data=b''):
        self.sequence = (self.sequence + 1) & 255
        payload = struct.pack('>BBH', op, self.sequence, len(data)) + data
        wire = b'\xa5\x5a' + payload + struct.pack('>H', binascii.crc_hqx(payload, 0xffff))
        self.uart.write(wire)
        deadline = time.monotonic() + 5
        records = []
        while True:
            header = self.read_exact(6, deadline)
            require(header[:2] == b'\x5a\xa5', 'UART record marker mismatch; reset the board')
            kind, sequence, size = struct.unpack('>BBH', header[2:])
            require(size <= 280, 'UART record is longer than the fixture allows')
            tail = self.read_exact(size + 2, deadline)
            require(binascii.crc_hqx(header[2:] + tail[:-2], 0xffff) == int.from_bytes(tail[-2:], 'big'),
                    'UART record CRC mismatch')
            item = dict(kind=kind, sequence=sequence, payload_hex=tail[:-2].hex(), record_hex=(header + tail).hex())
            self.log.write(json.dumps(item) + '\n')
            self.log.flush()
            records.append(item)
            if kind == 0x80 and sequence == self.sequence:
                return struct.unpack('<24I', tail[:-2]), records

    def close(self):
        self.uart.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--renode', action='store_true')
    mode.add_argument('--board-image', action='store_true')
    mode.add_argument('--port', help='explicit serial port of a flashed 16 MHz timing fixture')
    args = parser.parse_args()
    run, work = new_run('timing')
    if args.port:
        with (run / 'board_uart.jsonl').open('x', encoding='utf-8') as log:
            board = Board(args.port, log)
            try:
                cases = measure(board, 'board')
            finally:
                board.close()
        record = dict(mode='board', board_capture=True, cycle_counter_available=all(
            case['counter_available'] for case in cases), cases=cases)
    else:
        env = dict(os.environ, ARM_GCC=str(find_tool('arm-none-eabi-gcc', 'ARM_GCC')),
                   CTC_NASA_DIR=str(bootstrap('nasa') / 'nasa'))
        profile = 'renode-timing' if args.renode else 'board-timing'
        execute([sys.executable, work / 'build_firmware.py', '--profile', profile], work, 'timing-build.log', env)
        elf = work / 'stm32_farm.elf'
        record = dict(mode=profile, board_capture=False, elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
                      configured_core_hz=CLOCKS['renode' if args.renode else 'board'])
        if args.renode:
            if 'RENODE_HOME' not in os.environ:
                os.environ['RENODE_HOME'] = str(bootstrap('renode') / 'renode/renode_1.17.0-portable')
            sys.path.insert(0, str(work))
            from renode_driver import Renode
            renode = Renode('timing_probe')
            try:
                record['cases'] = measure(renode, 'renode')
            finally:
                renode.close()
    (run / 'timing.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(record, run_directory=str(run)), indent=2))


if __name__ == '__main__':
    main()
