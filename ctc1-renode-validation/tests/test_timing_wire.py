"""Checks for the physical host transport without opening a serial port."""
from io import StringIO
import binascii
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from run_timing import Board


def record(kind, seq, payload):
    body = struct.pack('>BBH', kind, seq, len(payload)) + payload
    return b'\x5a\xa5' + body + struct.pack('>H', binascii.crc_hqx(body, 0xffff))


class MemorySerial:
    def __init__(self, wire):
        self.wire = wire
        self.sent = b''

    def read(self, length):
        take = min(length, 3)
        data, self.wire = self.wire[:take], self.wire[take:]
        return data

    def write(self, data):
        self.sent += data


class WireTests(unittest.TestCase):
    def test_fragmented_status_and_timing(self):
        status = struct.pack('<24I', *range(24))
        diagnostic = bytes(48)
        port = MemorySerial(record(0x80, 255, status) + record(0x84, 1, diagnostic) + record(0x80, 1, status))
        with patch.dict('sys.modules', serial=SimpleNamespace(Serial=lambda *args, **kwargs: port)):
            target = Board('fixture', StringIO())
        observed, records = target.request(5)
        self.assertEqual(observed, tuple(range(24)))
        self.assertEqual([r['kind'] for r in records], [0x80, 0x84, 0x80])
        self.assertEqual(port.sent[:6], b'\xa5\x5a\x05\x01\x00\x00')
        self.assertEqual(binascii.crc_hqx(port.sent[2:-2], 0xffff), int.from_bytes(port.sent[-2:], 'big'))

    def test_bad_reply_crc(self):
        wire = record(0x84, 1, bytes(48))
        port = MemorySerial(wire[:-1] + bytes([wire[-1] ^ 1]))
        with patch.dict('sys.modules', serial=SimpleNamespace(Serial=lambda *args, **kwargs: port)):
            target = Board('fixture', StringIO())
        with self.assertRaisesRegex(RuntimeError, 'CRC mismatch'):
            target.request(5)


if __name__ == '__main__':
    unittest.main()
