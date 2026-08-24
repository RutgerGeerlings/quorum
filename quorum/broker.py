"""Alpaca-laag: Trading API, CLI en MCP — alle drie, want de jury noemt ze alle drie apart.

Ontwerpkeuze: dit is één interface met drie transporten, geen drie losse implementaties.
  - TradingAPI : REST, voor alles waar je een antwoord op moet wachten (ketens, orders, posities)
  - CLI        : voor de langlopende sessies en cron - Alpaca positioneert de CLI hier zelf voor
  - MCP        : de tool-oppervlakte die de LLM-agents zien

De MCP-descriptors staan hier omdat de agents alleen mógen wat hier gedefinieerd is. Een agent
kan geen order plaatsen die niet door een gate is gekomen, want de enige weg naar buiten loopt
via submit_proposal() en die roept gates.evaluate() aan. Dat is geen belofte in een prompt maar
een eigenschap van de code.

Alles draait in DRY_RUN zonder credentials, zodat de hele desk testbaar is zonder API-key.
"""
from __future__ import annotations
import json
import os
import subprocess
from dataclasses import dataclass, asdict
from datetime import date
from typing import Any, Dict, List, Optional

from .gates import Proposal, Limits, Verdict, evaluate, net_premium

PAPER_BASE = "https://paper-api.alpaca.markets"
DATA_BASE = "https://data.alpaca.markets"


@dataclass
class Fill:
    symbol: str
    qty: int
    avg_price: float
    order_id: str
    status: str


class AlpacaBroker:
    """Eén interface, drie transporten. transport='api' | 'cli' | 'mcp'."""

    def __init__(self, key: str = "", secret: str = "", *, dry_run: bool = True,
                 transport: str = "api"):
        self.key = key or os.environ.get("ALPACA_API_KEY", "")
        self.secret = secret or os.environ.get("ALPACA_SECRET_KEY", "")
        self.dry_run = dry_run or not (self.key and self.secret)
        self.transport = transport
        self.sent: List[Dict[str, Any]] = []      # audit trail, ook in dry run

    # ---- REST ---------------------------------------------------------------------------
    def _headers(self) -> Dict[str, str]:
        return {"APCA-API-KEY-ID": self.key, "APCA-API-SECRET-KEY": self.secret,
                "Content-Type": "application/json"}

    def _get(self, base: str, path: str) -> Any:
        if self.dry_run:
            return {"_dry_run": True, "path": path}
        import urllib.request
        req = urllib.request.Request(base + path, headers=self._headers())
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())

    def account(self) -> Dict[str, Any]:
        return self._get(PAPER_BASE, "/v2/account")

    def option_chain(self, underlying: str, expiry: date) -> Any:
        """Opties-keten. Hier kiest de Trader zijn echte strikes op echte premies -
        de Strateeg werkt met een schatting, de Trader met de markt."""
        return self._get(DATA_BASE,
                         f"/v1beta1/options/snapshots/{underlying}"
                         f"?expiration_date={expiry.isoformat()}&feed=indicative")

    # ---- CLI ----------------------------------------------------------------------------
    def cli(self, *args: str) -> Dict[str, Any]:
        """Alpaca CLI met JSON-output. Gebruikt voor de nachtelijke sessies en cron-taken,
        waar een MCP-server zwaarder is dan nodig."""
        cmd = ["alpaca", *args, "--output", "json"]
        if self.dry_run:
            self.sent.append({"transport": "cli", "cmd": cmd})
            return {"_dry_run": True, "cmd": cmd}
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            raise RuntimeError(f"alpaca cli faalde: {p.stderr[:200]}")
        return json.loads(p.stdout or "{}")

    # ---- MCP ----------------------------------------------------------------------------
    @staticmethod
    def mcp_tools() -> List[Dict[str, Any]]:
        """Het tool-oppervlak dat de LLM-agents zien. Bewust KLEIN gehouden.

        Merk op wat er NIET in staat: er is geen place_order. De enige weg naar de markt is
        submit_proposal(), en die dwingt de gates af. Een agent die 'toch even een order plaatst'
        bestaat hier niet, omdat het gereedschap er niet is."""
        return [
            {"name": "get_calendar_context",
             "description": "Vandaag: handelsdag, turn-of-month, NFP, resterende dagen."},
            {"name": "get_market_state",
             "description": "Spot, VIX-termijnstructuur, trend t.o.v. 200MA."},
            {"name": "get_option_chain",
             "description": "Ketens met bid/ask/IV voor een onderliggende en expiratie."},
            {"name": "get_desk_state",
             "description": "Premie gebruikt, posities open, resterend budget onder de gates."},
            {"name": "submit_proposal",
             "description": ("Dien een optievoorstel in. Gaat ALTIJD langs de deterministische "
                             "risk gates; een afwijzing is definitief en niet te overrulen.")},
        ]

    # ---- de enige weg naar buiten -------------------------------------------------------
    def submit_proposal(self, p: Proposal, limits: Limits, *, today: date,
                        premium_used_usd: float, premium_today_usd: float,
                        open_positions: int, account_usd: float) -> tuple[Verdict, Optional[Fill]]:
        """Poortwachter én uitvoerder. Er is geen andere manier om een order te plaatsen."""
        v = evaluate(p, limits, today=today, premium_used_usd=premium_used_usd,
                     premium_today_usd=premium_today_usd,
                     open_positions=open_positions, account_usd=account_usd)
        if not v.approved:
            self.sent.append({"rejected": True, "reasons": v.reasons,
                              "proposal": p.underlying, "thesis": p.thesis})
            return v, None
        order = self._build_order(p)
        self.sent.append({"transport": self.transport, "order": order})
        if self.dry_run:
            px = sum(abs(l.premium) for l in p.legs)
            return v, Fill(p.underlying, p.contracts, px, "dry-run", "accepted")
        raise NotImplementedError("live execution wordt tijdens het hackathon-venster aangezet")

    @staticmethod
    def _build_order(p: Proposal) -> Dict[str, Any]:
        """Alpaca multi-leg (Level 3) order. Eén leg -> simple, meerdere -> mleg."""
        legs = [{"symbol": f"{p.underlying}{l.expiry:%y%m%d}"
                           f"{'C' if l.right == 'call' else 'P'}{int(l.strike*1000):08d}",
                 "side": "buy" if l.qty > 0 else "sell",
                 "ratio_qty": abs(l.qty)} for l in p.legs]
        return {"order_class": "simple" if len(legs) == 1 else "mleg",
                "qty": str(p.contracts), "type": "limit", "time_in_force": "day",
                "limit_price": f"{abs(net_premium(p))/100/max(p.contracts,1):.2f}",
                "legs": legs}
