import pandas as pd


def detect_loss_intent(war: pd.DataFrame, extreme_gap: float = 500_000) -> pd.DataFrame:
    """
    Loss Intent Detection (rule-based MVP).
    Membaca pola serangan competitor, bukan menebak biaya.

    Output kolom:
      - competitor_intent: MARKET_GRAB / BAIT / SIGNAL / DEFENSIVE_PRICE / NOISE
      - intent_note: penjelasan singkat (audit-friendly)
    """

    out = war.copy()

    # Banyak SKU yang sedang ATTACK (indikasi skala serangan)
    attack_skus = out[out.get("status") == "ATTACK"]["product_id"].nunique() if "status" in out.columns else 0

    intents = []
    notes = []

    for _, r in out.iterrows():
        status = r.get("status")
        gap = r.get("gap_price")
        impact = r.get("impact_level")

        intent = "NOISE"
        note = "Tidak ada indikasi serangan harga yang bermakna."

        # Jika bukan ATTACK atau gap tidak valid → NOISE
        if status != "ATTACK" or gap is None or pd.isna(gap):
            intent = "NOISE"
            note = "Bukan kondisi ATTACK atau data gap tidak tersedia."
        else:
            # ATTACK dengan gap ekstrem tapi hanya 1 SKU → pancingan
            if gap >= extreme_gap and attack_skus == 1:
                intent = "BAIT / SIGNAL"
                note = f"Gap ekstrem (≥{int(extreme_gap):,}) namun hanya 1 SKU diserang → pancingan/umpan."
            # ATTACK gap masuk akal dan banyak SKU → market grab
            elif gap < extreme_gap and attack_skus >= 2:
                intent = "MARKET_GRAB"
                note = "Serangan multi-SKU dengan gap masih masuk akal → indikasi ambil market."
            # ATTACK gap masuk akal, impact rendah/menengah → defensive price
            elif gap < extreme_gap and impact in ["LOW", "MED"]:
                intent = "DEFENSIVE_PRICE"
                note = "Serangan terbatas dan impact tidak tinggi → kemungkinan harga defensif/normal."
            else:
                intent = "NOISE"
                note = "Pola tidak cukup kuat untuk disimpulkan sebagai market grab atau bait."

        intents.append(intent)
        notes.append(note)

    out["competitor_intent"] = intents
    out["intent_note"] = notes
    return out
