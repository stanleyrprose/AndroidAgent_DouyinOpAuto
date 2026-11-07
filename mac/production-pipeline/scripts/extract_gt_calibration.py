#!/usr/bin/env python3
"""Export evidence-backed R0 candidate correction cases for prompting/regression.

Read-only to private GT; does not change any production captions or models.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

LAYERS = ("ocr", "asr", "fusion")


def build_cases(gt_dir: Path) -> dict:
    result = {"schema_version": 1, "source_kind": "human_reviewed_candidates",
              "independent_recall_evidence": False, "layers": {}}
    source_hash = None
    for layer in LAYERS:
        filename = gt_dir / f"{layer}-human-gt.json"
        content = json.loads(filename.read_text(encoding="utf-8"))
        current_hash = content["meta"]["source_sha256"]
        if source_hash is not None and source_hash != current_hash:
            raise ValueError("inconsistent source hashes across human GT layers")
        source_hash = current_hash
        events = content["events"]
        accepted = [row for row in events if row.get("decision") == "accept"]
        excluded = [row for row in events if row.get("decision") != "accept"]
        corrections = [
            {"event_index": row["index"], "start": row["start"],
             "end": row["end"], "machine_text_zh": row["machine_text_zh"],
             "human_text_zh": row["human_text_zh"],
             "review_note": row.get("review_note")}
            for row in accepted
            if row.get("machine_text_zh") != row.get("human_text_zh")
        ]
        result["layers"][layer] = {
            "candidate_count": len(events),
            "accepted_count": len(accepted),
            "excluded": [{"event_index": row["index"],
                          "reason": row.get("decision"),
                          "machine_text_zh": row.get("machine_text_zh")}
                         for row in excluded],
            "corrections": corrections,
            "candidate_exact_match_rate": round(
                (len(accepted) - len(corrections)) / len(accepted), 4
            ) if accepted else None,
        }
    result["source_sha256"] = source_hash
    result["usage"] = (
        "Use examples as context-sensitive evaluation/calibration cases only. "
        "Do not globally replace substrings in unrelated videos; "
        "do not infer independent event recall from these reviewed candidates."
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gt-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    cases = build_cases(args.gt_dir)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "CANDIDATE_CALIBRATION_ONLY",
                      "layers": list(cases["layers"]), "report": str(args.report)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
