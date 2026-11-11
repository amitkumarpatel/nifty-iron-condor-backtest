#!/usr/bin/env bash
# Point 6: 15-delta and 25-delta sold puts for the put credit spread, in every month the forward-test
# condor rule skips (2021-26: 30 months, 2019-20: 20 months), with 200-pt and 300-pt hedges.
# Plus (for the walk-forward test, point 1): 20-delta puts in the 40 months the condor trades
# (2021-26: 36, 2019-20: 4), so months can switch between condor and put spread when thresholds move.
# Needs today's Breeze session (python shared/scripts/login_url.py first). Run from the repo root:
#     bash strategies/iron_condor/analysis/download_point6_put_deltas.sh
# Restart-safe: already cached candles are skipped, so it can be run again after a stop.
set -euo pipefail
cd "$(dirname "$0")/../../.."
source .venv/bin/activate
# Only the puts matter. Keep the call side on strikes that are already cached (30-delta calls, 300-pt hedge),
# so no API calls are spent on call legs.
export IC_HEDGE_WIDTH_CE=300

A="1 2 5 6 8 9 12 13 15 16 17 19 20 23 28 29 33 35 36 38 41 43 45 46 48 50 52 57 62 63"   # 2021-26 skipped months
C="3 4 7 10 11 14 18 21 22 25 26 27 30 31 32 34 37 39 40 42 44 47 49 51 53 54 55 56 58 59 60 61 64 65 66 67"  # 2021-26 condor months
E="1904 2001 2005 2008"   # 2019-20 condor months
B="1901 1902 1903 1905 1906 1907 1908 1909 1910 1911 1912 2002 2003 2004 2006 2007 2009 2010 2011 2012"  # 2019-20

echo "=== Step 1: pick the sold puts (about 130 API calls) ==="
for d in 15 25; do
  python strategies/iron_condor/scripts/select_strikes.py --trades $A --pe-delta 0.$d --around 3 --step 50 --name d${d}_pcs
  python strategies/iron_condor/scripts/select_strikes.py --trade-set 2019_2020 --trades $B --pe-delta 0.$d --around 3 --step 50 --name d${d}_pcs_2019_2020
  # 2019-20: copy the cached 30-delta call strikes into the new set (the trade file's own call strikes are not cached)
  python - "$d" <<'PY'
import sys, pandas as pd
d = sys.argv[1]; f = f"data/iron_condor/strike_sets/strikes_d{d}_pcs_2019_2020.csv"
new = pd.read_csv(f); ce = pd.read_csv("data/iron_condor/strike_sets/strikes_d30_2019_2020.csv")
ce = ce[(ce.opt_type == "CE") & ce.trade_id.isin(new.trade_id)]
pd.concat([new[new.opt_type == "PE"], ce]).sort_values(["trade_id", "opt_type"]).to_csv(f, index=False)
PY
done
# 20-delta puts in the condor months (walk-forward test)
python strategies/iron_condor/scripts/select_strikes.py --trades $C --pe-delta 0.20 --around 3 --step 50 --name d20_icm
python strategies/iron_condor/scripts/select_strikes.py --trade-set 2019_2020 --trades $E --pe-delta 0.20 --around 3 --step 50 --name d20_icm_2019_2020
python - <<'PY'
import pandas as pd
f = "data/iron_condor/strike_sets/strikes_d20_icm_2019_2020.csv"
new = pd.read_csv(f); ce = pd.read_csv("data/iron_condor/strike_sets/strikes_d30_2019_2020.csv")
ce = ce[(ce.opt_type == "CE") & ce.trade_id.isin(new.trade_id)]
pd.concat([new[new.opt_type == "PE"], ce]).sort_values(["trade_id", "opt_type"]).to_csv(f, index=False)
PY

echo
echo "=== Step 2: API calls needed for the candles ==="
for d in 15 25; do
  for h in 200 300; do
    echo "--- ${d}-delta, ${h}-pt hedge"
    python strategies/iron_condor/scripts/download.py --trades $A --strike-set d${d}_pcs --hedge $h --dry-run | tail -1
    python strategies/iron_condor/scripts/download.py --trade-set 2019_2020 --trades $B --strike-set d${d}_pcs_2019_2020 --hedge $h --dry-run | tail -1
  done
done
for h in 200 300; do
  echo "--- 20-delta in condor months, ${h}-pt hedge"
  python strategies/iron_condor/scripts/download.py --trades $C --strike-set d20_icm --hedge $h --dry-run | tail -1
  python strategies/iron_condor/scripts/download.py --trade-set 2019_2020 --trades $E --strike-set d20_icm_2019_2020 --hedge $h --dry-run | tail -1
done
echo "(The counts overlap: sold puts are shared between the 200 and 300-pt runs, so the real total is lower.)"
echo "Breeze limit: 5,000 calls a day. If the total is above that, run this script again tomorrow - cached data is skipped."
read -r -p "Download now, 200-pt hedges first, then 300-pt? [y/N] " ok
[[ "$ok" == "y" || "$ok" == "Y" ]] || { echo "Stopped before downloading."; exit 0; }

echo
echo "=== Step 3: download ==="
for h in 200 300; do
  for d in 15 25; do
    echo "--- ${d}-delta, ${h}-pt hedge"
    python strategies/iron_condor/scripts/download.py --trades $A --strike-set d${d}_pcs --hedge $h
    python strategies/iron_condor/scripts/download.py --trade-set 2019_2020 --trades $B --strike-set d${d}_pcs_2019_2020 --hedge $h
  done
done
for h in 200 300; do
  echo "--- 20-delta in condor months, ${h}-pt hedge"
  python strategies/iron_condor/scripts/download.py --trades $C --strike-set d20_icm --hedge $h
  python strategies/iron_condor/scripts/download.py --trade-set 2019_2020 --trades $E --strike-set d20_icm_2019_2020 --hedge $h
done
echo "Done. Tell Claude 'point 6 data downloaded'."
