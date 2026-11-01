"""确定性解码器覆盖率测量：同一语料喂给 FlagEngine，对比模型解题结果。

这是产品级对照测量，不替代模型准确性基准：
- 材料以 UTF-8 文本写入，调用与流水线相同的 analyze_bytes 路径；
- 只统计"标准答案是否出现在候选里"，以及同时出现了多少其它 Flag 候选；
- 不做任何针对性规则调整，也不修改语料。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from secone.config import load_config  # noqa: E402
from secone.core.flag_engine import FlagEngine  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT / "benchmarks" / "ctf_accuracy_v4.json"


def load_cases(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("cases") or [])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.WARNING))
    config = load_config(ROOT)
    patterns = config.flag_patterns()
    depth = int(config.get("analysis.decode_depth", 3))
    max_results = int(config.get("analysis.max_decode_results", 80))

    cases = load_cases(args.corpus)
    if not cases:
        print(f"corpus empty: {args.corpus}")
        return 2

    rows: list[dict] = []
    by_category: dict[str, list[bool]] = defaultdict(list)
    solved = 0
    clean = 0
    noise = 0

    for case in cases:
        material = str(case["material"])
        expected = str(case["flag"])
        category = str(case.get("category") or "unknown")
        engine = FlagEngine(
            patterns=patterns,
            decode_depth=depth,
            max_results=max_results,
        )
        engine.analyze_bytes(material.encode("utf-8"), "material.txt")
        values = [candidate.value for candidate in engine.all_candidates()]
        hit = expected.lower() in {value.lower() for value in values}
        others = [value for value in values if value.lower() != expected.lower()]
        solved += int(hit)
        clean += int(hit and not others)
        noise += len(others)
        by_category[category].append(hit)
        rows.append(
            {
                "id": case.get("id"),
                "category": category,
                "expected": expected,
                "solved": hit,
                "other_flags": others[:8],
                "other_flag_count": len(others),
            }
        )
        status = "OK " if hit else "MISS"
        extra = f" (+{len(others)} 其它候选)" if others else ""
        print(f"[{status}] {case.get('id')} ({category}){extra}")

    total = len(cases)
    category_solved = {
        name: f"{sum(1 for item in flags if item)}/{len(flags)}"
        for name, flags in sorted(by_category.items())
    }
    report = {
        "ok": True,
        "benchmark": "decoder-coverage",
        "note": (
            "确定性解码器覆盖率：材料仅经 FlagEngine 处理，不涉及模型。"
            "solved 表示标准答案出现在候选中；clean 表示候选中只有标准答案。"
        ),
        "corpus": str(args.corpus.relative_to(ROOT)) if args.corpus.is_relative_to(ROOT) else str(args.corpus),
        "cases": total,
        "solved": solved,
        "clean": clean,
        "recovery_rate": round(solved / total, 4),
        "clean_rate": round(clean / total, 4),
        "other_flag_total": noise,
        "by_category": category_solved,
        "rows": rows,
    }
    print()
    print(
        f"解码器覆盖：{solved}/{total} 命中标准答案，{clean}/{total} 无多余候选项，"
        f"其余候选共 {noise} 个"
    )
    print(f"按变换：{json.dumps(category_solved, ensure_ascii=False)}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
