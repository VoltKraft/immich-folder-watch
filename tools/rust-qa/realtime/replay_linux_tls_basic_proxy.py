"""Replay credential placement and client outcomes on the original HTTPS sockets."""

from collections import Counter
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit


def check_session(rows, tunneled):
    inner = [r for r in rows if r["kind"] == "inner"]
    assert len(inner) >= 4 and all(r["tls"] == "TLSv1.3" and r["apiHeader"] and not r["proxyHeader"] for r in inner)
    assert {r["route"] for r in inner} == {"tunnel" if tunneled else "direct"}
    connections = {r["subjectPort"] for r in inner}
    if tunneled:
        assert connections == {r["subjectPort"] for r in rows if r["kind"] == "connect" and r["status"] == 200}
    requests = [r for r in rows if r["kind"] == "request"]
    assert all(r["synthetic"] and r["source"] == "127.0.0.1" for r in requests)
    assert Counter(r["id"] for r in requests) == Counter(r["subjectPort"] for r in inner)
    operations = []
    for req in requests:
        url = urlsplit(req["path"])
        if url.path == "/collection/api/albums":
            operations.append("inventory")
            continue
        assert url.path == "/socket.io/"
        query = parse_qs(url.query)
        operations.append(query["transport"][0] + req["method"])
    assert set(operations) == {"inventory", "pollingGET", "pollingPOST", "websocketGET"}
    assert all(operations.count(k) == 1 for k in ("pollingGET", "pollingPOST", "websocketGET"))
    events = [r for r in rows if r["kind"] == "sent" and r["body"].startswith("42/collection,")]
    closed = [r for r in rows if r["kind"] == "echo-close"]
    assert len(events) == len(closed) == 1 and events[0]["id"] == closed[0]["id"] and closed[0]["body"].startswith("03e8")
    assert json.loads(events[0]["body"].split(",", 1)[1])[0] == "on_album_update"


def check_cases(cases, fixed):
    modes = {"anonymous", "correct", "incorrect", "other-scheme", "bypass"}
    assert len(cases) == 10 and {(c["client"], c["mode"]) for c in cases} == {
        (client, mode) for client in ("signed", "candidate") for mode in modes}
    for case in cases:
        rows = case["observations"]
        assert case["procExit"] == 0 and not case["fixtureRejection"] and case["netDevices"] == [[1, "lo"]]
        assert not any(row["kind"] == "handlerError" for row in rows)
        outer = [r for r in rows if r["kind"] == "connect"]
        assert all(not r["apiHeader"] for r in outer)
        attempts = Counter((r["credentials"], r["status"]) for r in outer)
        mode = case["mode"]
        if mode in ("anonymous", "correct", "bypass"):
            assert case["event"] and case["inventory"]
            check_session(rows, mode != "bypass")
        else:
            assert not case["event"] and not case["inventory"] and rows == outer
        if mode == "bypass":
            assert not outer
        elif mode == "anonymous":
            assert attempts.keys() == {("absent", 200)}
        elif case["client"] == "signed":
            supplied = {"correct": ("correct", 200), "incorrect": ("incorrect", 407),
                        "other-scheme": ("digest", 407)}[mode]
            assert attempts.keys() == {("absent", 407), supplied}
            assert attempts["absent", 407] == attempts[supplied] >= 2
        elif fixed:
            if mode == "other-scheme":
                assert attempts.keys() == {("absent", 407)} and attempts["absent", 407] >= 2
            else:
                supplied = ("correct", 200) if mode == "correct" else ("incorrect", 407)
                assert attempts.keys() == {("absent", 407), supplied}
                assert attempts["absent", 407] == attempts[supplied] >= 2
        else:
            supplied = {"correct": ("correct", 200), "incorrect": ("incorrect", 407),
                        "other-scheme": ("correct", 407)}[mode]
            assert attempts.keys() == {supplied} and attempts[supplied] >= 2


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--baseline", action="store_true", help="compare the original preemptive client")
    args = parser.parse_args()
    report = json.loads(args.receipt.read_text())
    check_cases(report["cases"], fixed=not args.baseline)
    print("Verified the ten original TLS proxy observations.")
