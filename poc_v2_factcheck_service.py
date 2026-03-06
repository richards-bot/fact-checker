#!/usr/bin/env python3
"""
POC v2: iconik-style webhook -> transcript fact-check pipeline -> comment payload JSON

- Webhook endpoint stub (stdlib HTTP server)
- Transcript ingestion
- Claim extraction (heuristic)
- Verification search (Wikipedia API; no key)
- iconik comment payload formatter

Run:
  python3 poc_v2_factcheck_service.py --serve --port 8787

Test webhook:
  curl -X POST http://localhost:8787/webhook/transcript-ready \
    -H 'content-type: application/json' \
    -d '{"asset_id":"asset-123","transcript_path":"sample_transcript.txt"}'
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

TIMECODE_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s*(.+)$")

CHECK_TRIGGERS = [
    "according to",
    "data shows",
    "studies show",
    "is the first",
    "is the largest",
    "increased by",
    "decreased by",
    "million",
    "billion",
    "%",
    "percent",
    "killed",
    "injured",
    "confirmed",
    "reported",
]


@dataclass
class Claim:
    timecode: str
    text: str
    risk: str


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def estimate_risk(sentence: str) -> str:
    s = sentence.lower()
    if any(k in s for k in ["killed", "injured", "accused", "fraud", "crime", "illegal"]):
        return "high"
    if any(k in s for k in ["first", "largest", "most", "%", "million", "billion"]):
        return "medium"
    return "low"


def extract_claims(transcript_text: str) -> list[Claim]:
    claims: list[Claim] = []
    for line in transcript_text.splitlines():
        m = TIMECODE_RE.match(line)
        if not m:
            continue
        tc, body = m.groups()
        for sent in split_sentences(body):
            low = sent.lower()
            if any(t in low for t in CHECK_TRIGGERS) or re.search(r"\b\d+(?:\.\d+)?\b", sent):
                claims.append(Claim(timecode=tc, text=sent, risk=estimate_risk(sent)))
    return claims


def wikipedia_search(query: str, limit: int = 3) -> list[dict[str, str]]:
    """Very lightweight no-key search over Wikipedia OpenSearch API."""
    params = urllib.parse.urlencode({"action": "opensearch", "search": query[:120], "limit": str(limit), "namespace": "0", "format": "json"})
    url = f"https://en.wikipedia.org/w/api.php?{params}"
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
        titles = data[1] if len(data) > 1 else []
        descs = data[2] if len(data) > 2 else []
        links = data[3] if len(data) > 3 else []
        out = []
        for i, t in enumerate(titles):
            out.append({
                "title": t,
                "description": descs[i] if i < len(descs) else "",
                "url": links[i] if i < len(links) else "",
            })
        return out
    except Exception:
        return []


def verify_claim(claim: Claim) -> dict[str, Any]:
    hits = wikipedia_search(claim.text)
    confidence = 0.62
    if claim.risk == "medium":
        confidence = 0.74
    elif claim.risk == "high":
        confidence = 0.84

    status = "needs_review"
    if len(hits) >= 2:
        status = "partially_supported"

    return {
        "claim": asdict(claim),
        "verification_status": status,
        "search_hits": hits,
        "confidence": confidence,
        "suggested_action": "human_editor_review",
    }


def format_iconik_comment_payload(asset_id: str, verifications: list[dict[str, Any]]) -> dict[str, Any]:
    comments = []
    for idx, v in enumerate(verifications, start=1):
        c = v["claim"]
        top = v["search_hits"][0]["url"] if v["search_hits"] else ""
        body = (
            f"[FACT-CHECK #{idx}] {c['text']}\n"
            f"risk={c['risk']} status={v['verification_status']} confidence={v['confidence']:.2f}\n"
            f"top_source={top}\n"
            f"action={v['suggested_action']}"
        )
        comments.append({
            "asset_id": asset_id,
            "timecode": c["timecode"],
            "comment": body,
            "tag": "fact_check",
        })

    return {
        "asset_id": asset_id,
        "factcheck_summary": {
            "claims_found": len(verifications),
            "high_risk": sum(1 for v in verifications if v["claim"]["risk"] == "high"),
            "needs_review": sum(1 for v in verifications if v["verification_status"] == "needs_review"),
        },
        "timeline_comments": comments,
    }


def run_pipeline(asset_id: str, transcript_path: str, out_dir: str = ".") -> dict[str, Any]:
    text = Path(transcript_path).read_text(encoding="utf-8")
    claims = extract_claims(text)
    verifications = [verify_claim(c) for c in claims]
    payload = format_iconik_comment_payload(asset_id=asset_id, verifications=verifications)

    out = Path(out_dir) / f"{asset_id}_iconik_factcheck_payload.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"ok": True, "asset_id": asset_id, "claims": len(claims), "output": str(out)}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/webhook/transcript-ready":
            self._send(404, {"ok": False, "error": "not_found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            asset_id = data["asset_id"]
            transcript_path = data["transcript_path"]
            out_dir = data.get("out_dir", ".")
            result = run_pipeline(asset_id, transcript_path, out_dir)
            self._send(200, result)
        except Exception as e:
            self._send(400, {"ok": False, "error": str(e)})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true", help="Run webhook server")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--asset-id")
    ap.add_argument("--transcript")
    ap.add_argument("--out-dir", default=".")
    args = ap.parse_args()

    if args.serve:
        server = HTTPServer(("0.0.0.0", args.port), Handler)
        print(f"Listening on http://0.0.0.0:{args.port}")
        server.serve_forever()
        return

    if args.asset_id and args.transcript:
        result = run_pipeline(args.asset_id, args.transcript, args.out_dir)
        print(json.dumps(result, indent=2))
        return

    ap.error("Use --serve OR provide --asset-id and --transcript")


if __name__ == "__main__":
    main()
