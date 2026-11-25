# P02 — Measurement environment calibration

Date: 2026-11-25. **Infrastructure implemented; current VDS NOT QUALIFIED for comparative speed claims.** Fundamental research remains paused. This does not change H13–H13.2 or release claims.

## Predeclared calibration
The executable and thresholds were committed before the run: [a4d8406](https://github.com/VasiliiBabkin/sedravarch/commit/a4d8406fde889fbd12dc84185c96f809b773aa56). The synthetic workload is 2,128,576 bytes, zlib 6 encode/decode, Python 3.12.3, zlib 1.3. Single-vCPU affinity, nice +10, shared laboratory benchmark lock, three batches of seven samples per operation, one warmup per batch, alternating deterministic workload order. Each sample batches calls to target about 100 ms CPU time (minimum 50 ms for the calibration sample); the final output of each timed batch is verified outside timing. CPU time and monotonic wall time are recorded separately. No physical CPU isolation is asserted. No services or host configuration were changed.

For both CPU and wall time, each batch must have range/median <=20%, IQR/median <=10%, and between-batch median shift <=10%. Wall-time gate additionally requires median wall/CPU <=1.10 per batch and measured vCPU steal fraction <=2%. These are engineering gates, not confidence intervals. The script returns 2 on calibration FAIL, 0 on PASS. A single PASS is only a local screening result; repeat on a different day/session and the intended workload before ranking codecs.

## Results
[Raw samples and metadata](results/P02-20261125.json).

| vCPU | operation | max CPU range | max wall range | CPU median shift | wall median shift |
|---:|---|---:|---:|---:|---:|
| 0 | encode | 16.28% | 16.08% | 11.62% | 11.36% |
| 0 | decode | 37.08% | 36.79% | 0.92% | 1.01% |
| 1 | encode | 37.20% | 40.55% | 23.31% | 27.15% |
| 1 | decode | 35.01% | 89.23% | 25.21% | 27.31% |

vCPU 0 steal: 0.26%; vCPU 1: 6.18%. Both CPU and wall gates FAIL on both vCPUs. 84 timed samples, not 84 independent corpus files; loop counts differ by operation/vCPU and these data must not be used as a speed comparison between CPUs. CPU-time variation remains even where steal is low. This does not identify its cause. No extrapolation to all workloads or future VDS sessions.

## Reproduction
```sh
python3 research/science/p02_calibrate.py --cpu 0 --lock /path/to/lab/tmp/benchmark.lock --out /path/to/new-cpu0.json
python3 research/science/p02_calibrate.py --cpu 1 --lock /path/to/lab/tmp/benchmark.lock --out /path/to/new-cpu1.json
```
Use the existing common lock; output paths must not already exist. Raw data stays in the laboratory as well as in the repository. Temporary checkout was removed by trap. No GitHub Actions run requested.

## Operational policy
- Do not publish speed superiority or resume H13 on the basis of this run. Do not silently discard slow samples, loosen gates, select a favorable vCPU after observing results, or retest until a lucky PASS.
- For valid comparative tests: pre-register the CPU/host, exact builds, workloads, paired randomized trials, sample size, comparison metric and uncertainty; calibrate before and after on relevant workloads and retain all failures. Use CPU time for compute cost and wall time for user-visible latency, not interchangeably.
- Obtain a truly dedicated measurement machine or provider-backed dedicated cores, document frequency policy, SMT, competing tasks, and verify repeatability across sessions. CPU affinity alone cannot supply host-level isolation. Do not change server-wide affinity, stop production services, or reconfigure a shared VDS just to make a benchmark pass.
- Product correctness and format work may proceed independently. P03: audit format, bounded decoder, malformed archives, path traversal, checksums, version compatibility and failure atomicity. P04 performance claims remain blocked pending environment qualification.
