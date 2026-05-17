#!/usr/bin/env python3
"""Export a MySQL table to CSV using a server-side cursor for low memory use."""

import argparse
import csv
import sys

import pymysql


def parse_args():
    p = argparse.ArgumentParser(description="Export MySQL table to CSV with headers.")
    p.add_argument("--host", required=True)
    p.add_argument("--db", required=True)
    p.add_argument("--user", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--table", required=True)
    p.add_argument("--output", required=True)
    return p.parse_args()


def main():
    args = parse_args()
    row_count = 0
    conn = None
    cur = None
    try:
        try:
            conn = pymysql.connect(
                host=args.host,
                user=args.user,
                password=args.password,
                database=args.db,
                charset="utf8mb4",
            )
        except Exception as exc:
            print(f"pymysql.connect failed: {exc}", file=sys.stderr)
            sys.exit(1)
        try:
            cur = conn.cursor(pymysql.cursors.SSCursor)
        except Exception as exc:
            print(f"SSCursor failed: {exc}", file=sys.stderr)
            sys.exit(1)
        try:
            try:
                cur.execute(f"SELECT * FROM `{args.table}`")
            except Exception as exc:
                print(f"execute SELECT failed: {exc}", file=sys.stderr)
                sys.exit(1)
            try:
                colnames = [d[0] for d in cur.description]
            except Exception as exc:
                print(f"read description failed: {exc}", file=sys.stderr)
                sys.exit(1)
            try:
                fh = open(args.output, "w", newline="", encoding="utf-8")
            except OSError as exc:
                print(f"open output failed: {exc}", file=sys.stderr)
                sys.exit(1)
            try:
                try:
                    writer = csv.writer(fh)
                    try:
                        writer.writerow(colnames)
                    except Exception as exc:
                        print(f"write header failed: {exc}", file=sys.stderr)
                        sys.exit(1)
                    while True:
                        try:
                            batch = cur.fetchmany(1000)
                        except Exception as exc:
                            print(f"fetchmany failed: {exc}", file=sys.stderr)
                            sys.exit(1)
                        if not batch:
                            break
                        for row in batch:
                            try:
                                writer.writerow(row)
                            except Exception as exc:
                                print(f"write row failed: {exc}", file=sys.stderr)
                                sys.exit(1)
                            row_count += 1
                finally:
                    try:
                        fh.close()
                    except Exception as exc:
                        print(f"close file failed: {exc}", file=sys.stderr)
                        sys.exit(1)
            finally:
                try:
                    cur.close()
                except Exception as exc:
                    print(f"cursor close failed: {exc}", file=sys.stderr)
                    sys.exit(1)
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception as exc:
                print(f"connection close failed: {exc}", file=sys.stderr)
                sys.exit(1)
        print(f"Row count written: {row_count}")
    except SystemExit:
        raise
    except Exception as exc:
        print(f"unexpected error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
