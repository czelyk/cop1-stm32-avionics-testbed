# Reproduction status and prerequisites

## Available files

- `examples/arm-farm-harness/pooled_farm.c`: simulation-oriented shared-memory step adapter; not standalone MCU firmware.
- `examples/arm-farm-harness/capacity_variants/*.c`: distinct compile-time slot allocations for approximate `.bss` measurements, not a full firmware footprint.
- `tests/yamcs/VirtualPeerV2.java`: deterministic native Yamcs FOP adapter. Depends on Yamcs internals **and Yamcs test class** `TcpTcDataLinkTest.MyCmdHistPublisher`.
- `tests/yamcs/TMVerifier.java`: native Yamcs TM CRC/OCF verification adapter.

## Required upstream checkouts

- NASA CFS_IO_LIB at the exact commit in `THIRD_PARTY_NOTICES.md`; original `cop1.c`, `tctf.c` and headers, plus independently provided cFE shims.
- Yamcs at the exact commit in the notices, with Maven-built test/runtime dependencies.
- For later Renode work: local sources + a version of Renode compatible with its STM32F4 platform file, GCC ARM toolchain, Java, and Python.

Do not claim reproducibility by running only the included snippets. The original 64-case campaign depended on other scripts and previous project directories intentionally withheld from this public package; it is represented by a small aggregate summary only. The project owner should import, refactor, document, and test the actual Renode project before advertising it as fully reproducible.

## File organizer

On the Windows computer, after extracting this folder to the intended destination, run **the optional file organizer** in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\import-local-renode.ps1
```

This script scans only the user's known local research workspace, copies an explicit file allowlist, and prints unresolved/missing files. It does **not** download, install, publish or commit anything. Inspect its summary and review the copied files before running Git.
