import pandas as pd

def load_sales_internal():
    try:
        return pd.read_csv("data/sales_internal.csv", parse_dates=["date"])
    except:
        return pd.DataFrame()

def load_market_size():
    try:
        return pd.read_csv("data/market_size.csv", parse_dates=["date"])
    except:
        return pd.DataFrame()
