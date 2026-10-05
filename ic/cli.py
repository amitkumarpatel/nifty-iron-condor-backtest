"""
Per-run variant options for the entry scripts, so a test needs no environment variables:

    --strike-set NAME   sold strikes from data/strike_sets/strikes_NAME.csv   (= IC_STRIKE_SET)
    --hedge N           bought legs N points beyond the sold legs            (= IC_HEDGE_WIDTH)
    --filter X          10-day trend filter limit in %, or `off`             (= IC_TREND_FILTER)

They are turned into the environment variables ic/config.py already reads, so this must run before
anything imports ic.config. backtest.py and export_prices.py also get a report name of their own for a
variant (output/<prefix>_<set>_h<width>[_nofilter].xlsx) unless --out is given, so a test never overwrites
the main report.
"""
import os
import sys

OPTIONS = {"--strike-set": "IC_STRIKE_SET", "--hedge": "IC_HEDGE_WIDTH", "--filter": "IC_TREND_FILTER"}


def preset(out_prefix=None):
    argv, used, i = sys.argv, {}, 1
    while i < len(argv):
        name, eq, val = argv[i].partition("=")
        if name in OPTIONS:
            if not eq:
                if i + 1 >= len(argv):
                    raise SystemExit(f"{name} needs a value")
                val = argv.pop(i + 1)
            argv.pop(i)
            os.environ[OPTIONS[name]] = used[name] = val
        else:
            i += 1
    if out_prefix and used and not any(a == "--out" or a.startswith("--out=") for a in argv):
        parts = [out_prefix, used.get("--strike-set") or "sm", f"h{os.environ.get('IC_HEDGE_WIDTH', 'default')}"]
        f = used.get("--filter")
        if f:
            parts.append("nofilter" if f.lower() == "off" else f"filter{f}")
        out_dir = os.environ.get("IC_OUTPUT_DIR") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
        argv += ["--out", os.path.join(out_dir, "_".join(parts) + ".xlsx")]
