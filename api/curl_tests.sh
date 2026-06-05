#!/usr/bin/env bash
# api/curl_tests.sh — Curl every deployed Flask endpoint with real-shaped payloads.
#
# Block 1 (Xinyue): integration smoke-test for the deployed Render backend.
# Each call prints the HTTP status, response time, and a one-line verdict.
# Non-200 responses print the full body so you can diagnose schema mismatches.
#
# Usage:
#   # Against local dev server
#   bash api/curl_tests.sh
#
#   # Against deployed Render backend
#   API_BASE=https://naik-api.onrender.com bash api/curl_tests.sh
#
#   # Verbose: print full response JSON for every call
#   VERBOSE=1 API_BASE=https://naik-api.onrender.com bash api/curl_tests.sh

set -euo pipefail

API_BASE="${API_BASE:-http://localhost:5050}"
VERBOSE="${VERBOSE:-0}"
GATE_SECS="${GATE_SECS:-10}"       # build-plan SLA

PASS=0
FAIL=0

# ── Sari's minimal valid payload ──────────────────────────────────────────── #
# voice_transcript satisfies the _require_a_signal validator without needing
# a full 70-transaction history. This is the "real-shaped" payload Xinyue uses.
SARI_PAYLOAD='{
  "user_id": "sari-curl-smoke",
  "age": 26,
  "monthly_income_idr": 6000000,
  "kecamatan": "Penjaringan",
  "city": "Jakarta",
  "risk_tolerance": "conservative",
  "household_size": 2,
  "is_gig_worker": true,
  "investment_horizon_years": 5.0,
  "financial_goals": ["perlindungan penghasilan", "dana darurat"],
  "voice_transcript": "Saya tidak punya asuransi apa pun. Saya kerja sebagai driver ojek online, jadi kalau banjir dan saya tidak bisa keluar, penghasilan saya langsung berhenti. Saya menabung sedikit, tapi sering tergoda checkout kalau ada diskon.",
  "transactions": []
}'

# ── Bad payloads for error-path validation ────────────────────────────────── #
BAD_MISSING_FIELD='{"user_id":"bad","age":26,"kecamatan":"Penjaringan","risk_tolerance":"conservative","voice_transcript":"test"}'
BAD_AGE='{"user_id":"bad","age":5,"monthly_income_idr":5000000,"kecamatan":"Penjaringan","risk_tolerance":"conservative","voice_transcript":"test"}'
BAD_NO_SIGNAL='{"user_id":"bad","age":26,"monthly_income_idr":5000000,"kecamatan":"Penjaringan","risk_tolerance":"conservative","voice_transcript":"","transactions":[]}'

SEP="────────────────────────────────────────────────────────────────"

# ── Helpers ───────────────────────────────────────────────────────────────── #
check() {
    local name="$1" got_status="$2" want_status="$3" elapsed="$4" body="$5"
    local ok="PASS" gate_ok=""

    if [ "$got_status" != "$want_status" ]; then
        ok="FAIL"
        FAIL=$((FAIL + 1))
    else
        PASS=$((PASS + 1))
    fi

    # Timing check (only for 200 responses)
    if [ "$want_status" = "200" ]; then
        elapsed_int="${elapsed%.*}"
        if [ "${elapsed_int:-0}" -ge "$GATE_SECS" ] 2>/dev/null; then
            gate_ok=" ⚠ SLOW (${elapsed}s > ${GATE_SECS}s)"
        else
            gate_ok=" (${elapsed}s)"
        fi
    fi

    printf "  [%s]  %-52s HTTP %s%s\n" "$ok" "$name" "$got_status" "$gate_ok"

    if [ "$ok" = "FAIL" ] || [ "${VERBOSE:-0}" = "1" ]; then
        echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
        echo
    fi
}

post() {
    local url="$1" data="$2"
    local result status elapsed body
    result=$(curl -sS -X POST "$url" \
        -H "Content-Type: application/json" \
        -d "$data" \
        -w "\n%{http_code}\n%{time_total}" \
        --max-time 60 \
        2>/dev/null)
    body=$(echo "$result" | head -n -2)
    status=$(echo "$result" | tail -n 2 | head -n 1)
    elapsed=$(echo "$result" | tail -n 1)
    echo "$status|$elapsed|$body"
}

get() {
    local url="$1"
    local result status elapsed body
    result=$(curl -sS -X GET "$url" \
        -w "\n%{http_code}\n%{time_total}" \
        --max-time 15 \
        2>/dev/null)
    body=$(echo "$result" | head -n -2)
    status=$(echo "$result" | tail -n 2 | head -n 1)
    elapsed=$(echo "$result" | tail -n 1)
    echo "$status|$elapsed|$body"
}

parse() { echo "$1" | cut -d'|' -f"$2"; }

# ── Tests ─────────────────────────────────────────────────────────────────── #
echo "═══════════════════════════════════════════════════════════════"
echo "  Naik curl integration tests"
echo "  Target: $API_BASE"
echo "═══════════════════════════════════════════════════════════════"

# --- GET /health -------------------------------------------------------------
echo
echo "GET /health"
echo "$SEP"
r=$(get "$API_BASE/health")
check "/health → 200" "$(parse "$r" 1)" "200" "$(parse "$r" 2)" "$(parse "$r" 3)"
# Check db key
body=$(parse "$r" 3)
db_val=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('db','?'))" 2>/dev/null)
echo "      db=$db_val"

