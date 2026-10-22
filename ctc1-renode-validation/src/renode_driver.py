from pathlib import Path
import binascii, json, re, socket, struct, subprocess, time, os
ROOT = Path(__file__).resolve().parent
RUNTIME = Path(os.environ['RENODE_HOME'])
FLAGS = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0

class Renode:
    def __init__(self, label, mips=100):
        self.label = label
        self.log = (ROOT / (label + '_renode.log')).open('x', encoding='utf-8')
        self.records = (ROOT / (label + '_uart.jsonl')).open('x', encoding='utf-8')
        self.console = (ROOT / (label + '_monitor.log')).open('x', encoding='utf-8')
        self.p = subprocess.Popen([str(RUNTIME / 'renode.exe'), '--disable-gui', '--plain',
                                  '-P', '21688', '--config', str(ROOT / 'renode.config')],
                                 cwd=RUNTIME, stdout=self.log, stderr=self.log, creationflags=FLAGS)
        self.monitor = None
        self.uart = None
        self.buffer = b''
        self.sim_us = 0
        self.sequence = 0
        self.pending = []
        try:
            for _ in range(100):
                try:
                    self.monitor = socket.create_connection(('127.0.0.1', 21688), timeout=.2)
                    break
                except OSError:
                    if self.p.poll() is not None: raise RuntimeError('Renode exited during startup')
                    time.sleep(.1)
            if self.monitor is None: raise TimeoutError('Renode monitor did not open')
            self.monitor.settimeout(20)
            self._prompt()
            self.cmd('mach create "ctc1_stm32"')
            self.cmd('machine LoadPlatformDescription @' + (ROOT / 'stm32_profile.repl').as_posix())
            self.cmd(f'cpu PerformanceInMips {mips}')
            self.cmd('emulation CreateServerSocketTerminal 21689 "serial" false')
            self.cmd('connector Connect sysbus.usart2 serial')
            self.uart = socket.create_connection(('127.0.0.1', 21689), timeout=2)
            self.uart.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.uart.setblocking(False)
            self.cmd('sysbus LoadELF @' + (ROOT / 'stm32_farm.elf').as_posix())
            self.cmd('emulation SetGlobalQuantum "0.0001"')
            self.run(10000)
        except Exception:
            self.close()
            raise

    def _prompt(self):
        data = b''
        while True:
            chunk = self.monitor.recv(65536)
            if not chunk: raise RuntimeError('Renode monitor disconnected')
            data += chunk
            if re.search(rb'\([^\r\n]*\)\s*$', data): break
        text = data.decode('utf-8', 'replace')
        self.console.write(text + '\n'); self.console.flush()
        return text

    def cmd(self, command):
        self.console.write('COMMAND ' + command + '\n'); self.console.flush()
        self.monitor.sendall((command + '\n').encode())
        response = self._prompt()
        if any(s in response.lower() for s in ['there was an error', 'unknown command', 'could not', 'no such command']):
            raise RuntimeError(response)
        return response

    def run(self, microseconds):
        if microseconds <= 0: return self.drain()
        self.cmd(f'emulation RunFor "{microseconds / 1e6:.6f}"')
        self.sim_us += microseconds
        # Socket transport synchronization is host-only; never used as target timing.
        time.sleep(.001)
        return self.drain()

    def drain(self):
        while True:
            try:
                part = self.uart.recv(65536)
                if not part: raise RuntimeError('UART socket closed')
                self.buffer += part
            except BlockingIOError: break
        records = []
        while len(self.buffer) >= 8:
            if self.buffer[:2] != b'\x5a\xa5': raise ValueError('Invalid UART record marker: ' + self.buffer[:24].hex())
            kind, seq, length = struct.unpack('>BBH', self.buffer[2:6])
            if len(self.buffer) < length + 8: break
            raw = self.buffer[:length + 8]; self.buffer = self.buffer[length + 8:]
            assert binascii.crc_hqx(raw[2:-2], 0xffff) == int.from_bytes(raw[-2:], 'big'), 'UART record CRC mismatch'
            r = {'collected_virtual_us': self.sim_us, 'kind': kind, 'sequence': seq,
                 'payload_hex': raw[6:-2].hex(), 'record_hex': raw.hex()}
            self.records.write(json.dumps(r) + '\n'); self.records.flush()
            records.append(r)
        return records

    def send(self, op, data=b''):
        self.sequence = (self.sequence + 1) & 255
        head = struct.pack('>BBH', op, self.sequence, len(data))
        raw = b'\xa5\x5a' + head + data
        raw += struct.pack('>H', binascii.crc_hqx(raw[2:], 0xffff))
        self.uart.setblocking(True)
        self.uart.sendall(raw)
        self.uart.setblocking(False)
        time.sleep(.003)  # host bridge delivery; no guest time advances here
        return self.sequence

    def request(self, op, data=b''):
        seq = self.send(op, data)
        received = []
        for _ in range(20):
            received.extend(self.run(1000))
            replies = [r for r in received if r['kind'] == 0x80 and r['sequence'] == seq]
            if replies:
                state = struct.unpack('<24I', bytes.fromhex(replies[-1]['payload_hex']))
                return state, received
        raise TimeoutError('No firmware status response')

    def close(self):
        if self.monitor:
            try: self.monitor.sendall(b'quit\n')
            except OSError: pass
            self.monitor.close()
        if self.uart: self.uart.close()
        try: self.p.wait(timeout=5)
        except subprocess.TimeoutExpired: self.p.terminate(); self.p.wait(timeout=5)
        self.console.close(); self.records.close(); self.log.close()

if __name__ == '__main__':
    r = Renode('boot_probe')
    try:
        state, records = r.request(3)
        print(json.dumps({'booted': True, 'state': list(state), 'uart_records': len(records)}))
    finally: r.close()
