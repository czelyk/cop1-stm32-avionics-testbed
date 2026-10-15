# COP-1 STM32 Avionics Testbed

**CCSDS COP-1 telecommand receiver integration and verification for a small-spacecraft-style embedded environment.**

This repository is a curated **engineering portfolio**, not a flight-qualified implementation, full COP-1 conformance suite, or peer-reviewed spacecraft performance study.

## Architecture

```text
Ground-side Yamcs FOP
        | TC transfer frames and retransmissions
        v
Decoded-frame / UART transport  <-- emulated in Renode when local sources are imported
        v
STM32F4 Cortex-M firmware --> NASA COP-1 FARM (pinned upstream dependency)
        |                              |
        |                     FDU ownership / Wait / CLCW
        v                              v
Command handler --> response records / TM frames --> ground verifier
```

The material available in the attached source archive includes **standalone ARM FARM test glue** and **Yamcs verification adapters**. A separate, later Renode campaign was reported, but its firmware and test files were **not present in the archive used to assemble this download**. Add and check those actual files from your local research directory before publishing claims that this repository reproduces the Renode runs.

## Repository layout

| Directory | Contents |
|---|---|
| `examples/arm-farm-harness/` | Finite-FDU Cortex-M harness around the pinned NASA `cop1.c` and `tctf.c`, including capacity-specific build variants |
| `tests/yamcs/` | Local Java adapters for pinned Yamcs FOP and TM frame decoder. These rely on upstream/internal Yamcs test classes and **are not standalone** |
| `results/` | Small, source-backed software-only validation and ARM harness footprint summaries |
| `docs/` | Architecture scope, evidence limitations, reproduction prerequisites, and dependency notices |
| `firmware/stm32f4/` | Destination for real STM32 firmware from the later local Renode campaign |
| `simulation/renode/` | Destination for Renode profile and driver from the local campaign |
| `tests/renode/` | Destination for local functional/end-to-end Renode tests |
| `tools/` | Non-destructive local-source organizer |

## Verified evidence available in this distribution

The uploaded earlier research archive records **64 software-only reference runs with 1,536 exact command outputs**. Those runs used assigned virtual service durations, not physical MCU timing. The selected source files and aggregate summary are in this package.

A separate later **Renode STM32F4** campaign was reported by the developer: **25 cases, 600/600 unique command/response records and 425 independently decoded TM frames**. This package **does not contain the later Renode firmware or raw logs**, so those reported numbers are not claimed as independently reproducible from this ZIP. After importing that source and validating it, document the results under `docs/renode-validation.md` with precise scope.

## Build and reproduction status

The included ARM harness requires the unchanged pinned NASA CFS_IO_LIB `cop1.c`, `tctf.c`, its original headers, and suitable cFE API shims. The Java code requires a pinned Yamcs checkout, appropriate dependencies, and some Yamcs test classes. **The original research build environment was Windows-specific and is not bundled here.** Therefore this curated snapshot is not advertised as a turn-key, independently building project. See [reproduction notes](docs/reproduction.md).

To populate the Renode portion using actual Windows source files, see [`tools/import-local-renode.ps1`](tools/import-local-renode.ps1). The script copies a strict allowlist, never deletes originals, does not overwrite conflicting files, and does not run Git.

## What this project does *not* establish

- No measurements of STM32 silicon service times, UART overrun resilience, WCET, or power usage.
- No DMA / FreeRTOS integration is claimed from the reported Renode setup.
- No flight hardware qualification, radiation tolerance, RF-layer processing, or mission-specific acceptance.
- No novel COP-1 protocol, buffer-sizing result, or scientifically validated predictive advantage is claimed.

## Upstream credit

Protocol implementation: [NASA CFS_IO_LIB](https://github.com/nasa/CFS_IO_LIB), pinned in the research to `3f41191d0d361bed88b056f2a7d45301ac7b3fe5`.
Ground FOP and TM decoding: [Yamcs](https://github.com/yamcs/yamcs), pinned to `ee4c33f1650f9fae84d9a932bea4d57d6c9b2bbb`.
Simulation infrastructure: [Renode](https://github.com/renode/renode).

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Upstream sources/binaries are **not bundled**. No blanket license has been asserted for third-party code.
