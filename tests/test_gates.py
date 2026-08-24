import sys, os
from datetime import date
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from quorum.gates import Leg, Proposal, Limits, evaluate, worst_case_loss, net_premium

F=P=0
def chk(n,g,w):
    global F,P
    if g==w: P+=1; print(f"  PASS  {n}")
    else: F+=1; print(f"  FAIL  {n}: {g!r} != {w!r}")

EXP=date(2026,9,4); L=Limits(); ACC=100_000.0
def ev(p, used=0.0, today_used=0.0, npos=0):
    return evaluate(p, L, today=date(2026,8,28), premium_used_usd=used,
                    premium_today_usd=today_used, open_positions=npos, account_usd=ACC)

print("-- long call: verlies = premie, punt --")
lc=Proposal("SPY",[Leg("call",640,1,6.50,EXP)],"TOM long",contracts=5)
chk("netto premie $3250", net_premium(lc), 3250.0)
chk("worst case = premie", worst_case_loss(lc), 3250.0)
chk("goedgekeurd", ev(lc).approved, True)

print("-- naked short call: CATEGORISCH verboden --")
ns=Proposal("SPY",[Leg("call",650,-1,4.00,EXP)],"premie schrijven",contracts=5)
v=ev(ns)
chk("afgewezen", v.approved, False)
chk("reden noemt naked", any("naked" in r for r in v.reasons), True)

print("-- debit spread: verlies begrensd tot netto debit --")
ds=Proposal("SPY",[Leg("call",640,1,6.50,EXP),Leg("call",650,-1,3.00,EXP)],"spread",contracts=5)
chk("netto debit $1750", net_premium(ds), 1750.0)
chk("worst case = debit", round(worst_case_loss(ds),2), 1750.0)
chk("goedgekeurd", ev(ds).approved, True)

print("-- limieten --")
big=Proposal("SPY",[Leg("call",640,1,6.50,EXP)],"te groot",contracts=100)
chk("dagcap 8% blokkeert $65k", ev(big).approved, False)
chk("totaalcap blokkeert bij $33k gebruikt", ev(lc, used=33_000).approved, False)
chk("positielimiet blokkeert bij 4 open", ev(lc, npos=4).approved, False)
chk("onbekende onderliggende geweigerd",
    ev(Proposal("TSLA",[Leg("call",300,1,5.0,EXP)],"x")).approved, False)
chk("expiratie na flat-datum geweigerd",
    ev(Proposal("SPY",[Leg("call",640,1,6.5,date(2026,9,11))],"x")).approved, False)

print("-- de belofte die we in de pitch doen --")
worst = sum(worst_case_loss(Proposal("SPY",[Leg("call",640,1,6.50,EXP)],"x",contracts=c))
            for c in (5,5,5))
chk("drie posities: verlies telt netjes op", worst, 9750.0)
chk("en blijft onder de 35%-cap", worst < 0.35*ACC, True)

print(f"\n{P} passed, {F} failed")
raise SystemExit(1 if F else 0)
