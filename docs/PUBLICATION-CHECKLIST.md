# Publication readiness checklist

- [ ] Actual STM32/Renode source files and test scripts from the later 25-case campaign imported and manually reviewed.
- [ ] Verify no private IAC reports, experimental model freezes, local absolute file paths or API keys appear in tracked files or existing Git history.
- [ ] Verify original source ownership and appropriate licensing for your own code; keep pinned NASA/Yamcs notices.
- [ ] Replace/adapt absolute tool paths and confirm documented clean-environment build/test reproduction.
- [ ] Save small independently verifiable Renode results and limits; never report virtual timestamps as real MCU measurements.
- [ ] Keep research source and publications private until your disclosure strategy is settled.
- [ ] Inspect `git status`, `git diff --cached`, and repository history before GitHub upload.

This snapshot cannot fully satisfy the first and fourth items because later Renode sources were not in the provided archive.
