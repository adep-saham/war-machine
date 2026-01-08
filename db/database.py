import sqlite3
import pandas as pd

DB_PATH = "storage/gold_war_room.db"

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def read_df(sql, params=None):
    conn = get_conn()
    df = pd.read_sql_query(sql, conn, params=params or [])
    conn.close()
    return df

def insert_df(df, table):
    conn = get_conn()
    df.to_sql(table, conn, if_exists="append", index=False)
    conn.commit()
    conn.close()
