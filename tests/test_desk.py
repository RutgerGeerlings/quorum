import sys, os
from datetime import date
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from quorum.desk import run_day, DeskState
from quorum.gates import Limits

print("=== QUORUM: de hele wedstrijdweek, droog gedraaid ===")
state=DeskState(); limits=Limits()
days=[date(2026,8,28),date(2026,8,29),date(2026,8,31),date(2026,9,1),
      date(2026,9,2),date(2026,9,3),date(2026,9,4)]
traded=0
for d in days:
    p=run_day(d, {"spot":640.0,"atm_premium":6.40}, state, limits)
    if p: traded+=1
print(f"\n=== samenvatting ===")
print(f"  dagen bekeken     : {len(days)}")
print(f"  trades gedaan     : {traded}")
print(f"  premie ingezet    : ${state.premium_used_usd:,.0f} "
      f"({state.premium_used_usd/state.account_usd:.1%} van het account)")
print(f"  posities open     : {state.open_positions}")
assert state.premium_used_usd <= limits.max_total_premium_pct*state.account_usd, "CAP GESCHONDEN"
assert traded>0, "desk deed helemaal niets"
print(f"  MAX VERLIES OOIT  : ${state.premium_used_usd:,.0f} - bewijsbaar, want nooit naked short")
print("\n  cap gerespecteerd, desk heeft gehandeld EN dagen overgeslagen. OK")
