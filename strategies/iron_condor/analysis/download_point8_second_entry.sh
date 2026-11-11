#!/usr/bin/env bash
# Point 8: a second entry two weeks after the normal one (Monday 4 weeks before the expiry week, 28-31 DTE),
# same expiry and rules: ~30-delta condor with 400 and 300-pt hedges, 20-delta put spread with 200 and 300-pt hedges.
# Trade set w4 (data/iron_condor/reference/ic_trades_w4.csv, 90 trades, id = EXPIRY month YYMM; the first-entry trade with the
# same expiry is the pair). Needs today's Breeze session (python shared/scripts/login_url.py first).
#
#   bash strategies/iron_condor/analysis/download_point8_second_entry.sh 18    # part 1: strikes + candles to the 18-DTE time exit (do this first)
#   bash strategies/iron_condor/analysis/download_point8_second_entry.sh 7     # part 2: extra candles to a 7-DTE exit (strikes reused)
#
# Restart-safe: cached data is skipped. If the daily limit stops it, run the same command again tomorrow.
set -euo pipefail
cd "$(dirname "$0")/../../.."
source .venv/bin/activate

EXIT="${1:-}"
[[ "$EXIT" == "18" || "$EXIT" == "7" ]] || { echo "Usage: bash strategies/iron_condor/analysis/download_point8_second_entry.sh 18|7"; exit 1; }
SS=data/iron_condor/strike_sets

if [[ ! -f $SS/strikes_d30_w4.csv || ! -f $SS/strikes_d20_w4.csv ]]; then
  [[ "$EXIT" == "18" ]] || { echo "Run part 1 (18) first - the strikes are picked there."; exit 1; }
  echo "=== Step 1: pick the strikes at the second entry (up to ~2,000 API calls) ==="
  [[ -f $SS/strikes_d30_w4.csv ]] || python strategies/iron_condor/scripts/select_strikes.py --trade-set w4 --ce-delta 0.30 --pe-delta 0.30 --around 3 --step 50 --name d30_w4
  python strategies/iron_condor/scripts/select_strikes.py --trade-set w4 --pe-delta 0.20 --around 3 --step 50 --name d20_w4
  # keep the put-spread run's call side on the condor's strikes (cached by the condor download, no extra calls)
  python - <<'PY'
import pandas as pd
f = "data/iron_condor/strike_sets/strikes_d20_w4.csv"
new = pd.read_csv(f); ce = pd.read_csv("data/iron_condor/strike_sets/strikes_d30_w4.csv")
ce = ce[(ce.opt_type == "CE") & ce.trade_id.isin(new.trade_id)]
pd.concat([new[new.opt_type == "PE"], ce]).sort_values(["trade_id", "opt_type"]).to_csv(f, index=False)
print(f"{f}: {len(new[new.opt_type == 'PE'])} puts + {len(ce)} calls (from d30_w4)")
PY
fi

dl() {   # dl <run options...>: the put-spread runs keep the call side on the condor's 400-pt strikes
  if [[ "$*" == *"d20_w4"* ]]; then IC_HEDGE_WIDTH_CE=400 python strategies/iron_condor/scripts/download.py --trade-set w4 "$@" --exit-dte "$EXIT"
  else python strategies/iron_condor/scripts/download.py --trade-set w4 "$@" --exit-dte "$EXIT"; fi
}
RUNS=(
  "--strike-set d30_w4 --hedge 400"
  "--strike-set d30_w4 --hedge 300"
  "--strike-set d20_w4 --hedge 200"
  "--strike-set d20_w4 --hedge 300"
)
echo
echo "=== Step 2: candle calls needed (exit ${EXIT} DTE) ==="
for r in "${RUNS[@]}"; do
  echo "--- $r"
  dl $r --dry-run | tail -1
done
echo "(Counts overlap: the sold legs are shared between runs, so the real total is lower. Limit 5,000 a day.)"
read -r -p "Download now? [y/N] " ok
[[ "$ok" == "y" || "$ok" == "Y" ]] || { echo "Stopped before downloading."; exit 0; }

echo
echo "=== Step 3: download (exit ${EXIT} DTE) ==="
for r in "${RUNS[@]}"; do
  echo "--- $r"
  dl $r
done
echo "Done. Tell Claude 'point 8 (${EXIT} DTE) data downloaded'."
