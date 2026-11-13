#!/usr/bin/env python3
"""Build the chat edition of the forward-test skill (for Claude chat / mobile) from the repo config.

Run from the repo root:  python .claude/skills/nifty-ic-forward-test/chat_edition/build_chat_skill.py
Writes   .claude/skills/nifty-ic-forward-test/chat_edition/dist/nifty-ic-chat/  (SKILL.md + scripts/ic_chat.py)
and the upload file  .claude/skills/nifty-ic-forward-test/chat_edition/nifty-ic-chat.zip
Rebuild and re-upload whenever the rules, lot size or NSE holiday list change (e.g. each December).
"""
import csv
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
from strategies.iron_condor import config as c  # noqa: E402

TEMPLATE_JOURNAL = HERE.parent / "assets" / "forward_trades_template.csv"


def values():
    cols = next(csv.reader(open(TEMPLATE_JOURNAL)))
    return dict(
        built=dt.date.today().isoformat(),
        entry_time=c.ENTRY_TIME, check_time=c.CHECK_TIME, entry_dte=int(c.ENTRY_DTE), exit_dte=int(c.EXIT_DTE),
        expiry_weekday=str(c.EXPIRY_WEEKDAY), lookback=int(c.TREND_LOOKBACK_DAYS), target_delta=0.30,
        hedge_width=int(c.HEDGE_WIDTH), tp=float(c.TP_FRACTION), sl=float(c.SL_FRACTION),
        earlier_limit_pct=float(c.SKIP_IF_10D_MOVE_PCT),
        fwd_signal_width=int(c.FWD_SIGNAL_WIDTH), fwd_wide_widths=[int(w) for w in c.FWD_WIDE_WIDTHS],
        fwd_wide_move_pct=float(c.FWD_WIDE_MOVE_PCT), fwd_wide_min_credit_pct=float(c.FWD_WIDE_MIN_CREDIT_PCT),
        fwd_narrow_move_pct=float(c.FWD_NARROW_MOVE_PCT), fwd_min_credit_pct=float(c.FWD_MIN_CREDIT_PCT),
        fwd_wide_tp=float(c.FWD_WIDE_TP_FRACTION), fwd_pcs_delta=float(c.FWD_PCS_DELTA),
        fwd_pcs_widths=[int(w) for w in c.FWD_PCS_WIDTHS], fwd_pcs_alt_widths=[int(w) for w in c.FWD_PCS_ALT_WIDTHS],
        fwd_pcs_rise_pct=float(c.FWD_PCS_RISE_PCT), fwd_pcs_min_5d_pct=float(c.FWD_PCS_MIN_5D_PCT),
        fwd_pcs_tp=float(c.FWD_PCS_TP_FRACTION),
        fallback_shifts=[int(x) for x in c.FALLBACK_SHIFTS], fallback_hedge_extra=[int(x) for x in c.FALLBACK_HEDGE_EXTRA],
        lot_sizes=[[str(a), int(b)] for a, b in c.LOT_SIZES if str(a) >= "2025-01-01"],
        holidays=sorted(str(h) for h in getattr(c, "NSE_HOLIDAYS", [])),
        muhurat_days=sorted(str(h) for h in c.MUHURAT_DAYS if str(h) >= "2025-01-01"),
        risk_free_rate=float(c.RISK_FREE_RATE), div_yield=float(getattr(c, "DIV_YIELD", 0.0)),
        journal_cols=cols,
    )


def main():
    v = values()
    dist = HERE / "dist" / "nifty-ic-chat"
    if dist.exists():
        shutil.rmtree(dist)
    (dist / "scripts").mkdir(parents=True)
    script = (HERE / "ic_chat_template.py").read_text().replace("__CONFIG_JSON__", json.dumps(v, indent=1))
    (dist / "scripts" / "ic_chat.py").write_text(script)
    rules = subprocess.run([sys.executable, str(dist / "scripts" / "ic_chat.py"), "rules"], capture_output=True, text=True,
                           check=True).stdout.splitlines()[1:-1]
    md = (HERE / "SKILL_template.md").read_text().replace("__BUILT__", v["built"])
    md = md.replace("__RULES__", "\n".join("- " + r.strip() for r in rules if r.strip()))
    (dist / "SKILL.md").write_text(md)
    zp = HERE / "nifty-ic-chat.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(dist.rglob("*")):
            if f.is_file():
                z.write(f, Path("nifty-ic-chat") / f.relative_to(dist))
    print(f"built {dist} and {zp} (values from config, {v['built']})")


if __name__ == "__main__":
    main()
