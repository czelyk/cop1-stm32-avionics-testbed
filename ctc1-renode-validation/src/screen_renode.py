"""Manual ownership/recovery controls on real emulated STM32 UART firmware."""
from pathlib import Path
import json, struct
from renode_driver import Renode, ROOT

def packet(uid, length=64):
    return struct.pack('>HHHQ', 0x1042, 0xc000, length - 7, uid) + bytes([uid & 255]) * (length - 14)
def frame(sequence, payload):
    n = len(payload) + 5 - 1
    return bytes([0, 42, 4 | (n >> 8), n & 255, sequence & 255]) + payload
def farm_result(records):
    values = struct.unpack('<10I', bytes.fromhex([r for r in records if r['kind'] == 0x83][-1]['payload_hex']))
    signed = values[0] - 2**32 if values[0] >= 2**31 else values[0]
    return signed, values

results = []
r = Renode('ownership_screen')
try:
    for capacity in [1, 2, 4, 8]:
        state, _ = r.request(0, bytes([capacity, 255, 0]) + struct.pack('>H', 100))
        assert state[1] == 255 and state[3] == state[5] == 0 and state[4] == 1
        expected = {}
        for index in range(capacity):
            data = packet((capacity << 32) | index)
            expected[data[6:14].hex()] = data.hex()
            state, records = r.request(1, frame(255 + index, data))
            ret, f = farm_result(records)
            assert ret == 64 and f[3] == index + 1 and f[1] == (256 + index) % 256
        blocked = packet((capacity << 32) | capacity)
        state, records = r.request(1, frame(255 + capacity, blocked))
        ret, f = farm_result(records)
        assert ret == -1 and f[2] & 0x18 == 0x18 and f[3] == capacity
        executed = {}
        state, records = r.request(2)
        assert state[2] & 0x10 == 0 and state[3] == capacity - 1
        for item in records:
            if item['kind'] == 0x81:
                data = bytes.fromhex(item['payload_hex']); executed[data[6:14].hex()] = data.hex()
        state, records = r.request(1, frame(255 + capacity, blocked))
        ret, f = farm_result(records)
        assert ret == 64 and f[1] == (256 + capacity) % 256 and f[2] & 0x18 == 0
        expected[blocked[6:14].hex()] = blocked.hex()
        # Repeating the same frame must never add another admitted/executed UID.
        state, records = r.request(1, frame(255 + capacity, blocked))
        ret, f = farm_result(records)
        assert ret == -3 and f[3] == capacity
        while state[3]:
            state, records = r.request(2)
            for item in records:
                if item['kind'] == 0x81:
                    data = bytes.fromhex(item['payload_hex']); uid = data[6:14].hex()
                    assert uid not in executed; executed[uid] = data.hex()
        assert executed == expected and state[5] == capacity + 1
        bad = bytearray(frame((256 + capacity) % 256, packet(0x999)))
        bad[3] ^= 1
        state, records = r.request(1, bytes(bad))
        ret, f = farm_result(records)
        assert ret == -10 and state[4] == 1 and state[3] == 0
        assert state[13] == state[14] == state[18] == 0
        results.append({'capacity': capacity, 'exact_unique_executions': len(executed),
                        'wait_release_retry_duplicate_wrap_invalid_length_guards': 'passed',
                        'uart_rx_interrupts_cumulative': state[11], 'systick_ms': state[10]})
    payload = {'kind': 'Renode STM32F4 UART/NVIC firmware controls; no physical timing claim',
               'cases': results, 'total_exact_unique_executions': sum(x['exact_unique_executions'] for x in results),
               'physical_measurements': False}
    with (ROOT / 'ownership_screen_result.json').open('x') as out: json.dump(payload, out, indent=2)
    print(json.dumps(payload))
finally:
    r.close()
