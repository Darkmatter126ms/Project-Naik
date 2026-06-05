# Compliance Agent — Rules Reference

**File:** `naik_agents/compliance.py :: run_compliance()`
**Path:** fully deterministic — **no LLM prompt**
**Returns:** `ComplianceResult` (verdict + rewritten artefacts)
**Last reviewed:** Day 3

---

## Why no LLM?

The compliance gate must provide a **guarantee**, not a best-effort. You cannot
delegate "does this sentence promise a return?" to a model that might miss edge
cases under competition pressure. The four rules below are deterministic
rewriters: regex + replacement string. Every rewrite is auditable, repeatable,
and testable with a unit test that runs in milliseconds.

A model could later rephrase already-sanitised text more fluently — that would be
additive. But the *enforcement* remains deterministic forever.

---

## The Four Rules

### Rule 1 — No specific return predictions

**Trigger:** a forward-looking claim containing a return word (imbal hasil,
return, keuntungan, untung, profit, cuan, menghasilkan) followed by a percentage
and optional per-period.

**Regex (simplified):**
```
(?:akan|bisa|dapat|memberi...)?\b(imbal hasil|return|keuntungan|...)\b
  \s*(sekitar|hingga|rata-rata|...)?\s*\d+[.,]?\d*\s*%
  (\s*(per tahun|setahun|per bulan|...))?
```

**Exception:** fee / expense-ratio / inflation percentages (matched by context
words: biaya, pengelolaan, rasio, expense, inflasi). These pass through unchanged.

**Replacement:**
```
berpotensi memberikan imbal hasil (kinerja masa lalu tidak menjamin hasil di masa depan)
```

---

### Rule 2 — No guarantee or no-risk language

**2a — guarantee-of-return:**

| Pattern | Example |
|---|---|
| `dijamin(kan)?` | "keuntungan dijamin" |
| `jaminan (untung\|keuntungan\|imbal hasil...)` | "dengan jaminan untung" |
| `pasti (untung\|cuan\|naik\|menghasilkan...)` | "pasti untung" |
| `guaranteed?` | "guaranteed returns" |

**Exception:** `dijamin LPS` (deposit-insurance statement) — passes through.

**Replacement:**
```
berpotensi memberikan imbal hasil (tanpa jaminan)
```

**2b — no-risk claims:**

| Pattern | Replacement |
|---|---|
| `tanpa risiko`, `bebas risiko`, `nol risiko`, `100% aman`, `risk-free` | `dengan risiko yang relatif lebih rendah (semua investasi tetap mengandung risiko)` |

---

### Rule 3 — Sharia suitability

**Trigger:** `halal_investor = True` AND any pick in `WealthRecommendation` has
`is_sharia = False`.

**Action:** annotates the offending pick's rationale with:
```
[PERLU TINJAUAN: dana ini belum tersertifikasi syariah dan tidak sesuai
untuk investor syariah.]
```

**Status escalation:** `APPROVED` → `NEEDS_HUMAN_REVIEW`

**Note:** the wealth agent is called with `sharia_only=True` for halal profiles,
so in practice Rule 3 fires only if there is a bug in the fund catalogue or the
halal-flag inference. It is a safety net, not the primary gate.

---

### Rule 4 — Manual confirmation (always on)

`requires_human_confirmation = True` on every `ComplianceVerdict`, always.
Not configurable. This is the OJK POJK 05/2021 requirement: no automated
financial transaction without a human-confirmed step.

The disclaimer `"Konfirmasi manual diperlukan sebelum melakukan transaksi apa pun."`
appears in every `FinalResponse.disclaimers` list.

---

## Status Codes

| Status | Condition |
|---|---|
| `APPROVED` | No rules triggered |
| `APPROVED_WITH_CONDITIONS` | Rules 1 or 2 triggered (text rewritten) |
| `NEEDS_HUMAN_REVIEW` | Rule 3 triggered (sharia mismatch) |
| `REJECTED` | (reserved; not triggered by current rules) |

For Sari (halal profile, heuristic Bahasa templates): status = `APPROVED`.
The heuristic templates contain no return predictions or guarantee language,
so Rules 1 and 2 never fire. Rule 3 does not fire because the wealth agent
correctly returns only sharia funds for halal personas.

---

## Standard Disclaimers

These five disclaimers appear for a full (wealth + insurance) FinalResponse:

1. `"Ini adalah panduan umum, bukan nasihat keuangan yang dipersonalisasi, sesuai ketentuan OJK."`
2. `"Konfirmasi manual diperlukan sebelum melakukan transaksi apa pun."` (Rule 4)
3. `"Kinerja masa lalu tidak menjamin hasil di masa depan."` (wealth present)
4. `"Investasi reksa dana mengandung risiko; nilai investasi dapat naik atau turun."` (wealth present)
5. `"Asuransi parametrik membayar berdasarkan indeks cuaca BMKG, bukan penilaian kerugian individual."` (insurance present)

Additional disclaimers added if Rules 1/2 or Rule 3 fire.

---

## Day-3 Cold-Read Findings

| # | Observation | Action |
|---|---|---|
| 1 | Compliance rationale (`len=147`) is appropriately concise | No change |
| 2 | Disclaimers address second person as "pengguna" in #2 but "Anda" elsewhere — minor inconsistency | Low priority; no change for now |
| 3 | `APPROVED` status for Sari's heuristic output is correct — no Rules fire | ✓ Confirmed expected |

---

## Testing

```bash
# Unit test for the rewriters (fast, no LLM)
python naik_agents/test_compliance.py

# Integration: confirm Sari's verdict is APPROVED
python eval/test_e2e_sari.py
# Expected: [PASS] compliance.status is APPROVED or APPROVED_WITH_CONDITIONS
```

---

## Iteration Guidance

- **Adding a new rule:** implement as a deterministic rewriter in
  `compliance.py`, add a unit test in `test_compliance.py`, and update
  the `_flags` / `_status` logic in `run_compliance()`.
- **Do not move rule enforcement to an LLM.** The speed benefit is minor;
  the auditability loss is significant for a regulated product.
- **Softening the copy:** if the rewritten text sounds clunky, improve the
  `_RETURN_REPLACEMENT` / `_GUARANTEE_REPLACEMENT` strings. They are
  constants at the top of `compliance.py`.
