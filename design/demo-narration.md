# Naik — Demo Narration Script (2:00)

**Narrator:** Allen · **Run:** Sari, end-to-end · **App language:** Bahasa Indonesia · **Narration:** English
**Hard rule:** if it runs over 2:00 in rehearsal, cut from the *italic* "stretch" lines first — they are marked.

Speaking pace assumed ~140 wpm. Word counts per beat are noted so you can verify timing without a stopwatch on every run. Total spoken ≈ 265 words (≈ 240 if both *stretch* lines are cut); the remaining seconds are the click/load pauses, which is why it lands at 2:00 not 1:50.

---

## Beat 0 — Problem (0:00 → 0:15) · ~35 words

> [ON SCREEN: landing page, Naik logo]
>
> "Forty million Indonesians earn irregular, gig-based income. When a flood shuts the road, an ojek driver's earnings stop that day — and no robo-advisor or insurer talks to that reality. Naik does. Meet Sari."

**[ACTION at 0:13]** Click **"Use Sari"** → navigate to `/intake`.

---

## Beat 1 — Sari + voice intake (0:15 → 0:45) · ~56 words

> [ON SCREEN: /intake, voice button, 90-second countdown]
>
> "Sari is 26, an ojek driver in Penjaringan — one of Jakarta's most flood-prone districts. She earns about six million rupiah a month, but it swings week to week. She's Muslim and wants halal-only investing. She just speaks to Naik, in her own words."

**[ACTION at 0:30]** Press the voice button → play **cached Sari intake** (do not rely on live mic — see fallback).

> *(stretch, cut first)* "Notice the transcript appearing live — this is the OpenAI Realtime API, Indonesian."

**[ACTION at 0:43]** Transcript complete → click submit → `/loading`.

> **Fallback (say only if live voice stalls):** "I'll use our cached intake so we stay on time" — then hit **Use cached audio**. Do not debug live.

---

## Beat 2 — Diagnostic + priority gap (0:45 → 1:15) · ~70 words

> [ON SCREEN: /results, WellnessRadar — risk_management spoke highlighted]
>
> "Naik scores seven dimensions of financial wellness from her spending and her words. Look at the shape: she actually saves well — growth and liquidity are strong. But risk management sits at twenty-six out of a hundred. That's the gap. Sari isn't bad with money — one flood week erases it. So Naik leads with protection, not products."

> *(stretch, cut first)* "Each spoke is grounded in real transaction patterns, not a questionnaire."

---

## Beat 3 — Fund recommendation (1:15 → 1:35) · ~48 words

> [ON SCREEN: three FundCards]
>
> "For investing, Naik ranks OJK-licensed funds against her profile. Top pick: Trimegah Kas Syariah — a money-market fund. The one-line reason: her income is irregular and she wants halal, so Naik weights low-risk pasar-uang syariah over equities. Every fund here is sharia-compliant, by her choice."

---

## Beat 4 — Insurance, income-protection framing (1:35 → 1:55) · ~48 words

> [ON SCREEN: InsuranceCard — trigger prominent]
>
> "Then the part nobody offers her: income protection. If rainfall in Penjaringan hits 150 millimetres in 24 hours, this pays out automatically — no claim form. Nine hundred twenty-five thousand rupiah per event, for about forty-seven thousand a week. It covers lost earnings, not a damaged phone."

---

## Beat 5 — Compliance gate (1:55 → 2:00) · ~12 words

> [ON SCREEN: ComplianceBadge green + "Konfirmasi manual diperlukan"]
>
> "And nothing executes without Sari's confirmation — OJK general guidance, by design."

**[END 2:00]**

---

## Timing ladder (for the stopwatch run)

| Beat | Ends at | Cumulative budget |
|------|---------|-------------------|
| 0 Problem | 0:15 | 0:15 |
| 1 Sari + voice | 0:45 | 0:30 |
| 2 Diagnostic | 1:15 | 0:30 |
| 3 Fund | 1:35 | 0:20 |
| 4 Insurance | 1:55 | 0:20 |
| 5 Compliance | 2:00 | 0:05 |

## Numbers locked to the pipeline (do not ad-lib different figures)

- Priority gap: **risk_management = 26.4 / 100** (lowest of 7).
- Top fund: **Trimegah Kas Syariah** (pasar uang / money-market, sharia-compliant).
- Premium: **Rp 202,471 / month ≈ Rp 46,724 / week.** Payout: **Rp 925,000 / event.**
- Trigger: **rainfall ≥ 150 mm / 24h, Penjaringan.**
- `next_step = confirm_both`; `requires_human_confirmation = True`.

> If a judge challenges a number, quote the monthly premium (Rp 202,471) — that is the schema-billed figure the form issues; the weekly figure is the same premium expressed per week.

## Rehearsal checklist

1. Run twice, timed. If > 2:00, cut the two *stretch* lines (Beat 1, Beat 2) — recovers ~8s.
2. Confirm cached audio is wired before rehearsing; never rehearse on live mic.
3. Q&A handoff: Hilda = agents, Xinyue = backend, Sher Min = eval.
