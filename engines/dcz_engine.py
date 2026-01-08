import pandas as pd


def apply_dont_compete_zone(war: pd.DataFrame) -> pd.DataFrame:
    """
    Don't Compete Zone (DCZ)
    Menentukan keputusan strategis:
      - FIGHT  : wajib dilawan
      - HOLD   : pantau, jangan agresif
      - LET_GO : sengaja tidak dilawan (DCZ)

    Output kolom:
      - compete_decision
      - dcz_reason
    """

    out = war.copy()

    decisions = []
    reasons = []

    for _, r in out.iterrows():
        status = r.get("status")
        impact = r.get("impact_level")
        intent = r.get("competitor_intent")
        share = r.get("market_share_pct")
        blocked = r.get("guardrail_status") == "BLOCKED"

        decision = "HOLD"
        reason = "Pantau kondisi, tidak perlu aksi agresif."

        # 1️⃣ BAIT / SIGNAL → JANGAN TERPANCING
        if intent == "BAIT / SIGNAL":
            decision = "LET_GO"
            reason = "Harga kompetitor terindikasi pancingan (bait)."

        # 2️⃣ Impact LOW + share kecil → KORBANKAN
        elif impact == "LOW" and share is not None and share < 5:
            decision = "LET_GO"
            reason = "Impact rendah dan market share kecil (korban strategis)."

        # 3️⃣ BLOCKED + impact tidak tinggi → JANGAN DIPAKSA
        elif blocked and impact in ["LOW", "MED"]:
            decision = "HOLD"
            reason = "Harga terblokir guardrail, impact tidak kritikal."

        # 4️⃣ Impact HIGH → WAJIB FIGHT
        elif impact == "HIGH":
            decision = "FIGHT"
            reason = "Impact tinggi terhadap market share."

        # 5️⃣ MARKET GRAB → LAWAN
        elif intent == "MARKET_GRAB":
            decision = "FIGHT"
            reason = "Kompetitor agresif ambil market (market grab)."

        decisions.append(decision)
        reasons.append(reason)

    out["compete_decision"] = decisions
    out["dcz_reason"] = reasons
    return out
