import sys, os
from datetime import date
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from quorum.broker import AlpacaBroker
from quorum.gates import Leg, Proposal, Limits

F=P=0
def chk(n,g,w):
    global F,P
    if g==w: P+=1; print(f"  PASS  {n}")
    else: F+=1; print(f"  FAIL  {n}: {g!r} != {w!r}")

EXP=date(2026,9,4); b=AlpacaBroker(dry_run=True); L=Limits()
def sub(p, used=0.0, npos=0):
    return b.submit_proposal(p, L, today=date(2026,8,28), premium_used_usd=used,
                             premium_today_usd=0.0, open_positions=npos, account_usd=100_000.0)

print("-- drie transporten aanwezig --")
chk("dry_run zonder credentials", b.dry_run, True)
chk("CLI bouwt json-commando", b.cli("account","get")["cmd"][:2], ["alpaca","account"])
chk("CLI vraagt json-output", "--output" in b.cli("positions","list")["cmd"], True)

print("-- MCP tool-oppervlak --")
names=[t["name"] for t in AlpacaBroker.mcp_tools()]
chk("submit_proposal bestaat", "submit_proposal" in names, True)
chk("place_order bestaat NIET", "place_order" in names, False)
chk("5 tools", len(names), 5)

print("-- de enige weg naar buiten dwingt de gates af --")
ok=Proposal("SPY",[Leg("call",640,1,6.40,EXP)],"TOM",contracts=5)
v,f=sub(ok)
chk("geldig voorstel gaat door", v.approved, True)
chk("levert een fill", f is not None, True)
naked=Proposal("SPY",[Leg("call",650,-1,4.0,EXP)],"premie schrijven",contracts=5)
v,f=sub(naked)
chk("naked short geweigerd", v.approved, False)
chk("geen fill bij weigering", f, None)
chk("weigering staat in de audit trail", b.sent[-1]["rejected"], True)

print("-- OCC-symbool en order-opbouw --")
o=AlpacaBroker._build_order(ok)
chk("simple bij 1 leg", o["order_class"], "simple")
chk("OCC-symbool klopt", o["legs"][0]["symbol"], "SPY260904C00640000")
sp=Proposal("SPY",[Leg("call",640,1,6.4,EXP),Leg("call",650,-1,3.0,EXP)],"spread",contracts=5)
chk("mleg bij 2 legs", AlpacaBroker._build_order(sp)["order_class"], "mleg")

print(f"\n{P} passed, {F} failed")
raise SystemExit(1 if F else 0)
