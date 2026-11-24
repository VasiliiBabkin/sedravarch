# Mathematical model

For ordered inputs `X = (X₁, …, Xₘ)`, a representation chooses a partition for each file, a transformation or base for each block, and a code and model for each emitted stream. Retain only byte-exact inverses. If `Pᵥ` is the actual serialized payload, the current objective in bytes is

```text
minimize 16 + 8m + Σᵥ (15 + |Pᵥ|)
subject to workspace ≤ M, search work ≤ B, depth(v) ≤ D,
           and C(select j) ≤ Wⱼ for each file j.
```

The 16 bytes cover magic, file count and archive CRC. Each 8-byte file entry records length and block count. The 15-byte record includes reference ID, lengths, checksum and codec ID. The payload includes model tables, initial states, transformation operands, positions, values and residual bytes where present. A future external index or side stream adds its serialized byte count. This formulation scores complete emitted bytes. External benchmarks that store filenames have materially different metadata.

A dependency points at a smaller file ordinal. Depth is zero for an independent block and one plus base depth otherwise. A conservative restoration cost is the sum of decoded sizes along each selected block's ancestor chain, counted per visit, plus the encoded scan and a per-visited-block decoder setup bound. v1 enforces three edges and 16 KiB per block; it does not implement arbitrary caller-specified per-file restoration budgets. Worst-case reconstruction work for a file of length ℓ is bounded by ℓ plus 48 KiB per block, excluding parser scan and per-block setup. rANS model expansion has at most 4096 entries. Delta operation counts are bounded by both payload length and output length.

## Probability and model description

For empirical distribution `P`, entropy is `H(P) = −Σ P(a) log₂ P(a)`. Conditional entropy averages `H(P(·|c))` over contexts. A predictive model `Q` has expected cross-entropy `H(P,Q) = H(P) + D_KL(P‖Q)` when it supports every observed symbol. Integer normalization makes `Q` explicit and quantization contributes to the mismatch term. Residual concentration can lower the empirical order-0 entropy while a serialized residual stream still grows due to model cost. The experiment uses two-part minimum description length through actual bytes, including frequency records and termination. It does not use the empirical entropy as an acceptance rule.

## Exact oracle and scalable approximation

An exact small-instance search can enumerate partitions in topological order, then, for each block, enumerate permitted independent models and previously chosen bases. To make an optimum claim, define a finite candidate universe including all precision values, and for delta include every admissible copy/add parse or generate a minimum encoded script by a shortest path over output positions. Track actual resource consumption and dependency depths as state. Reject assignments exceeding any bound and retain the feasible complete assignment of minimum serialized size, using lexicographic ties. A lower bound can sum per-block minimum cost in a relaxation that allows every possible base; pruning an incumbent only when that bound cannot improve it preserves exactness. This global oracle is specified for future implementation. Search across potential prior partitions grows exponentially.

The implemented optimizer freezes the history from prior completed files. For each input, it visits start positions in ascending 4 KiB cells and proposes spans of 4, 2 and 1 cells, with final truncation at EOF. At each edge, it retains the smallest candidate found. It computes the exact shortest path for this generated edge set by `D[t] = min(D[s] + 15 + |payload(s,t)|)`. This optimum is conditional on frozen history, candidate pruning and the deterministic allocation of delta work. Earlier files are never revisited. A smaller earlier archive can eliminate useful future reference blocks.

Bottom-k votes rank candidates from a 256-block rolling index; only the most recent 16 postings per key vote. Exact hits require byte equality. At most two ranked bases reach delta encoding, charged by the sum of base and target sizes against eight times the file length. The encoder retains the best evaluated payload per edge. Spending on unused edges can exhaust the allowance. The budget is a work proxy and excludes independent modeling, hashing and analysis. Multi-file global allocation and Pareto dynamic programming remain open.
