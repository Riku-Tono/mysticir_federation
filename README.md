# MysticIR Federation v0.8.5

> **Different Surface, Same Underground Pipeline**

A prototype verification demo confirming that two languages with different surface notation — **💩 ScatLang** and **🌊 SeaIR** — normalize to the same Core AST and, from there, follow the same CEK trace and reach the same error signature on representative failure cases.

[日本語版はこちら](./ja/README.md)

---

## Overview

MysticIR Federation v0.8.5 is not a complete formal proof. It is a **prototype verification demo** targeting three representative failure cases. The key claim:

> Even when the surface symbols differ, once programs are parsed into the Core AST they become indistinguishable — they run through the same CEK machine and produce the same error at the same step.

The current implementation uses a **shared normalizing parser** that accepts both ScatLang-style and SeaIR-style tokens and maps them to the same Core AST nodes. Describing this as "two independent frontends converging" would be an overstatement for v0.8.5.

---

## The Two Surface Languages

Both programs below have the same meaning:

| | **💩 ScatLang** | **🌊 SeaIR** |
|---|---|---|
| zero | `💩₀` | `🌊` |
| N | `💩×N` | `🌊×N` |
| mod | `⊛` | `⚫` |
| assign | `←` | `⚓` |
| flush | `🚽⇐` | `🏝️` |
| while | `⟳` | `🌀` |
| succ | `💩⁺(…)` | `〰️…` |

Although their symbols differ, both notations are normalized at the parser layer to the same Core AST nodes.

---

## Pipeline

```
💩 ScatLang (surface parser)    🌊 SeaIR (surface parser)
          │                               │
          └───────────────┬───────────────┘
                          ▼
                      Core AST
                 (same tree structure)
                          │
                          ▼
              CEK Machine / Trace
            (same steps, same continuations)
                          │
                          ▼
                  Error Federation
             (same error signature,
              excluding frontend label)
```

Frontend labels (`💩ScatLang` / `🌊SeaIR`) are preserved in the trace record, so **surface differences are captured as evidence** while the underlying execution is identical.

---

## Verification Results

All three representative failure cases confirmed: `ast_equal`, `trace_equal`, `error_equal = true` and `surface_diff = true`.

| Case | Error Type | ast_equal | trace_equal | error_equal | surface_diff | Steps |
|---|---|---|---|---|---|---|
| mod by zero | `ScatError` | ✅ | ✅ | ✅ | ✅ | 12 == 12 |
| unbound variable | `ScatError` | ✅ | ✅ | ✅ | ✅ | 2 == 2 |
| step limit / infinite loop | `StepLimitError` | ✅ | ✅ | ✅ | ✅ | 40 == 40 |

Step counts match because both surface forms normalize to the same Core AST, causing the CEK machine to advance by the same number of steps.

---

## Metrics

**`ast_equal`** — After parsing, `parse(scat_src) == parse(sea_src)` is checked via structural equality. `true` means both surface notations produce the identical internal tree before execution begins.

**`trace_equal`** — The step-sequence records produced by the CEK machine are compared with frontend labels stripped. `true` means both followed the same execution path.

**`error_equal`** — The state fingerprint at the moment of the error is compared with frontend labels stripped. `true` means both failed at the same point with the same signature.

> ⚠️ The current signature includes `error_message` text. A future version should separate a stable `error_code` from the human-readable message to avoid fragility from wording changes.

**`surface_diff`** — When compared *with* frontend labels included, a mismatch is expected. `true` means surface differences are preserved in the record.

When all four metrics are `true`, the Federation's claim of **"different surface, same underground pipeline"** is confirmed for that case.

---

## Why 💩 and Not A?

`💩` and `🌊` are **surface markers**, not semantic primitives. What matters in MysticIR is not which symbol is used, but whether that symbol projects to the same Core AST node. `A`, `B`, or any other symbol would work equally well. The underground pipeline is indifferent to surface notation.

---

## Note on Underflow

`pred(💩₀)` does **not** raise an error in MysticIR. It returns an `Underflow` value (`💩∅`), propagating silently as a value rather than halting execution. Underflow is intentionally excluded from the Error Federation cases in v0.8.5 — it is treated as a **value**, not an error event.

---

## Usage

**Requirements:** Python 3.10+

```bash
python mysticir_federation_v085.py
```

Output: `mysticir_v085_error_federation_report.json` in the same directory.

**Presentation demo:** Open `demo.html` in a browser for an interactive overview of the pipeline and results.

---

## Files

| File | Description |
|---|---|
| `mysticir_federation_v085.py` | Core implementation: values, Core AST, CEK machine, parser, Error Federation runner |
| `demo.html` | Browser-based presentation of the verification results |
| `mysticir_v085_error_federation_report.json` | JSON report generated by the Python script |

---

*MysticIR Federation v0.8.5 — Verification demo on representative cases | Not a complete or formally proven result*

---

## Documents

- [Demo / explanation](./docs/demo.html)
- [Evidence report](./mysticir_v085_error_federation_report.json)
- [日本語版 README](./ja/README.md)

---

## License

MIT License. See [LICENSE](./LICENSE).

---

Please don’t alter the 💩 and 🌊 symbols; they are part of the project’s identity.
