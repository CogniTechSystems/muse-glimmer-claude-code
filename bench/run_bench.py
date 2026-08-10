#!/usr/bin/env python3
"""Benchmark an OpenAI-compatible endpoint on the cases in cases.json.

Measures per-case correctness (substring check), wall time, and tok/s.
llama-server includes a `timings` object in its responses; when present we
report its generation speed (measured server-side, excludes network) alongside
the wall-clock figure.

Usage:
    python3 bench/run_bench.py --target local --label baseline
"""

import argparse
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def call(target: dict, case: dict) -> dict:
    payload = {
        "model": target["model"],
        "messages": [{"role": "user", "content": case["prompt"]}],
        "max_tokens": case.get("max_tokens", 512),
        "temperature": case.get("temperature", 0),
    }
    req = urllib.request.Request(
        target["base_url"].rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {target.get('api_key', 'none')}",
        },
    )
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as resp:
        body = json.load(resp)
    wall = time.perf_counter() - start

    text = body["choices"][0]["message"]["content"] or ""
    usage = body.get("usage", {})
    completion_tokens = usage.get("completion_tokens", 0)
    timings = body.get("timings", {})  # llama-server extension

    return {
        "text": text,
        "wall_s": round(wall, 3),
        "completion_tokens": completion_tokens,
        "wall_tok_s": round(completion_tokens / wall, 2) if wall > 0 else None,
        "server_tok_s": round(timings["predicted_per_second"], 2)
        if "predicted_per_second" in timings
        else None,
        "prompt_tok_s": round(timings["prompt_per_second"], 2)
        if "prompt_per_second" in timings
        else None,
    }


def check(case: dict, text: str) -> bool:
    needles = [n.lower() for n in case.get("expect", [])]
    if not needles:
        return True
    haystack = text.lower()
    hits = [n in haystack for n in needles]
    return any(hits) if case.get("match", "any") == "any" else all(hits)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="local")
    parser.add_argument("--label", default="run", help="e.g. baseline / speculative")
    args = parser.parse_args()

    targets = json.loads((ROOT / "bench" / "targets.json").read_text())
    target = targets[args.target]
    cases = json.loads((ROOT / "bench" / "cases.json").read_text())["cases"]

    results = []
    for case in cases:
        try:
            r = call(target, case)
        except Exception as exc:  # noqa: BLE001 - record and continue
            print(f"  {case['id']}: ERROR {exc}")
            results.append({"id": case["id"], "error": str(exc)})
            continue
        r["id"] = case["id"]
        r["pass"] = check(case, r["text"])
        results.append(r)
        speed = r["server_tok_s"] or r["wall_tok_s"]
        print(
            f"  {case['id']}: {'PASS' if r['pass'] else 'FAIL'}  "
            f"{r['completion_tokens']} tok in {r['wall_s']}s  ({speed} tok/s)"
        )

    ok = [r for r in results if "error" not in r]
    passed = sum(1 for r in ok if r["pass"])
    speeds = [r["server_tok_s"] or r["wall_tok_s"] for r in ok if r["completion_tokens"]]
    summary = {
        "label": args.label,
        "target": args.target,
        "model": target["model"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "total": len(cases),
        "mean_tok_s": round(sum(speeds) / len(speeds), 2) if speeds else None,
        "results": results,
    }
    print(f"\n{args.label}: {passed}/{len(cases)} passed, mean {summary['mean_tok_s']} tok/s")

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = out_dir / f"{stamp}-{args.label}.json"
    out.write_text(json.dumps(summary, indent=2))
    print(f"saved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