# --- GET /eval-summary -------------------------------------------------------
echo
echo "GET /eval-summary"
echo "$SEP"
r=$(get "$API_BASE/eval-summary")
check "/eval-summary → 200" "$(parse "$r" 1)" "200" "$(parse "$r" 2)" "$(parse "$r" 3)"
if [ "${VERBOSE:-0}" = "1" ]; then
    parse "$r" 3 | python3 -m json.tool 2>/dev/null
fi

# --- POST /diagnostic --------------------------------------------------------
echo
echo "POST /diagnostic (Sari)"
echo "$SEP"
r=$(post "$API_BASE/diagnostic" "$SARI_PAYLOAD")
check "/diagnostic → 200" "$(parse "$r" 1)" "200" "$(parse "$r" 2)" "$(parse "$r" 3)"
gap=$(echo "$(parse "$r" 3)" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('priority_gap','?'))" 2>/dev/null)
echo "      priority_gap=$gap (expected: risk_management)"
if [ "$gap" != "risk_management" ]; then
    echo "      ✗ WRONG priority_gap — schema or scoring drift"
    FAIL=$((FAIL + 1))
fi

# --- POST /wealth ------------------------------------------------------------
echo
echo "POST /wealth (Sari)"
echo "$SEP"
r=$(post "$API_BASE/wealth" "$SARI_PAYLOAD")
check "/wealth → 200" "$(parse "$r" 1)" "200" "$(parse "$r" 2)" "$(parse "$r" 3)"
picks=$(echo "$(parse "$r" 3)" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('picks',[])))" 2>/dev/null)
echo "      picks=$picks (expected: ≥1)"

# --- POST /insurance ---------------------------------------------------------
echo
echo "POST /insurance (Sari)"
echo "$SEP"
r=$(post "$API_BASE/insurance" "$SARI_PAYLOAD")
check "/insurance → 200" "$(parse "$r" 1)" "200" "$(parse "$r" 2)" "$(parse "$r" 3)"
kec=$(echo "$(parse "$r" 3)" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('trigger',{}).get('kecamatan','?'))" 2>/dev/null)
echo "      trigger.kecamatan=$kec (expected: Penjaringan)"
if [ "$kec" != "Penjaringan" ]; then
    echo "      ✗ KECAMATAN MISMATCH — trigger not using persona's district"
    FAIL=$((FAIL + 1))
fi

# --- POST /compliance --------------------------------------------------------
echo
echo "POST /compliance (Sari)"
echo "$SEP"
r=$(post "$API_BASE/compliance" "$SARI_PAYLOAD")
check "/compliance → 200" "$(parse "$r" 1)" "200" "$(parse "$r" 2)" "$(parse "$r" 3)"
is_general=$(echo "$(parse "$r" 3)" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('is_general_guidance','?'))" 2>/dev/null)
echo "      is_general_guidance=$is_general (expected: True)"

# --- POST /orchestrate (the headline) ----------------------------------------
echo
echo "POST /orchestrate (Sari) — the SLA gate"
echo "$SEP"
r=$(post "$API_BASE/orchestrate" "$SARI_PAYLOAD")
status=$(parse "$r" 1)
elapsed=$(parse "$r" 2)
body=$(parse "$r" 3)
check "/orchestrate → 200" "$status" "200" "$elapsed" "$body"

if [ "$status" = "200" ]; then
    ns=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('next_step','?'))" 2>/dev/null)
    dnhm=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('compliance',{}); print(c.get('requires_human_confirmation','?'))" 2>/dev/null)
    disclaimers=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('disclaimers',[])))" 2>/dev/null)
    echo "      next_step=$ns  human_confirm=$dnhm  disclaimers=$disclaimers"

    # Contract assertions on FinalResponse shape
    for field in wellness wealth insurance compliance narrative next_step disclaimers; do
        present=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok' if '$field' in d else 'MISSING')" 2>/dev/null)
        if [ "$present" != "ok" ]; then
            echo "      ✗ FinalResponse missing field: $field"
            FAIL=$((FAIL + 1))
        fi
    done
fi

# --- Validation error paths --------------------------------------------------
echo
echo "Validation error paths"
echo "$SEP"

r=$(post "$API_BASE/orchestrate" "$BAD_MISSING_FIELD")
check "missing monthly_income_idr → 422" "$(parse "$r" 1)" "422" "" ""

r=$(post "$API_BASE/orchestrate" "$BAD_AGE")
check "age=5 → 422" "$(parse "$r" 1)" "422" "" ""

r=$(post "$API_BASE/diagnostic" "$BAD_NO_SIGNAL")
check "no signal (empty transcript + no txns) → 422" "$(parse "$r" 1)" "422" "" ""

# --- Content-type and method handling ----------------------------------------
echo
echo "HTTP method / content-type handling"
echo "$SEP"
r=$(curl -sS -X POST "$API_BASE/orchestrate" \
    -H "Content-Type: text/plain" \
    -d "not json" \
    -w "\n%{http_code}" \
    --max-time 10 2>/dev/null)
status=$(echo "$r" | tail -1)
check "text/plain body → 415" "$status" "415" "" ""

status=$(curl -sS -o /dev/null -w "%{http_code}" -X GET "$API_BASE/orchestrate" --max-time 10 2>/dev/null)
check "GET /orchestrate → 405" "$status" "405" "" ""

status=$(curl -sS -o /dev/null -w "%{http_code}" -X GET "$API_BASE/nope" --max-time 10 2>/dev/null)
check "GET /nope → 404" "$status" "404" "" ""

# ── Summary ───────────────────────────────────────────────────────────────── #
echo
echo "═══════════════════════════════════════════════════════════════"
printf "  RESULT: %d passed, %d failed\n" "$PASS" "$FAIL"
echo "═══════════════════════════════════════════════════════════════"
echo

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
