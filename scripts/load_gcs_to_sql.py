#!/usr/bin/env python3
"""Load a CSV file into MySQL using batched INSERT via pymysql executemany."""

import argparse
import sys

import pandas as pd
import pymysql


def normalize_bigquery_csv_for_mysql(df):
    """BigQuery TIMESTAMP columns in CSV often end with ' UTC'. MySQL DATETIME rejects that suffix."""
    for col in df.columns:
        if df[col].dtype != object:
            continue

        def fix_cell(x):
            if pd.isna(x):
                return x
            if isinstance(x, str) and x.endswith(" UTC"):
                return x[: -len(" UTC")]
            return x

        df[col] = df[col].map(fix_cell)
    return df


def parse_args():
    p = argparse.ArgumentParser(description="Load CSV into MySQL in batches.")
    p.add_argument("--csv-file", required=True)
    p.add_argument("--host", required=True)
    p.add_argument("--db", required=True)
    p.add_argument("--user", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--table", required=True)
    p.add_argument("--chunk-size", type=int, default=500)
    return p.parse_args()


def main():
    args = parse_args()
    try:
        try:
            df = pd.read_csv(args.csv_file)
        except Exception as exc:
            print(f"read_csv failed: {exc}", file=sys.stderr)
            sys.exit(1)
        normalize_bigquery_csv_for_mysql(df)
        if df.empty:
            print("CSV has no rows; nothing to insert.", file=sys.stderr)
            sys.exit(1)
        columns = list(df.columns)
        placeholders = ", ".join(["%s"] * len(columns))
        col_sql = ", ".join([f"`{c}`" for c in columns])
        sql = f"INSERT INTO `{args.table}` ({col_sql}) VALUES ({placeholders})"
        try:
            conn = pymysql.connect(
                host=args.host,
                user=args.user,
                password=args.password,
                database=args.db,
                charset="utf8mb4",
                autocommit=False,
            )
        except Exception as exc:
            print(f"pymysql.connect failed: {exc}", file=sys.stderr)
            sys.exit(1)
        try:
            try:
                cur = conn.cursor()
            except Exception as exc:
                print(f"cursor failed: {exc}", file=sys.stderr)
                sys.exit(1)
            total = 0
            try:
                for start in range(0, len(df), args.chunk_size):
                    chunk = df.iloc[start : start + args.chunk_size]
                    rows = [tuple(row) for row in chunk.itertuples(index=False, name=None)]
                    try:
                        cur.executemany(sql, rows)
                    except Exception as exc:
                        print(f"executemany failed at offset {start}: {exc}", file=sys.stderr)
                        sys.exit(1)
                    total += len(rows)
                    print(f"Inserted chunk ending at row {total} ({len(rows)} rows in batch)")
                try:
                    conn.commit()
                except Exception as exc:
                    print(f"commit failed: {exc}", file=sys.stderr)
                    sys.exit(1)
            finally:
                try:
                    cur.close()
                except Exception:
                    pass
        finally:
            try:
                conn.close()
            except Exception as exc:
                print(f"close failed: {exc}", file=sys.stderr)
                sys.exit(1)
        print(f"Total rows inserted: {total}")
    except SystemExit:
        raise
    except Exception as exc:
        print(f"unexpected error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
