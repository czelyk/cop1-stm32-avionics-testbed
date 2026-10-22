# Packaging validation — 22 October 2026

**Executed successfully in the curated working copy:** 4 ownership controls / 19 exact executions, then 25 coupled cases / 600 exact commands and responses.

Renode functional emulation; no physical UART or MCU timing. Fresh firmware and Java adapter were rebuilt. Pinned Yamcs classes/JARs came from a copied public dependency cache; the from-empty Maven bootstrap was not executed in this packaging run.

Raw fresh outputs are retained in `evidence/packaging-20261022/`; earlier evidence
remains in `evidence/recorded/`. The `verification.json` file records the actual
test working directory and the file count at execution time. Later additions of
documentation/evidence change the final package file count, not those results.

Environment: Windows, Python 3.12.10; applicable tools were Arm GNU 15.2.1,
Unicorn 2.1.4, pyelftools 0.32, Renode 1.17.0, OpenJDK 21.0.10 and Go 1.27.3.
Only tools actually used by this project are prerequisites; see README.md.

Historical reports retain their original scope, decisions and local source paths.
Use the current README for execution. Historical paths are provenance, not runtime
dependencies. The clean Git copy and ZIP are checked again with `--verify-only`.
No physical testing, new scientific GO, conference acceptance or publication is
claimed by this packaging operation.
