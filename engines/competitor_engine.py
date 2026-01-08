def predict_competitor_response(row):
    if row["gap_price"] < 50000:
        return "Kompetitor kemungkinan ikut turunkan harga"
    return "Kompetitor relatif pasif"
