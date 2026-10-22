"""Pinned native Yamcs FOP -> emulated STM32 UART/NASA FARM -> MCU TM -> FOP.

This is functional peripheral emulation. UART socket messages arrive in batches;
decoded frame/link spacing is an external reference assumption. Collection times
are quantized by the declared polling bound, never physical service measurements.
"""
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import binascii, hashlib, heapq, json, math, queue, random, struct, subprocess, sys, threading, os
from renode_driver import Renode, ROOT, FLAGS
JAVA = Path(os.environ['JAVA'])

def save(path, data):
    path.parent.mkdir(exist_ok=True, parents=True)
    with path.open('x', encoding='utf-8') as out: json.dump(data, out, indent=2)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

class Fop:
    def __init__(self, prefix):
        self.stderr = (ROOT / (prefix + '_fop_stderr.log')).open('x', encoding='utf-8')
        self.proc = subprocess.Popen([str(JAVA), '-cp', str(ROOT / 'compiled_v2') + os.pathsep + os.environ['YAMCS_CLASSPATH'],
                                      'org.yamcs.tctm.ccsds.VirtualPeerV2'], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=self.stderr, text=True,
                                     creationflags=FLAGS)
        self.queue = queue.Queue()
        def reader():
            for line in self.proc.stdout: self.queue.put(line)
            self.queue.put(None)
        threading.Thread(target=reader, daemon=True).start()
        self.state = {}
    def ask(self, operation, **data):
        self.proc.stdin.write(json.dumps({'op': operation, **data}) + '\n'); self.proc.stdin.flush()
        line = self.queue.get(timeout=20)
        if line is None: raise RuntimeError('Native FOP exited')
        self.state = json.loads(line)
        if 'error' in self.state: raise RuntimeError(self.state['error'])
        return self.state
    def close(self):
        if self.proc.poll() is None:
            self.proc.stdin.write('{"op":"quit"}\n'); self.proc.stdin.flush()
            try: self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired: self.proc.terminate(); self.proc.wait(timeout=5)
        self.stderr.close()

def packets(raw, response=False):
    out = []
    offset = 0
    while offset < len(raw):
        assert len(raw) - offset >= 7
        apid = int.from_bytes(raw[offset:offset + 2], 'big')
        length = 7 + int.from_bytes(raw[offset + 4:offset + 6], 'big')
        data = raw[offset:offset + length]
        assert len(data) == length
        if apid != 0x07ff:
            assert apid == (0x0042 if response else 0x1042) and length >= 14
            out.append((data[6:14].hex(), data.hex()))
        offset += length
    assert offset == len(raw)
    return out

def demands(seed):
    rng = random.Random(seed)
    output = []
    for index in range(24):
        instant = (0 if index < 12 else 250000) + rng.randrange(5000)
        length = rng.choice([14, 64, 128, 256])
        uid = (seed << 32) | index
        data = struct.pack('>HHHQ', 0x1042, 0xc000 | index, length - 7, uid) + bytes([index]) * (length - 14)
        output.append({'t_us': instant, 'index': index, 'uid': data[6:14].hex(), 'hex': data.hex()})
    return sorted(output, key=lambda item: (item['t_us'], item['index']))

