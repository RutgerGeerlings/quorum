from datetime import date
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from quorum.market_calendar import (is_trading_day, trading_days, is_turn_of_month,
                                    is_nfp_day, labor_day, days_until, calendar_context)

F=P=0
def chk(name, got, want):
    global F,P
    if got==want: P+=1; print(f"  PASS  {name}")
    else: F+=1; print(f"  FAIL  {name}: {got!r} != {want!r}")

print("-- feestdagen --")
chk("Labor Day 2026 = 7 sep", labor_day(2026), date(2026,9,7))
chk("Labor Day is geen handelsdag", is_trading_day(date(2026,9,7)), False)
chk("weekend is geen handelsdag", is_trading_day(date(2026,8,29)), False)
chk("gewone maandag wel", is_trading_day(date(2026,8,31)), True)

print("-- augustus 2026 --")
chk("21 handelsdagen", len(trading_days(2026,8)), 21)
chk("laatste = 31 aug", trading_days(2026,8)[-1], date(2026,8,31))

print("-- turn-of-month venster --")
for d,want in [(date(2026,8,25),False),(date(2026,8,26),True),(date(2026,8,27),True),
               (date(2026,8,28),True),(date(2026,8,31),True),(date(2026,9,1),True),
               (date(2026,9,2),True),(date(2026,9,3),True),(date(2026,9,4),False)]:
    chk(f"{d} TOM={want}", is_turn_of_month(d), want)

print("-- NFP --")
chk("4 sep 2026 is NFP", is_nfp_day(date(2026,9,4)), True)
chk("3 sep is dat niet", is_nfp_day(date(2026,9,3)), False)

print("-- wedstrijdvenster: 5 van de 6 dagen zijn TOM --")
hack=[d for d in trading_days(2026,8)+trading_days(2026,9) if date(2026,8,28)<=d<=date(2026,9,4)]
chk("6 handelsdagen in het venster", len(hack), 6)
chk("waarvan 5 TOM", sum(is_turn_of_month(d) for d in hack), 5)

print("-- resterende dagen --")
chk("28 aug -> 4 sep = 5 handelsdagen", days_until(date(2026,8,28), date(2026,9,4)), 5)
ctx=calendar_context(date(2026,8,31), date(2026,9,4))
chk("context TOM op 31 aug", ctx["turn_of_month"], True)
chk("context prior 9.0bp", ctx["tom_prior_bp_per_day"], 9.0)

print(f"\n{P} passed, {F} failed")
raise SystemExit(1 if F else 0)
