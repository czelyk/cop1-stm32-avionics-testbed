"""Fresh exploratory profiles after source-auditing the V1 UART model.

Keep firmware and V1 fixed. UART BRR=16 gives 500 kbaud at model 8 MHz,
enough for the reference 256 kbit/s decoded ingress plus bench envelope.
The model still lacks real hardware overrun/TX readiness. No physical claim.
"""
from datetime import datetime, timezone
import json
from coupled_renode import ROOT, Fop, Renode, run_case, save, sha

cases = []
for capacity in [1, 2, 4, 8]:
    cases.append({'id': f'v3_r256000_n{capacity}_fb1000_s81_m100', 'capacity': capacity,
                  'feedback_ms': 1000, 'rate_bps': 256000, 'seed': 81, 'mips': 100, 'uart_baud': 500000})
for mips in [100, 50]:
    for feedback in [100, 1000]:
        cases.append({'id': f'v3_r256000_n1_fb{feedback}_s83_m{mips}', 'capacity': 1,
                      'feedback_ms': feedback, 'rate_bps': 256000, 'seed': 83, 'mips': mips, 'uart_baud': 500000})
cases.append({'id': 'v3_loss_r256000_n1_fb100_s89_m100', 'capacity': 1, 'feedback_ms': 100,
              'rate_bps': 256000, 'seed': 89, 'mips': 100, 'uart_baud': 500000, 'drop_first': True,
              'classification': 'declared one-frame-loss functional control'})
spec = {'frozen_utc': datetime.now(timezone.utc).isoformat(), 'kind': 'Fresh exploratory functional controls',
        'reason': 'Source audit found V1 USART default 8 MHz / BRR139 = 57553 baud; that stage limits high-rate pressure',
        'changes': 'Explicit UART BRR16 at quiescent boundaries; fresh seeds; two paired MIPS sensitivity cases; one frame-loss control',
        'unchanged': 'All frozen V1 firmware/source/class files, NASA protocol behavior, service code, source-only causal inputs',
        'cases': cases, 'no_physical_or_model_prediction_claim': True,
        'source_sha256': {name: sha(ROOT / name) for name in ['renode_v3_controls.py', 'coupled_renode.py', 'renode_driver.py', 'stm32_farm.elf']}}
save(ROOT / 'V3-FROZEN-SPEC.json', spec)
manifest = json.loads((ROOT / 'FROZEN-CAMPAIGN.json').read_text())
assert all(sha(ROOT / name) == digest for name, digest in manifest['sha256'].items())
r = Renode('exploratory_fast_uart_v3'); peer = Fop('exploratory_fast_uart_v3'); results = []
try:
    for case in cases:
        r.cmd(f'cpu PerformanceInMips {case["mips"]}')
        r.cmd('sysbus WriteDoubleWord 0x40004408 0x10')
        actual = r.cmd('sysbus.usart2 BaudRate')
        assert '0x0007A120' in actual or '500000' in actual, actual
        result = run_case(r, peer, case, 'exploratory_fast_uart_v3')
        results.append(result)
        print(json.dumps({'case': case['id'], 'exact_sink': result['exact_sink_count'], 'complete': result['complete']}), flush=True)
        if not result['complete']: raise RuntimeError('Incomplete exploratory case retained; no positive result assumed')
    save(ROOT / 'exploratory_fast_uart_v3_summary.json', {
        'completed_utc': datetime.now(timezone.utc).isoformat(), 'kind': 'Exploratory Renode functionality and MIPS sensitivity',
        'cases': len(results), 'exact_source_commands': sum(x['source_count'] for x in results),
        'exact_executions': sum(x['exact_unique_executions'] for x in results),
        'exact_sink_commands': sum(x['exact_sink_count'] for x in results), 'uart_baud_verified': 500000,
        'no_physical_measurements': True,
        'limitations': 'ORE permanently false, TXE permanently true; host output collection and modeled return delay remain explicit'})
finally:
    peer.close(); r.close()

