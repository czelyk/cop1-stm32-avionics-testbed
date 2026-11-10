# CTC1 STM32/Renode Validation

Bare-metal STM32F4 fixture with NASA FARM, UART/NVIC/SysTick handling, a native Yamcs FOP adapter, and preserved raw campaign evidence.

## Run

Requirements: Windows, Python 3.12, Arm GNU Toolchain on PATH (or ARM_GCC). Renode is downloaded anonymously with checksum verification. The optional campaign also needs Java 17+ (JAVA/JAVA_HOME) and Maven 3.9+ (MAVEN/PATH).

```powershell
python tests/run.py --verify-only
python tests/run.py
# Optional full 25-case rerun: Java + Maven/pinned Yamcs classpath
python tests/run.py --campaign
```

`python tests/run.py --verify-only` checks the packaged file hashes without
rerunning the experiment. New runs go to ignored `runs/` directories (or
`outputs/` in the F Prime lab). Archived evidence is never used as an output target.

## Timing probe

The optional [STM32F407 timing probe](docs/TIMING-PROBE.md) builds a
16 MHz board image and checks its diagnostic format using a separate
Renode profile. It reports FARM, command commit and TM phases separately.

## Contents

- `src/`: C firmware, linker/profile files, Renode driver, Java peer and fresh campaign scripts.
- `evidence/recorded/`: 25 cases, 600 exact command/response records and 425 TM frames.
- `tools/`: pinned public dependency setup; optional Yamcs build.
- `docs/original-results.md`: actual limitations and original results.

## Scope

The default fresh run builds firmware and exercises four ownership/recovery cases. The full campaign is optional. Renode UART timing and MIPS are models; no DMA, RTOS, physical UART overrun, energy or silicon timing result is claimed.

This is a research implementation/archive, not flight-qualified software or a
claim of conference acceptance. Research and packaging used AI assistance.
The retained reports include negative findings and unresolved questions.

## Provenance and licensing

Original evidence was copied without overwriting its source directory. Portable
path changes are recorded in `provenance/patches/`; copied inputs and code have
SHA-256 provenance. `provenance/manifest.json` protects the curated files.
See `LICENSE.md` and `THIRD_PARTY_NOTICES.md`. GitHub publication is not performed
by any script in this repository.
