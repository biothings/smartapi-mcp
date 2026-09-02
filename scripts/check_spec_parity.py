#!/usr/bin/env python
"""
Build every selected SmartAPI API and report on the resulting tool catalogue.

Written to validate the removal of ``awslabs_openapi_mcp_server``: with that
package still installed, ``--baseline`` records what its
``create_mcp_server_async`` produced, and a later ``--compare`` run diffs the
current code against that recording. It is also useful on its own as a coverage
check -- which registry APIs can be served, and which cannot and why.

Needs network access and takes a few minutes on a large set, so it is a script
rather than a test.

    # coverage check against the working registry APIs
    python scripts/check_spec_parity.py --query '_status.uptime_status:pass'

    # record a baseline (on a revision that still has awslabs), then compare
    git stash && python scripts/check_spec_parity.py --api-set biothings_all \
        --baseline old.json
    git stash pop && python scripts/check_spec_parity.py --api-set biothings_all \
        --compare old.json
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from smartapi_mcp.server import get_mcp_server
from smartapi_mcp.smartapi import get_predefined_api_set, get_smartapi_ids


async def snapshot(smartapi_ids: list[str]) -> dict[str, Any]:
    """Build each API and record its tools, or the reason it could not build."""
    out: dict[str, Any] = {}
    for i, sid in enumerate(smartapi_ids, 1):
        print(f"[{i}/{len(smartapi_ids)}] {sid}", file=sys.stderr, flush=True)
        try:
            server = await get_mcp_server(sid)
            tools = await server.list_tools()
            prompts = await server.list_prompts()
            out[sid] = {
                "server_name": server.name,
                "prompts": len(prompts),
                "tools": {
                    tool.name: {
                        "description_len": len(tool.description or ""),
                        "parameters": tool.parameters,
                    }
                    for tool in tools
                },
            }
        except Exception as exc:
            out[sid] = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    return out


def report(current: dict[str, Any], baseline: dict[str, Any] | None) -> int:
    """Print a summary. Returns a process exit code."""
    ok = [k for k, v in current.items() if "error" not in v]
    failed = {k: v["error"] for k, v in current.items() if "error" in v}
    total_tools = sum(len(v["tools"]) for k, v in current.items() if k in ok)
    print(f"\nAPIs: {len(current)}  built: {len(ok)}  failed: {len(failed)}")
    print(f"tools: {total_tools}")
    if failed:
        print("\nfailures:")
        for sid, reason in sorted(failed.items()):
            print(f"  {sid}  {reason}")

    if baseline is None:
        return 0

    print("\n--- vs baseline ---")
    # Only structural losses count as regressions. Description and schema text
    # legitimately *changes* between implementations -- e.g. honouring JSON
    # Schema sibling precedence over a $ref yields the spec's own specific
    # description and example instead of the generic one on the referenced
    # target, which can be either longer or shorter. Byte length is too crude a
    # proxy for "worse", so those are reported for review, not failed on.
    regressions: list[str] = []
    changed: list[str] = []
    identical = 0
    for sid, want in baseline.items():
        got = current.get(sid)
        if got is None:
            regressions.append(f"{sid}: absent from this run")
            continue
        if "error" in want and "error" in got:
            continue
        if "error" in got:
            regressions.append(f"{sid}: now fails ({got['error']})")
            continue
        if "error" in want:
            print(f"  {sid}: now builds (was {want['error']})")
            continue
        if set(got["tools"]) != set(want["tools"]):
            only_now = sorted(set(got["tools"]) - set(want["tools"]))
            only_before = sorted(set(want["tools"]) - set(got["tools"]))
            regressions.append(f"{sid}: tool names differ (+{only_now} -{only_before})")
            continue
        for name, want_tool in want["tools"].items():
            got_tool = got["tools"][name]
            diffs = []
            if got_tool["parameters"] != want_tool["parameters"]:
                diffs.append("input schema")
            delta = got_tool["description_len"] - want_tool["description_len"]
            if delta:
                diffs.append(f"description {delta:+d} chars")
            if diffs:
                changed.append(f"{sid}/{name}: {', '.join(diffs)}")
            else:
                identical += 1

    total = identical + len(changed)
    print(f"  tools compared: {total}  identical: {identical}  changed: {len(changed)}")
    if changed:
        print("\n  changed (review, not failures):")
        for line in changed:
            print(f"    {line}")
    if regressions:
        print(f"\n  {len(regressions)} REGRESSION(S):")
        for line in regressions:
            print(f"    {line}")
        return 1
    print("\n  no structural regressions")
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--api-set", help="a predefined set, e.g. biothings_all")
    source.add_argument("--query", help="a SmartAPI registry query")
    source.add_argument("--ids", help="comma-separated SmartAPI ids")
    parser.add_argument("--limit", type=int, help="only build the first N APIs")
    parser.add_argument("--baseline", type=Path, help="write a snapshot to this file")
    parser.add_argument("--compare", type=Path, help="diff against this snapshot")
    args = parser.parse_args()

    if args.ids:
        ids = args.ids.split(",")
    elif args.query:
        ids = await get_smartapi_ids(args.query)
    else:
        spec = get_predefined_api_set(args.api_set)
        ids = spec.get("smartapi_ids") or await get_smartapi_ids(spec["smartapi_q"])
        excluded = set(spec.get("smartapi_exclude_ids") or [])
        ids = [i for i in ids if i not in excluded]

    ids = sorted(set(ids))[: args.limit]
    print(f"building {len(ids)} API(s)", file=sys.stderr)

    current = await snapshot(ids)
    if args.baseline:
        args.baseline.write_text(json.dumps(current, indent=1, default=str))
        print(f"baseline written to {args.baseline}", file=sys.stderr)

    baseline = json.loads(args.compare.read_text()) if args.compare else None
    return report(current, baseline)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
