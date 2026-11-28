"""Validate the original request sequence from the archived Linux Basic proxy trial."""

from collections import Counter
import json
from pathlib import Path
import sys


def verify_retries(proxy, operations, credential, status):
    assert {r["operation"] for r in proxy} == set(operations)
    for op in operations:
        attempts = [(r["credentials"], r["status"]) for r in proxy if r["operation"] == op]
        assert len(attempts) >= 2 and len(attempts) % 2 == 0
        assert attempts == [("absent", "407"), (credential, status)] * (len(attempts) // 2)


def replay(cases, candidate=False):
    expected = {("signed", "anonymous"), ("signed", "correct"), ("signed", "incorrect"),
                ("rust", "anonymous"), ("rust", "correct")}
    if candidate:
        expected.update(("candidate", mode) for mode in ("anonymous", "correct", "incorrect", "connect-only", "other-scheme"))
    assert len(cases) == len(expected) and {(c["client"], c["mode"]) for c in cases} == expected
    for case in cases:
        client, mode = case["client"], case["mode"]
        rows = case["observations"]
        assert case["netDevices"] == [[1, "lo"]]
        assert all(r["kind"] != "handlerError" for r in rows)
        proxy = [r for r in rows if r["kind"] == "proxy"]
        assert all(r["apiKey"] == (r["operation"] != "connect") for r in proxy)
        assert all(r["synthetic"] for r in rows if r["kind"] == "request")
        if (client, mode) == ("rust", "correct"):
            assert not rows and case["fixtureProtocolRejected"] and case["exitCode"] == 1
            assert not any(case[k] for k in ("eventObserved", "inventorySucceeded", "stopped"))
            continue
        assert case["exitCode"] == 0 and case["stopped"] and not case["fixtureProtocolRejected"]
        if mode == "other-scheme":
            assert not case["eventObserved"] and not case["inventorySucceeded"]
            assert rows == proxy and {r["operation"] for r in proxy} == {"inventory", "pollingGET"}
            assert all(r["credentials"] == "absent" and r["status"] == "407" for r in proxy)
            continue
        if mode == "connect-only":
            assert not case["eventObserved"] and case["inventorySucceeded"]
            assert not any(r["kind"] == "innerUpgrade" for r in rows)
            direct = [r for r in proxy if r["operation"] != "connect"]
            assert {r["operation"] for r in direct} == {"inventory", "pollingGET", "pollingPOST"}
            assert all(r["credentials"] == "absent" and r["status"] == "allow" for r in direct)
            connect = [r for r in proxy if r["operation"] == "connect"]
            assert len(connect) == 2
            verify_retries(connect, ["connect"], "incorrect", "407")
            continue
        if mode == "incorrect":
            assert not case["eventObserved"] and not case["inventorySucceeded"]
            assert all(r["kind"] == "proxy" for r in rows)
            verify_retries(proxy, ["inventory", "pollingGET"], "incorrect", "407")
            continue
        assert case["eventObserved"] and case["inventorySucceeded"]
        counts = Counter(r["operation"] for r in proxy if r["status"] == "allow")
        assert counts.keys() == {"inventory", "pollingGET", "pollingPOST", "connect"}
        assert counts["inventory"] >= 1 and all(counts[k] == 1 for k in ("pollingGET", "pollingPOST", "connect"))
        if mode == "correct":
            verify_retries(proxy, ["inventory", "pollingGET", "pollingPOST", "connect"], "correct", "allow")
        else:
            assert all(r["status"] == "allow" and r["credentials"] == "absent" for r in proxy)
        upgrades = [r for r in rows if r["kind"] == "innerUpgrade"]
        assert upgrades == [{"kind": "innerUpgrade", "proxyHeader": False, "apiKey": True}]
        sent = [r for r in rows if r["kind"] == "sent" and r["body"].startswith("42/collection,")]
        assert len(sent) == 1 and json.loads(sent[0]["body"].split(",", 1)[1])[0] == "on_album_update"
        socket_id = sent[0]["id"]
        closed = [r for r in rows if r["kind"] == "echo-close"]
        assert len(closed) == 1 and closed[0]["body"].startswith("03e8") and closed[0]["id"] == socket_id
        assert any(r["kind"] == "received" and r["id"] == socket_id and r["body"] == "41/collection," for r in rows)


if __name__ == "__main__":
    report = json.loads(Path(sys.argv[1]).read_text())
    replay(report["cases"], "candidateBinarySha256" in report)
    print(f"Validated {len(report['cases'])} archived Linux proxy observations.")