def run_case(renode, peer, case, folder):
    state, reset_records = renode.request(0, bytes([case['capacity'], 255, 1]) + struct.pack('>H', case['feedback_ms']))
    assert state[1] == 255 and state[3] == 0 and state[4] == 1
    assert state[13] == state[14] == state[18] == 0
    initial_irq_count = state[11]
    baseline = renode.sim_us
    now, serial_free, ordering = 0, 0, 0
    wire_busy = False
    events, executed, returned = [], {}, {}
    frame_instances = 0
    tm_frames = []
    original = demands(case['seed'])
    expected = {item['uid']: item['hex'] for item in original}
    trace_path = ROOT / folder / (case['id'] + '.jsonl')
    trace_path.parent.mkdir(exist_ok=True, parents=True)
    trace = trace_path.open('x', encoding='utf-8')
    def log(event, **data):
        trace.write(json.dumps({'virtual_us': now, 'event': event, **data}) + '\n'); trace.flush()
    def enqueue(instant, kind, value):
        nonlocal ordering
        ordering += 1; heapq.heappush(events, (instant, ordering, kind, value))
    for demand in original: enqueue(demand['t_us'], 'source', demand)
    peer.ask('reset', max_frame=261, window=4, t1_ms=3000, tx_limit=3, vr=255)
    log('configuration', **case, time_kind='Renode virtual execution and quantized output collection')
    try:
        while len(returned) < 24 and now < 30000000 and not peer.state.get('alerts'):
            native = peer.state.get('next_due_us', math.inf)
            next_time = min(events[0][0] if events else math.inf, native, now + 5000)
            if next_time > now:
                new_records = renode.run(int(next_time - now))
                now = int(next_time)
                peer.ask('advance', now_us=now)
                for record in new_records:
                    kind = record['kind']; data = bytes.fromhex(record['payload_hex'])
                    if kind == 0x81:
                        for uid, encoded in packets(data):
                            assert uid not in executed and encoded == expected[uid]
                            executed[uid] = {'hex': encoded, 'collected_us': now}
                            log('handler_commit', uid=uid, hex=encoded, time_is_collection_upper_bound=True)
                    elif kind == 0x82:
                        assert len(data) == 280 and data[:2] == b'\x02\xa3' and data[4:6] == b'\x18\x00'
                        assert binascii.crc_hqx(data[:-2], 0xffff) == int.from_bytes(data[-2:], 'big')
                        tm_frames.append(data.hex()); start = max(now, serial_free)
                        serial_free = start + 2240
                        enqueue(serial_free, 'tm_arrival', data)
                        log('mcu_tm_output', hex=data.hex(), collection_us=now, return_arrival_us=serial_free)
                    elif kind == 0x83:
                        fields = list(struct.unpack('<10I', data))
                        log('farm_result', fields=fields)
                    elif kind == 0x80:
                        fields = struct.unpack('<24I', data)
                        assert fields[4] == 1 and fields[13] == fields[14] == fields[18] == 0
            while events and events[0][0] <= now:
                _, _, kind, value = heapq.heappop(events)
                if kind == 'source':
                    log('source', **value)
                    peer.ask('send', hex=value['hex'], index=value['index'])
                elif kind == 'tc_arrival':
                    wire_busy = False
                    log('tc_ingress_message', hex=value.hex(), sequence=value[4])
                    renode.send(1, value)
                elif kind == 'declared_drop_complete':
                    wire_busy = False
                    log('declared_first_frame_loss_serialization_complete')
                elif kind == 'tm_arrival':
                    log('tm_arrival', hex=value.hex(), clcw=value[-6:-2].hex())
                    for uid, encoded in packets(value[6:-6], True):
                        transformed = bytearray.fromhex(expected[uid]); transformed[0] &= 0xef
                        assert uid not in returned and encoded == transformed.hex() and uid in executed
                        returned[uid] = {'hex': encoded, 'received_us': now}
                        log('sink', uid=uid, hex=encoded)
                    peer.ask('clcw', hex=value[-6:-2].hex())
            if not wire_busy:
                frame = peer.ask('pull')
                if 'frame_hex' in frame:
                    data = bytes.fromhex(frame['frame_hex']); frame_instances += 1
                    wire_busy = True
                    arrival = now + math.ceil(8 * len(data) * 1e6 / case['rate_bps'])
                    log('tc_departure', hex=data.hex(), sequence=data[4], arrival_us=arrival)
                    if case.get('drop_first') and frame_instances == 1:
                        enqueue(arrival, 'declared_drop_complete', None)
                        log('declared_first_frame_loss', hex=data.hex())
                    else: enqueue(arrival, 'tc_arrival', data)
        state, tail_records = renode.request(3)
        assert state[4] == 1 and state[13] == state[14] == state[18] == 0
        latencies = [returned[item['uid']]['received_us'] - item['t_us'] for item in original if item['uid'] in returned]
        result = {'case': case, 'kind': 'Renode STM32F4 peripheral emulation, not physical MCU timing validation',
                  'source_count': 24, 'exact_unique_executions': len(executed), 'exact_sink_count': len(returned),
                  'complete': len(executed) == len(returned) == 24 and not peer.state.get('alerts'),
                  'alerts': peer.state.get('alerts', []), 'max_owned_fdu': state[16], 'guards_ok': bool(state[4]),
                  'rx_interrupts_delta': state[11] - initial_irq_count,
                  'final_firmware_status': list(state), 'tm_frame_count': len(tm_frames), 'tc_instances': frame_instances,
                  'max_quantized_source_to_sink_virtual_us': max(latencies, default=None),
                  'p95_quantized_source_to_sink_virtual_us': sorted(latencies)[math.ceil(.95 * len(latencies)) - 1] if latencies else None,
                  'elapsed_virtual_us': now, 'output_collection_quantum_max_us': 5000,
                  'source': original, 'executed': executed, 'sink': returned, 'tm_frames': tm_frames,
                  'physical_measurements': False}
        save(ROOT / folder / (case['id'] + '.json'), result)
        return result
    finally: trace.close()

