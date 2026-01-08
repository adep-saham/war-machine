import pandas as pd


def _to_float(x, default=None):
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return default
        return float(x)
    except Exception:
        return default


def generate_counter_moves(
    war: pd.DataFrame,
    max_discount_pct: float = 0.02,   # batas diskon “aman” untuk rekomendasi (bukan guardrail)
    base_duration_days: int = 5
) -> pd.DataFrame:
    """
    Counter-Move Generator (rule-based, audit-friendly).
    Output kolom:
      - counter_move
      - counter_move_short
      - counter_channel
      - counter_duration_days
      - counter_rationale

    Menggunakan sinyal:
      status, guardrail_status, competitor_intent, compete_decision,
      gap_price, impact_level, market_share_pct, share_at_risk_pct
    """

    out = war.copy()

    moves = []
    shorts = []
    channels = []
    durations = []
    rationales = []

    for _, r in out.iterrows():
        status = r.get("status")
        guard = r.get("guardrail_status")
        intent = r.get("competitor_intent")
        dcz = r.get("compete_decision")
        impact = r.get("impact_level")

        gap = _to_float(r.get("gap_price"), default=0.0)
        share = _to_float(r.get("market_share_pct"), default=0.0)
        risk = _to_float(r.get("share_at_risk_pct"), default=0.0)

        # default: no move
        move = "HOLD – Monitor"
        short = "HOLD"
        channel = "All"
        duration = base_duration_days
        rationale = "Tidak ada tekanan harga signifikan atau diputuskan tidak agresif."

        # 0) DCZ LET_GO → jangan bakar margin
        if dcz == "LET_GO":
            move = "LET GO (DCZ) – Tidak perang harga. Fokus produk lain."
            short = "DCZ"
            channel = "—"
            duration = 0
            rationale = f"DCZ aktif ({intent}). Menghindari perang harga yang tidak memberi leverage."

        else:
            # 1) Jika bukan ATTACK, tetap punya opsi ofensif ringan (opsional)
            if status != "ATTACK":
                if impact == "HIGH":
                    move = "DEFEND – Jaga value: stok, SLA, edukasi, dan loyalty"
                    short = "DEFEND"
                    channel = "All"
                    duration = base_duration_days
                    rationale = "Impact tinggi, tetapi tidak sedang kalah harga. Prioritas mempertahankan pengalaman & ketersediaan."
                else:
                    move = "HOLD – Monitor (no action)"
                    short = "HOLD"
                    channel = "All"
                    duration = base_duration_days
                    rationale = "Tidak kalah harga dan impact bukan prioritas."

            # 2) ATTACK cases
            else:
                # 2a) ATTACK + BLOCKED → non-price counter move (promo/benefit)
                if guard == "BLOCKED":
                    # gunakan risk untuk mengatur agresivitas
                    if impact == "HIGH" or risk >= 5:
                        move = "PROMO VALUE – Cashback + Free Ongkir (Online) + Limited Time"
                        short = "VALUE PROMO"
                        channel = "Online"
                        duration = 7
                        rationale = "Harga tidak bisa diturunkan (guardrail). Impact/risk tinggi → kompensasi value untuk menahan migrasi."
                    elif intent == "MARKET_GRAB":
                        move = "BUNDLING – Bundle pecahan + bonus kecil (Online/Store) + duration pendek"
                        short = "BUNDLE"
                        channel = "Online/Store"
                        duration = 5
                        rationale = "Serangan market grab tapi harga terblokir → bundling untuk meningkatkan perceived value tanpa turunkan price tag."
                    else:
                        move = "PROMO RINGAN – Cashback kecil / Voucher member (Online)"
                        short = "LIGHT PROMO"
                        channel = "Online"
                        duration = 3
                        rationale = "Guardrail blocked, impact sedang/rendah → promo ringan agar tidak mengorbankan margin."

                # 2b) ATTACK + ALLOWED → price ladder + response shaping
                else:
                    # rekomendasi diskon berdasarkan gap
                    # gap kecil: match tipis, gap sedang: 1% ladder, gap besar: 2% ladder (dibatasi max_discount_pct)
                    if gap <= 25_000:
                        move = "MATCH – Turunkan tipis (≤0.5%) untuk parity"
                        short = "MATCH"
                        channel = "All"
                        duration = 3
                        rationale = "Gap tipis → cukup parity cepat, hindari spiral perang harga."
                    elif gap <= 75_000:
                        move = "LADDER – Turunkan ~1% (bertahap) + monitoring 24–48 jam"
                        short = "LADDER 1%"
                        channel = "All"
                        duration = 5
                        rationale = "Gap sedang → gunakan ladder agar bisa berhenti jika kompetitor ikut turun."
                    else:
                        disc = min(max_discount_pct, 0.02)  # cap di 2% secara default
                        move = f"LADDER – Turunkan ~{int(disc*100)}% + opsi promo kecil"
                        short = f"LADDER {int(disc*100)}%"
                        channel = "All"
                        duration = 7
                        rationale = "Gap besar → perlu langkah lebih tegas, namun tetap bertahap agar fleksibel terhadap respon kompetitor."

                    # tambahan shaping berdasarkan intent
                    if intent == "BAIT / SIGNAL":
                        move = "HOLD / VALUE – Jangan terpancing, fokus benefit non-price"
                        short = "ANTI-BAIT"
                        channel = "Online"
                        duration = 3
                        rationale = "Intent terdeteksi bait/signal → respon non-price lebih aman daripada turun harga."

        moves.append(move)
        shorts.append(short)
        channels.append(channel)
        durations.append(duration)
        rationales.append(rationale)

    out["counter_move"] = moves
    out["counter_move_short"] = shorts
    out["counter_channel"] = channels
    out["counter_duration_days"] = durations
    out["counter_rationale"] = rationales

    return out
