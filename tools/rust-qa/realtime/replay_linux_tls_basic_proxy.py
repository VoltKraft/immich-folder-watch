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


def check_cases(cases, fixed, digest_capable=False):
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
        elif case["client"] == "signed" or digest_capable:
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


def check_digest(cases, digest_capable):
    modes = {f"digest-{scheme}{policy}{password}"
             for scheme in ("sha256", "md5") for policy in ("", "-legacy") for password in ("", "-incorrect")}
    assert Counter((c["client"], c["mode"]) for c in cases) == {
        (client, mode): 1 for client in ("signed", "candidate") for mode in modes}
    for case in cases:
        rows, mode = case["observations"], case["mode"]
        assert case["procExit"] == 0 and case["netDevices"] == [[1, "lo"]]
        assert not any(row["kind"] == "handlerError" for row in rows)
        outer = [row for row in rows if row["kind"] == "connect"]
        assert outer and all(not row["apiHeader"] for row in outer)
        counts = Counter((row["credentials"], row["digestUri"], row["status"]) for row in outer)
        initial = counts.pop(("absent", None, 407))
        assert initial >= 2
        signed = case["client"] == "signed"
        accepted = "incorrect" not in mode and ("legacy" in mode if signed else digest_capable)
        if signed:
            comparison = "incorrect" if "incorrect" in mode else "correct" if accepted else "target-mismatch"
            assert counts == {(comparison, "root", 200 if accepted else 407): initial}
        elif digest_capable:
            assert not case["fixtureRejection"]
            outcome = ("correct", "authority", 200) if accepted else ("incorrect", "authority", 407)
            assert counts == {outcome: initial}
        else:
            assert not counts
        assert case["inventory"] == case["event"] == accepted
        if accepted:
            check_session(rows, tunneled=True)
        else:
            assert rows == outer


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--baseline", action="store_true", help="compare the original preemptive client")
    mode.add_argument("--digest-reference", action="store_true", help="check the signed Digest reference and Basic-only candidate")
    mode.add_argument("--digest", action="store_true", help="require the authority-bound Digest candidate response")
    mode.add_argument("--basic-with-digest", action="store_true", help="check the ten Basic cases with a Digest-capable candidate")
    args = parser.parse_args()
    report = json.loads(args.receipt.read_text())
    if args.digest_reference or args.digest:
        check_digest(report["cases"], digest_capable=args.digest)
        print("Verified sixteen original TLS Digest observations.")
    else:
        check_cases(report["cases"], fixed=not args.baseline, digest_capable=args.basic_with_digest)
        print("Verified the ten original TLS proxy observations.")