def make_cases():
    return [{'id': f'r{rate}_n{cap}_fb{feedback}_s67', 'rate_bps': rate, 'capacity': cap,
             'feedback_ms': feedback, 'seed': 67, 'initial_sequence': 255, 'mips': 100,
             'classification': 'functional reference assumptions, not measured spacecraft workload'}
            for rate in [4000, 256000] for cap in [1, 2, 4, 8] for feedback in [100, 1000]]

def freeze():
    save(ROOT / 'campaign_charter.json', {'kind': 'Functional Renode campaign; no calibrated prediction claims',
         'cases': make_cases(), 'arrival': 'Complete framed UART requests are batched after externally modeled decoded-frame serialization',
         'return': 'Firmware TM bytes, collection quantization at most 5 ms plus externally modeled 1 Mbit/s serialization',
         'success': '24 exact unique commits and replies per case, no fatal FOP alert, no guard/ring/parser/reply overflow',
         'service_cost': 'Compiled instructions under explicit 100 MIPS, SysTick clock 72 MHz; not STM32 hardware cycles',
         'no_artificial_service_delays': True, 'no_background_work_or_RTOS_claim': True,
         'selection': 'No mission resource selection from these functional runs; earlier paper decision remains conditional'})
    paths = [ROOT / name for name in ['stm32_firmware.c', 'stm32_startup.c', 'pool_adapter.c', 'stm32.ld', 'stm32_farm.elf',
             'stm32_profile.repl', 'renode_driver.py', 'coupled_renode.py', 'campaign_charter.json', 'VirtualPeerV2.java']]
    paths += list((ROOT / 'compiled_v2').rglob('*.class'))
    save(ROOT / 'FROZEN-CAMPAIGN.json', {'frozen_utc': datetime.now(timezone.utc).isoformat(),
         'scope': 'Renode functional campaign, not a model prediction/physical validation split',
         'sha256': {str(path.relative_to(ROOT)): sha(path) for path in paths}})

def main(action):
    if action == 'freeze': freeze(); print('Functional campaign frozen before target matrix'); return
    if action in ['pilot', 'pilot2']:
        seed = 61 if action == 'pilot' else 62
        cases = [{'id': f'{action}_r256000_n1_fb100_s{seed}', 'rate_bps': 256000, 'capacity': 1, 'feedback_ms': 100, 'seed': seed, 'mips': 100}]
        prefix, folder = 'coupled_' + action, action
    else:
        manifest = json.loads((ROOT / 'FROZEN-CAMPAIGN.json').read_text())
        assert all(sha(ROOT / name) == digest for name, digest in manifest['sha256'].items())
        cases = json.loads((ROOT / 'campaign_charter.json').read_text())['cases']
        prefix, folder = 'coupled_matrix', 'cases'
    r = Renode(prefix); peer = Fop(prefix); output = []
    try:
        for case in cases:
            result = run_case(r, peer, case, folder); output.append(result)
            print(json.dumps({'case': case['id'], 'exact_sink': result['exact_sink_count'], 'complete': result['complete']}), flush=True)
            if not result['complete']: raise RuntimeError('Saved incomplete case; inspect retained evidence')
        save(ROOT / (prefix + '_summary.json'), {'completed_utc': datetime.now(timezone.utc).isoformat(),
              'cases': len(output), 'exact_source_commands': sum(item['source_count'] for item in output),
              'exact_executions': sum(item['exact_unique_executions'] for item in output),
              'exact_sink_commands': sum(item['exact_sink_count'] for item in output), 'physical_measurements': False})
    finally: peer.close(); r.close()

if __name__ == '__main__': main(sys.argv[1])
