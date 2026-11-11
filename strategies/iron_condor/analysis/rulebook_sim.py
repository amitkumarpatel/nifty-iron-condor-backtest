import os, sys, pandas as pd, numpy as np
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
from strategies.iron_condor import config as C, engine as E
from strategies.iron_condor.common import contract_key, lot_size, load_calendar, time_exit_day
from shared import spread_sim as _spread_sim
class S:   # shared simulator with the condor's exit DTE (C.EXIT_DTE, read at call time)
    run = staticmethod(lambda *a, **k: _spread_sim.run(*a, **{"exit_dte": C.EXIT_DTE, **k}))
from strategies.iron_condor.analysis import pcs_lib as L
C.EXIT_DTE=18
REF=L.REF
CL=pd.read_csv("data/shared/nifty_daily.csv",parse_dates=["date"]).set_index("date").close.sort_index()
D30=pd.read_csv("data/iron_condor/strike_sets/strikes_d30_2019_2020.csv")
P20={}
for n in ("d20_skip","d20_rest","d20_2019_2020","d20_icm","d20_icm_2019_2020"):
    f=pd.read_csv(f"data/iron_condor/strike_sets/strikes_{n}.csv"); P20.update(dict(zip(f[f.opt_type=="PE"].trade_id,f[f.opt_type=="PE"].strike)))
def usable(exp,k,o,e):
    px,q,m=E.price_at(contract_key(exp,k,o),e,C.ENTRY_TIME)
    return px if (px is not None and not (q=="AFTER" and abs(m)>C.MAX_AFTER_MIN_AT_ENTRY)) else None
def cover(exp,k,o,e,x):
    cal=load_calendar(e,x); tx=time_exit_day(x,cal); need=[d for d in cal if e<=d<=tx]
    f=os.path.join(str(C.CACHE_DIR),contract_key(exp,k,o)); have=set(z[:-4] for z in os.listdir(f)) if os.path.isdir(f) else set()
    return sum(str(d) in have for d in need)/len(need)
def side(exp,o,k,w,e,x):
    out=1 if o=="CE" else -1
    tries=[(k,k+out*w)]+[(k+out*s,k+out*(s+w)) for s in C.FALLBACK_SHIFTS]+[(k,k+out*(w+z)) for z in C.FALLBACK_HEDGE_EXTRA]
    for ks,kb in tries:
        a,b=usable(exp,ks,o,e),usable(exp,kb,o,e)
        if a and b and b<a and min(cover(exp,ks,o,e,x),cover(exp,kb,o,e,x))>=0.9: return ks,kb
    return None
def month(t):
    e=pd.Timestamp(REF.entry_date[t]).date(); x=pd.Timestamp(REF.expiry[t]).date()
    p=CL[CL.index<pd.Timestamp(e)]; mv=(p.iloc[-1]/p.iloc[-11]-1)*100; mv5=(p.iloc[-1]/p.iloc[-6]-1)*100
    if t<1000: ce,pe=int(REF.sell_ce[t]),int(REF.sell_pe[t])
    else:
        s=D30[D30.trade_id==t].set_index("opt_type").strike; ce,pe=int(s.get("CE",REF.sell_ce[t])),int(s.get("PE",REF.sell_pe[t]))
    return e,x,p.iloc[-1],mv,mv5,ce,pe,P20.get(t)
def condor(t,e,x,ce,pe,w,tp):
    exp=str(x); a=side(exp,"CE",ce,w,e,x); b=side(exp,"PE",pe,w,e,x)
    if not a or not b: return None
    legs=[(-1,"CE",a[0]),(1,"CE",a[1]),(-1,"PE",b[0]),(1,"PE",b[1])]; q=lot_size(x)
    r0=S.run(e,exp,legs,q); cr=-r0["entry_val"]; width=max(a[1]-a[0],b[0]-b[1])
    if tp is None: return dict(cr=cr,width=width)
    r=S.run(e,exp,legs,q,tp_pts=tp*cr,sl_pts=cr); return dict(cr=cr,width=width,net=r["net"],reason=r["reason"],legs=legs)
def pcs(t,e,x,k,w):
    exp=str(x); a=side(exp,"PE",int(k),w,e,x)
    if not a: return None
    legs=[(-1,"PE",a[0]),(1,"PE",a[1])]; q=lot_size(x); cr=-S.run(e,exp,legs,q)["entry_val"]
    r=S.run(e,exp,legs,q,tp_pts=0.5*cr,sl_pts=cr); return dict(cr=cr,net=r["net"],reason=r["reason"],legs=legs)
def rnd(v): return max(100,int(round(v/100)*100))
def rulebook(t,widths):
    e,x,spot,mv,mv5,ce,pe,p20=month(t); ww,wn,wp=widths(spot)
    d=dict(trade_id=t,entry=e,spot=round(spot),move=round(mv,2),mv5=round(mv5,2),w_wide=ww,w_norm=wn,w_pcs=wp)
    sig=condor(t,e,x,ce,pe,ww,None)
    d["cw"]=round(sig["cr"]/ww*100,1) if sig else np.nan
    if abs(mv)<=2 and sig and d["cw"]>=45:   r=condor(t,e,x,ce,pe,ww,0.60); d["trade"]=f"IC {ww}"
    elif abs(mv)<=2 and sig and d["cw"]>=40: r=condor(t,e,x,ce,pe,wn,0.50); d["trade"]=f"IC {wn}"
    elif mv>2.5 and mv5<=1:                  r=None; d["trade"]="skip (5-day)"
    elif p20 is not None:                    r=pcs(t,e,x,p20,wp); d["trade"]=f"PCS {wp}"
    else: r=None; d["trade"]="no strikes"
    if r is None and d["trade"].startswith(("IC","PCS")): d["trade"]+=" (no price)"
    d["net"]=r["net"] if r else np.nan; d["reason"]=r["reason"] if r else ""
    return d
