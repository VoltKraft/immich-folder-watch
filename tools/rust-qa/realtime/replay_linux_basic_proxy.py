"""Validate the original request sequence from the archived Linux Basic proxy trial."""

from collections import Counter
import argparse
import json
from pathlib import Path


def verify_retries(proxy, operations, credential, status):
    assert {r["operation"] for r in proxy} == set(operations)
    for op in operations:
        attempts = [(r["credentials"], r["status"]) for r in proxy if r["operation"] == op]
        assert len(attempts) >= 2 and len(attempts) % 2 == 0
        assert attempts == [("absent", "407"), (credential, status)] * (len(attempts) // 2)


def verify_session(rows):
    upgrades = [r for r in rows if r["kind"] == "innerUpgrade"]
    assert upgrades == [{"kind": "innerUpgrade", "proxyHeader": False, "apiKey": True}]
    sent = [r for r in rows if r["kind"] == "sent" and r["body"].startswith("42/collection,")]
    assert len(sent) == 1 and json.loads(sent[0]["body"].split(",", 1)[1])[0] == "on_album_update"
    socket_id = sent[0]["id"]
    closed = [r for r in rows if r["kind"] == "echo-close"]
    assert len(closed) == 1 and closed[0]["body"].startswith("03e8") and closed[0]["id"] == socket_id
    assert any(r["kind"] == "received" and r["id"] == socket_id and r["body"] == "41/collection," for r in rows)


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
        verify_session(rows)


def replay_digest(cases, baseline):
    modes = {f"digest-{algorithm}{policy}{suffix}" for algorithm in ("sha256", "md5")
             for policy in ("", "-legacy") for suffix in ("", "-incorrect")}
    assert Counter((c["client"], c["mode"]) for c in cases) == {
        (client, mode): 1 for client in ("signed", "candidate") for mode in modes}
    for case in cases:
        rows = case["observations"]
        signed, mode = case["client"] == "signed", case["mode"]
        assert case["netDevices"] == [[1, "lo"]] and case["stopped"] and case["exitCode"] == 0
        assert not case["fixtureProtocolRejected"] and not any(row["kind"] == "handlerError" for row in rows)
        proxy = [row for row in rows if row["kind"] == "proxy"]
        assert proxy and all(row["apiKey"] == (row["operation"] != "connect") for row in proxy)
        passed = not mode.endswith("incorrect") and ("legacy" in mode if signed else not baseline)
        assert case["eventObserved"] == case["inventorySucceeded"] == passed
        operations = {"inventory", "pollingGET", "pollingPOST", "connect"} if passed else {"inventory", "pollingGET"}
        if baseline and not signed:
            assert {r["operation"] for r in proxy} == operations
            assert all(r["credentials"] == "absent" and r["digestUri"] is None and r["status"] == "407" for r in proxy)
        else:
            outcome = "incorrect" if mode.endswith("incorrect") else "correct" if passed else "target-mismatch"
            verify_retries(proxy, operations, outcome, "allow" if passed else "407")
            for row in proxy:
                if row["credentials"] == "absent":
                    assert row["digestUri"] is None
                elif row["operation"] == "connect":
                    assert row["digestUri"] == ("root" if signed else "authority")
                else:
                    assert row["digestUri"] == ("origin" if signed else "absolute")
        if not signed:
            assert case["acceptedNonceCounts"] == list(range(1, 1 + sum(row["status"] == "allow" for row in proxy)))
        if passed:
            verify_session(rows)
        else:
            assert rows == proxy


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--digest-reference", action="store_true")
    mode.add_argument("--digest", action="store_true")
    args = parser.parse_args()
    report = json.loads(args.receipt.read_text())
    if args.digest_reference or args.digest:
        replay_digest(report["cases"], baseline=args.digest_reference)
    else:
        replay(report["cases"], "candidateBinarySha256" in report)
    print(f"Validated {len(report['cases'])} archived Linux proxy observations.")
