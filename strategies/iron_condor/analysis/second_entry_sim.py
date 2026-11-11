import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
import pandas as pd, numpy as np
from strategies.iron_condor.analysis import rulebook_sim as p7
from strategies.iron_condor import config as C
from shared import spread_sim as _spread_sim
class S:   # shared simulator with the condor's exit DTE (C.EXIT_DTE, read at call time)
    run = staticmethod(lambda *a, **k: _spread_sim.run(*a, **{"exit_dte": C.EXIT_DTE, **k}))
from strategies.iron_condor.common import lot_size
C.EXIT_DTE=18
CL=p7.CL
def readings(e):
    p=CL[CL.index<pd.Timestamp(e)]; return (p.iloc[-1]/p.iloc[-11]-1)*100,(p.iloc[-1]/p.iloc[-6]-1)*100,p.iloc[-1]
def run_rule(tid,e,x,ce,pe,p20,dte=18):
    C.EXIT_DTE=dte; exp=str(x); mv,mv5,spot=readings(e); q=lot_size(x)
    d=dict(trade_id=tid,entry=e,expiry=x,move=round(mv,2),mv5=round(mv5,2))
    sig=p7.condor(tid,e,x,ce,pe,400,None); d["cw"]=round(sig["cr"]/400*100,1) if sig else np.nan
    legs=None
    if abs(mv)<=2 and sig and d["cw"]>=45: w,tp,kind=400,0.6,"IC 400"
    elif abs(mv)<=2 and sig and d["cw"]>=40: w,tp,kind=300,0.5,"IC 300"
    elif mv>2.5 and mv5<=1: kind="skip (5-day)"
    elif p20 is not None and not pd.isna(p20): kind="PCS 200"
    else: kind="no strikes"
    if kind.startswith("IC"):
        a=p7.side(exp,"CE",ce,w,e,x); b=p7.side(exp,"PE",pe,w,e,x)
        if a and b: legs=[(-1,"CE",a[0]),(1,"CE",a[1]),(-1,"PE",b[0]),(1,"PE",b[1])]
    elif kind=="PCS 200":
        b=p7.side(exp,"PE",int(p20),200,e,x); tp=0.5
        if b: legs=[(-1,"PE",b[0]),(1,"PE",b[1])]
    d["trade"]=kind
    if legs:
        cr=-S.run(e,exp,legs,q)["entry_val"]; z=S.run(e,exp,legs,q,tp_pts=tp*cr,sl_pts=cr)
        d.update(credit=round(cr,1),net=z["net"],reason=z["reason"],exit=z["exit_day"],days=(z["exit_day"]-e).days)
    elif kind.startswith(("IC","PCS")): d["trade"]+=" (no price)"
    C.EXIT_DTE=18
    return d
def A_rows(dte=18):
    out=[]
    for t in p7.REF.index:
        if t==24: continue
        e,x,spot,mv,mv5,ce,pe,p20=p7.month(t); out.append(run_rule(t,e,x,ce,pe,p20,dte))
    return pd.DataFrame(out)
def B_rows(dte=18):
    W=pd.read_csv("data/iron_condor/reference/ic_trades_w4.csv").set_index("trade_id")
    s30=pd.read_csv("data/iron_condor/strike_sets/strikes_d30_w4.csv"); s20=pd.read_csv("data/iron_condor/strike_sets/strikes_d20_w4.csv")
    out=[]
    for t in W.index:
        e=pd.Timestamp(W.entry_date[t]).date(); x=pd.Timestamp(W.expiry[t]).date()
        s=s30[s30.trade_id==t].set_index("opt_type").strike
        ce,pe=int(s.get("CE",W.sell_ce[t])),int(s.get("PE",W.sell_pe[t]))
        p=s20[(s20.trade_id==t)&(s20.opt_type=="PE")].strike; p20=int(p.iloc[0]) if len(p) else None
        out.append(run_rule(t,e,x,ce,pe,p20,dte))
    return pd.DataFrame(out)
def stats(df,order="exit"):
    g=df.dropna(subset=["net"]).sort_values(order); s=g.net; eq=s.cumsum(); dd=(eq-eq.cummax().clip(lower=0)).min(); l=s[s<=0]
    yrs=g.groupby(pd.to_datetime(g.exit).dt.year).net.sum()
    return dict(n=len(s),net=round(s.sum()),W=int((s>0).sum()),L=len(l),dd=round(dd),worst=round(s.min()),PF=round(s[s>0].sum()/-l.sum(),2) if len(l) else None,lose_yrs=int((yrs<0).sum()))
