import pandas as pd

def format_idr(x):
    if pd.isna(x):
        return "-"
    try:
        return f"{int(x):,}".replace(",", ".")
    except:
        return "-"
