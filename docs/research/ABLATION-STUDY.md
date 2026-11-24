# Ablation study

The pilot starts with every candidate family enabled. Each row removes one component from that profile. Positive byte differences mean the archive grew. Prediction is evaluated through rANS, so removing rANS also removes the wire path for predictions. Removing references prevents both exact reuse and deltas. The analyzer reports statistics and does not affect encoding.

| Removed | Alice bytes Δ | Git ELF bytes Δ | Numeric bytes Δ | Random bytes Δ | SQLite bytes Δ | Synthetic family bytes Δ | zlib family bytes Δ |
|---|---:|---:|---:|---:|---:|---:|---:|
| Multiscale DP | 0 | +4,194 | 0 | 0 | +1,456 | −163,515 | −46,626 |
| References and candidate index | 0 | 0 | 0 | 0 | 0 | +360,399 | +32,546 |
| Copy/add deltas | 0 | 0 | 0 | 0 | 0 | +16,335 | +32,546 |
| rANS | +63,432 | +990,723 | +233,350 | 0 | +108,713 | 0 | +72,003 |
| Lag prediction | 0 | +27,569 | +158,966 | 0 | 0 | 0 | 0 |

The single-file time ratios are in the machine summary. Removing multiscale DP increased median encode throughput by about 6.1–7.2× on the five single-file probes. Removing lag prediction increased it by about 3.5–4.3×. Lag prediction substantially reduced the structured numeric input and also shrank the ELF. The benchmark checks every archive by reconstruction. [Pilot ablations](results/summary.json) · [zlib version family](results/zlib-versions.json)

With multiscale enabled the first file can choose boundaries that obscure future references. Freezing each file's locally best partition and charging search budgets in edge order can also waste delta work on unchosen edges. Fixed 16 KiB blocks improved both version-family results. Multiscale remains an explicit research control via `--multiscale`.

## Component decisions

| Component | Decision | Evidence or remaining test |
|---|---|---|
| Entropy, repetition and heterogeneity analysis | Accept as a diagnostic | Report whole-input and block entropy plus exact repeated grid chunks |
| Adaptive multiscale segmentation | Revise | Larger archives in both version families and substantial runtime cost. Off by default |
| Rolling hash, bottom-k and bounded index | Revise | Combined reference ablation helps both families. Candidate recall and index cost require a dedicated comparison |
| Copy/add delta | Accept for experiment | Deltas grew neither family and saved bytes in both. Compare optimal versus greedy parsing |
| Local and periodic prediction | Accept for experiment | Measurable numeric and ELF gains with high encoding cost. Profile and gate candidates |
| General context prediction | Revise | No general context model implemented |
| Inter-block prediction | Revise | The reference copy/add path is exercised across files. Model-based prediction remains open |
| Separate position and value streams | Revise | v1 interleaves scripts. The separate-stream hypothesis remains untested |
| Byte rANS and precision selection | Accept for experiment | Verified bit-exact streams and large gains versus fixed-width raw representation. Precision selection lacks an isolated ablation |
| Full serialized-cost codec selection | Accept | Candidates must beat raw or the incumbent including model bytes |
| Global graph optimization | Revise | Only bounded per-file shortest paths and prior-file references are implemented |
| Cross-file deduplication and extraction | Accept for experiment | Named alternatives compared on the same file bytes. Encoded reads are still global |
| Multi-stage ranking and adaptive budget | Revise | Votes, exact checking and limited deltas are implemented. Standalone ranking, budget and posting ablations remain open |
| Structure probes | Revise | BCJ, preflate and byte shuffle showed input-specific gains. Keep them out of the v1 codec |
| Blind DEFLATE recompression | Reject | The study did not reproduce PNG or DOCX streams from plaintext and zlib levels alone |
