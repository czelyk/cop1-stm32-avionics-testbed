"""Validate archived bytes, rebuild firmware and run fresh Renode controls."""
from pathlib import Path
import argparse
import binascii
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from lab import new_run, execute, find_tool, verify_recorded, finish
from bootstrap import bootstrap


def archived_cases():
    paths = sorted((ROOT / 'evidence/recorded/cases').glob('*.json'))
    paths += sorted((ROOT / 'evidence/recorded/exploratory_fast_uart_v3').glob('*.json'))
    assert len(paths) == 25
    commands, tm_frames = 0, 0
    for path in paths:
        case = json.loads(path.read_text())
        assert case['complete'] and case['guards_ok'] and not case['alerts']
        assert case['source_count'] == case['exact_unique_executions'] == case['exact_sink_count'] == 24
        expected = {x['uid']: bytes.fromhex(x['hex']) for x in case['source']}
        assert len(expected) == 24
        assert set(expected) == set(case['executed']) == set(case['sink'])
        for uid, raw in expected.items():
            assert bytes.fromhex(case['executed'][uid]['hex']) == raw
            response = bytes([raw[0] & ~0x10]) + raw[1:]
            assert bytes.fromhex(case['sink'][uid]['hex']) == response
        for text in case['tm_frames']:
            raw = bytes.fromhex(text)
            assert binascii.crc_hqx(raw[:-2], 0xffff) == int.from_bytes(raw[-2:], 'big')
        commands += len(expected)
        tm_frames += len(case['tm_frames'])
    assert commands == 600 and tm_frames == 425
    return dict(archived_cases=25, archived_exact_commands=commands, archived_tm_crc_checks=tm_frames)


p = argparse.ArgumentParser()
p.add_argument('--verify-only', action='store_true')
p.add_argument('--campaign', action='store_true', help='also run the 16-case and nine-case Yamcs/Renode campaigns')
args = p.parse_args()
verified = verify_recorded()
recorded = archived_cases()
if args.verify_only:
    print(json.dumps(dict(packaged_files_verified=verified, **recorded), indent=2))
    raise SystemExit(0)
if os.name != 'nt':
    raise SystemExit('Fresh Renode execution currently supports Windows; --verify-only is portable.')
deps = bootstrap()
run, work = new_run('renode')
env = os.environ.copy()
env['ARM_GCC'] = str(find_tool('arm-none-eabi-gcc', 'ARM_GCC'))
env['CTC_NASA_DIR'] = str(deps / 'nasa')
env['RENODE_HOME'] = str(deps / 'renode/renode_1.17.0-portable')
execute([sys.executable, work / 'build_firmware.py'], work, 'build.log', env)
execute([sys.executable, work / 'screen_renode.py'], work, 'controls.log', env)
controls = json.loads((work / 'ownership_screen_result.json').read_text())
assert len(controls['cases']) == 4 and controls['total_exact_unique_executions'] == 19
detail = dict(packaged_files_verified=verified, fresh_ownership_cases=4,
              fresh_exact_executions=19, **recorded)
if args.campaign:
    env['JAVA'] = str(find_tool('java', 'JAVA'))
    execute([sys.executable, ROOT / 'tools/prepare_yamcs.py'], ROOT, run / 'yamcs-prepare.log', env, timeout=1800)
    cp = json.loads((deps / 'yamcs-classpath.json').read_text())
    env['YAMCS_CLASSPATH'] = str(deps / 'yamcs-dependencies.jar')
    execute([sys.executable, ROOT / 'tools/compile_peer.py', str(work)], ROOT, run / 'peer-build.log', env)
    execute([sys.executable, work / 'coupled_renode.py', 'freeze'], work, 'freeze.log', env)
    execute([sys.executable, work / 'coupled_renode.py', 'matrix'], work, 'matrix.log', env, timeout=1200)
    execute([sys.executable, work / 'renode_v3_controls.py'], work, 'v3.log', env, timeout=1200)
    matrix = json.loads((work / 'coupled_matrix_summary.json').read_text())
    v3 = json.loads((work / 'exploratory_fast_uart_v3_summary.json').read_text())
    assert matrix['cases'] == 16 and matrix['exact_sink_commands'] == 384
    assert v3['cases'] == 9 and v3['exact_sink_commands'] == 216
    detail.update(fresh_coupled_cases=25, fresh_coupled_commands=600)
finish(run, dict({'pass': True, 'kind': 'Renode functional emulation; no physical timing'}, **detail))
