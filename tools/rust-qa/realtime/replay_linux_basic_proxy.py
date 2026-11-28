"""Validate the original request sequence from the archived Linux Basic proxy trial."""

from collections import Counter
import json
from pathlib import Path
import sys


def replay(cases):
    expected = {("signed", "anonymous"), ("signed", "correct"), ("signed", "incorrect"),
                ("rust", "anonymous"), ("rust", "correct")}
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
        if mode == "incorrect":
            assert not case["eventObserved"] and not case["inventorySucceeded"]
            assert all(r["kind"] == "proxy" for r in rows)
            assert [(r["operation"], r["credentials"], r["status"]) for r in proxy] == [
                (op, creds, "407") for op in ("inventory", "pollingGET") for creds in ("absent", "incorrect")]
            continue
        assert case["eventObserved"] and case["inventorySucceeded"]
        counts = Counter(r["operation"] for r in proxy if r["status"] == "allow")
        assert counts.keys() == {"inventory", "pollingGET", "pollingPOST", "connect"}
        assert counts["inventory"] >= 1 and all(counts[k] == 1 for k in ("pollingGET", "pollingPOST", "connect"))
        if mode == "correct":
            assert [(r["operation"], r["credentials"], r["status"]) for r in proxy] == [
                (op, creds, status) for op in ("inventory", "pollingGET", "pollingPOST", "connect")
                for creds, status in (("absent", "407"), ("correct", "allow"))]
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
    replay(json.loads(Path(sys.argv[1]).read_text())["cases"])
    print("Five archived Linux Basic proxy observations passed.")
