"""Build the existing bare-metal UART/NVIC/SysTick fixture, not flight firmware."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess

ROOT = Path(__file__).resolve().parent
NASA = Path(os.environ['CTC_NASA_DIR'])
GCC = Path(os.environ['ARM_GCC'])
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--profile', choices=('legacy', 'renode-timing', 'board-timing'), default='legacy')
profile = parser.parse_args().profile
defines = []
if profile != 'legacy':
    defines.append('-DCTC_TIMING')
if profile == 'board-timing':
    defines.append('-DCTC_BOARD')
sources = [ROOT / name for name in ('stm32_startup.c', 'stm32_firmware.c', 'pool_adapter.c')]
sources += [NASA / 'fsw/src/services/cop1.c', NASA / 'fsw/src/formats/tctf.c']
command = [GCC, '-mcpu=cortex-m4', '-mthumb', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror',
           '-ffreestanding', '-fno-builtin', '-nostdlib', '-Wl,--build-id=none', *defines,
           '-Wl,-Map=' + str(ROOT / 'stm32_farm.map'), '-I', ROOT / 'shim',
           '-I', NASA / 'fsw/public_inc', '-T', ROOT / 'stm32.ld', *sources,
           '-o', ROOT / 'stm32_farm.elf']
p = subprocess.run(list(map(str, command)), capture_output=True, text=True)
(ROOT / 'build.json').write_text(json.dumps(dict(profile=profile, command=list(map(str, command)), exit_code=p.returncode,
    stdout=p.stdout, stderr=p.stderr), indent=2), encoding='utf-8')
if p.returncode:
    raise RuntimeError(p.stderr)
print(json.dumps(dict(built=True, sha256=hashlib.sha256((ROOT / 'stm32_farm.elf').read_bytes()).hexdigest())))
