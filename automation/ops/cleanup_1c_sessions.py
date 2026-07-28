# -*- coding: utf-8 -*-
"""Terminate stale 1C sessions for a server infobase via rac/RAS.

This is intentionally separate from UI tests and update scripts: browser-based
checks often leave hibernated WebClient sessions that keep the limited test
license busy. The script targets one infobase and selected app ids only.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys


DEFAULT_RAS = "192.168.2.126:2545"
DEFAULT_CLUSTER_PORT = "2541"
DEFAULT_INFOBASE = "fresh-unf"
DEFAULT_RAC = r"C:\Program Files\1cv8\8.5.1.1150\bin\rac.exe"


def run_rac(rac: str, ras: str, args: list[str]) -> str:
    result = subprocess.run(
        [rac, ras] + args,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout


def parse_blocks(text: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    for raw_block in re.split(r"\r?\n\r?\n", text.strip()):
        item: dict[str, str] = {}
        for line in raw_block.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            item[key.strip()] = value.strip()
        if item:
            blocks.append(item)
    return blocks


def find_cluster(rac: str, ras: str, port: str) -> str:
    clusters = parse_blocks(run_rac(rac, ras, ["cluster", "list"]))
    for cluster in clusters:
        if cluster.get("port") == port:
            return cluster["cluster"]
    if len(clusters) == 1:
        return clusters[0]["cluster"]
    raise RuntimeError(f"Cluster with port {port} not found at {ras}")


def find_infobase(rac: str, ras: str, cluster: str, name: str) -> str:
    bases = parse_blocks(
        run_rac(rac, ras, ["infobase", "--cluster", cluster, "summary", "list"])
    )
    for base in bases:
        if base.get("name") == name:
            return base["infobase"]
    raise RuntimeError(f"Infobase {name!r} not found in cluster {cluster}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ras", default=os.getenv("RAS_ADDR", DEFAULT_RAS))
    parser.add_argument("--cluster-port", default=DEFAULT_CLUSTER_PORT)
    parser.add_argument("--infobase", default=DEFAULT_INFOBASE)
    parser.add_argument("--rac", default=os.getenv("RAC_EXE", DEFAULT_RAC))
    parser.add_argument(
        "--app-id",
        action="append",
        default=None,
        help="App id to terminate. May be passed multiple times. Default: WebClient.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    app_ids = set(args.app_id or ["WebClient"])
    cluster = find_cluster(args.rac, args.ras, args.cluster_port)
    infobase = find_infobase(args.rac, args.ras, cluster, args.infobase)
    sessions = parse_blocks(
        run_rac(args.rac, args.ras, ["session", "--cluster", cluster, "list"])
    )

    targets = [
        session
        for session in sessions
        if session.get("infobase") == infobase and session.get("app-id") in app_ids
    ]

    for session in targets:
        sid = session["session"]
        print(
            f"{'would terminate' if args.dry_run else 'terminate'} "
            f"{sid} id={session.get('session-id')} app={session.get('app-id')} "
            f"user={session.get('user-name')} started={session.get('started-at')}"
        )
        if not args.dry_run:
            run_rac(
                args.rac,
                args.ras,
                ["session", "terminate", "--cluster", cluster, "--session", sid],
            )

    print(f"terminated={0 if args.dry_run else len(targets)} matched={len(targets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
