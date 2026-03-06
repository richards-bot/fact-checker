#!/usr/bin/env python3
"""
POC: Transcript -> fact-check comment candidates (timeline-friendly JSON)

This intentionally avoids external APIs by default so it can run anywhere.
Later: swap `extract_claims_heuristic` with an LLM call and plug in real verification search.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List

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
class ClaimComment:
    timecode: str
    sentence: str
    reason: str
    risk: str
    confidence: float
    suggested_checks: List[str]


def split_sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def estimate_risk(sentence: str) -> str:
    s = sentence.lower()
    if any(k in s for k in ["killed", "injured", "accused", "fraud", "crime", "illegal"]):
        return "high"
    if any(k in s for k in ["first", "largest", "most", "%", "million", "billion"]):
        return "medium"
    return "low"


def suggested_checks_for(sentence: str) -> List[str]:
    checks = ["Find 2+ authoritative sources confirming this claim"]
    s = sentence.lower()
    if any(k in s for k in ["%", "percent", "million", "billion", "increased", "decreased"]):
        checks.append("Verify numeric value, unit, and comparison period")
    if any(k in s for k in ["first", "largest", "most"]):
        checks.append("Validate superlative with explicit date range and scope")
    if any(k in s for k in ["killed", "injured", "crime", "accused"]):
        checks.append("Confirm legal/incident framing and attribution language")
    return checks


def extract_claims_heuristic(lines: List[str]) -> List[ClaimComment]:
    comments: List[ClaimComment] = []

    for raw in lines:
        m = TIMECODE_RE.match(raw)
        if not m:
            continue
        timecode, text = m.groups()
        for sent in split_sentences(text):
            low = sent.lower()
            if any(t in low for t in CHECK_TRIGGERS) or re.search(r"\b\d+(?:\.\d+)?\b", sent):
                risk = estimate_risk(sent)
                confidence = 0.65 if risk == "low" else 0.78 if risk == "medium" else 0.86
                comments.append(
                    ClaimComment(
                        timecode=timecode,
                        sentence=sent,
                        reason="Potentially check-worthy factual claim",
                        risk=risk,
                        confidence=confidence,
                        suggested_checks=suggested_checks_for(sent),
                    )
                )

    return comments


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcript", required=True, help="Transcript file with [HH:MM:SS] prefix per line")
    parser.add_argument("--out", required=True, help="Output JSON path")
    args = parser.parse_args()

    transcript_path = Path(args.transcript)
    out_path = Path(args.out)

    lines = transcript_path.read_text(encoding="utf-8").splitlines()
    comments = extract_claims_heuristic(lines)

    payload = {
        "asset_factcheck": {
            "claims_found": len(comments),
            "comments": [asdict(c) for c in comments],
        }
    }

    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(comments)} claim comments -> {out_path}")


if __name__ == "__main__":
    main()
