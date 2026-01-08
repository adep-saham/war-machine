import pandas as pd
import os

DATA_DIR = "data"

def safe_read_csv(filename):
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        return pd.read_csv(path)
    return None
