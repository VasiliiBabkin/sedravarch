# Research roadmap

Keep v1 on the research branch. Use the existing SedravArch engine for stable archives. The benchmark gate for a future general-purpose replacement is a measured improvement on independently held-out named-file workloads and a supported path for existing archives.

1. Compare the dependency graph with and without an intra-block dictionary coder. Reuse comparable LZ baselines, score actual headers and plot encode and decode resource trade-offs. Include a metadata-equivalent container comparison.
2. Build a manifest of real version families from separate upstream projects. Deduplicate across development, tuning and holdout families using exact hashes and resemblance audits. Add both equal-size edits and substantial insertion, deletion and movement.
3. Implement the small-instance oracle and compare candidate regret on fixed, content-defined and dynamic partitions. Record index recall separately from greedy delta parsing loss. Compare actual byte cost and dependency work under fixed budgets. Test a distinct opcode/address/length/value representation against interleaved scripts.
4. Prototype file-backed seeking and a checksummed offset index. Measure bytes actually read, reconstruction latency and cache reuse for old and new versions. Compare shallow versus deep policies and separate memory caps for encoder and decoder.
5. Test preflate corrections, full reversible BCJ/BCJ2 and numeric structure transforms as optional candidates. Include complete corrected stream and index byte counts, and reject candidates lacking verified byte-exact restoration. Run PE/DLL and ELF samples as inputs to data-only tools.
6. Introduce a coverage-guided decoder fuzzing job, check allocation thresholds at hard limits, and test error propagation, interrupted writes and cross-platform behavior. Optimize only phases whose wall or CPU breakdown shows material cost.
