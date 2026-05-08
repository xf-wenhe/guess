#!/usr/bin/env python3
"""
Generate 44 curated bad cases for semantic error review.

- Tries to get actual current_score from the embedding server.
- Falls back to current_score=-1 if server is unavailable.
- Appends new cases to data/semantic_error_review_template_v1.csv
  (skips duplicates based on answer+user_input).

Usage:
    python scripts/generate_bad_cases_v1.py [--dry-run]
"""

import argparse, csv, json, math, sys
from datetime import date
from pathlib import Path

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

SERVER_URL = "http://127.0.0.1:8000"
TODAY      = date.today().isoformat()
CSV_PATH   = Path("data/semantic_error_review_template_v1.csv")

_CALIB_CANDIDATES = [
    Path("data/semantic_calibration_v28_conservative.json"),
    Path("data/semantic_calibration_v27_semreal_anchor.json"),
]

ANGLES = [
    "从含义角度看：",
    "从用途角度看：",
    "从场景角度看：",
    "从特征角度看：",
    "从关联角度看：",
]

# ─── calibration helpers ──────────────────────────────────────────────────────

def load_calib():
    for p in _CALIB_CANDIDATES:
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            print(f"[calib] loaded {p}", file=sys.stderr)
            return d["x_pred"], d["y_calibrated"]
    raise FileNotFoundError("No calibration file found")

def lerp(xs, ys, v):
    if v <= xs[0]:  return float(ys[0])
    if v >= xs[-1]: return float(ys[-1])
    for i in range(len(xs) - 1):
        if xs[i] <= v <= xs[i + 1]:
            t = (v - xs[i]) / (xs[i + 1] - xs[i])
            return float(ys[i]) + t * float(ys[i + 1] - ys[i])
    return float(ys[-1])

# ─── embedding helpers ────────────────────────────────────────────────────────

def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb + 1e-9)

def embed_batch(texts):
    r = requests.post(f"{SERVER_URL}/embed", json={"texts": texts}, timeout=15)
    r.raise_for_status()
    return r.json()["embeddings"]

def lexical_sim(a: str, b: str) -> int:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0
    return round(len(sa & sb) / len(sa | sb) * 100)

def score_pair(answer: str, guess: str, xs, ys) -> int:
    """Full pipeline: embed → cosine → calibrate → lexical blend → guards."""
    texts = []
    for ang in ANGLES:
        texts.append(ang + answer)
        texts.append(ang + guess)
    embs = embed_batch(texts)
    sims = [cosine(embs[2 * i], embs[2 * i + 1]) for i in range(len(ANGLES))]
    sims.sort()
    raw_cos = sum(sims[1:]) / (len(ANGLES) - 1)   # drop lowest
    raw_pct = raw_cos * 100
    cal_pct = lerp(xs, ys, raw_pct)
    lex     = lexical_sim(answer, guess)
    # midband cap guard
    if lex <= 20 and raw_pct < 70:
        cal_pct = min(cal_pct, 55)
    combined = cal_pct * 0.8 + lex * 0.2
    # zero-lexical final cap
    if lex == 0 and raw_pct < 75:
        combined = min(combined, 45)
    return round(combined)

# ─── curated candidate pairs ──────────────────────────────────────────────────
# Columns: answer, user_input,
#          corrected_score, error_type, error_severity,
#          why_wrong, natural_relation

CANDIDATES = [
    # ── abstract_confusion: 抽象词因共现语境被过度评分 ──────────────────────────
    ("宇宙", "物理",     20, "abstract_confusion",         "high",
     "宇宙与物理是关联抽象词，但语义核心不同，模型因共现语境高估",
     "related_domain_not_synonym"),
    ("宇宙", "数学",     12, "abstract_confusion",         "high",
     "宇宙与数学无直接语义关联，模型抽象共现误判",
     "very_weak"),
    ("宇宙", "哲学",     18, "abstract_confusion",         "high",
     "宇宙与哲学均高度抽象，模型受共现影响高估",
     "very_weak"),
    ("宇宙", "时间",     35, "abstract_confusion",         "medium",
     "时间是宇宙属性之一，有合理关联但非同义",
     "weak_relation"),
    ("命运", "因果",     42, "abstract_confusion",         "medium",
     "因果和命运有哲学关联，但语义核心不同",
     "related_concept"),
    ("灵魂", "思想",     55, "abstract_confusion",         "low",
     "两者都是抽象内心概念，有合理相似性但非同义",
     "related_moderate"),
    ("智慧", "力量",     28, "abstract_confusion",         "medium",
     "智慧和力量都是人的属性，但语义核心不同",
     "same_attribute_domain"),
    ("星球", "物理",     15, "abstract_confusion",         "high",
     "星球是天体概念，物理是学科，仅因抽象词共现被高估",
     "very_weak"),

    # ── antonym_or_conflict: 反义词被高估 ──────────────────────────────────────
    ("快乐", "悲伤",     10, "antonym_or_conflict",        "critical",
     "明确反义词，语义完全相反，不应超过12",
     "antonym"),
    ("高兴", "难过",     10, "antonym_or_conflict",        "critical",
     "明确情绪反义词",
     "antonym"),
    ("白天", "黑夜",     12, "antonym_or_conflict",        "high",
     "时间反义词，同类但方向相反",
     "antonym"),
    ("胜利", "失败",     12, "antonym_or_conflict",        "high",
     "结果反义词，语义完全对立",
     "antonym"),
    ("古代", "现代",     12, "antonym_or_conflict",        "high",
     "时间段反义词",
     "antonym"),
    ("永恒", "瞬间",     12, "antonym_or_conflict",        "high",
     "持续性反义词",
     "antonym"),
    ("虚无", "存在",     12, "antonym_or_conflict",        "high",
     "哲学反义词，不应高分",
     "antonym"),
    ("智慧", "愚昧",     10, "antonym_or_conflict",        "high",
     "智力反义词",
     "antonym"),

    # ── same_category_but_far: 同类但语义明显不同 ──────────────────────────────
    ("医生",   "老师",   22, "same_category_but_far",      "medium",
     "同为职业，但功能和语义核心完全不同",
     "same_domain_different"),
    ("老虎",   "大象",   22, "same_category_but_far",      "medium",
     "同为大型动物，语义核心明显不同",
     "same_domain_different"),
    ("春天",   "秋天",   28, "same_category_but_far",      "medium",
     "同为季节，描述完全不同的季节特征",
     "same_domain_different"),
    ("北京",   "上海",   28, "same_category_but_far",      "medium",
     "同为中国城市，是两个不同地名",
     "same_domain_different"),
    ("飞机",   "轮船",   22, "same_category_but_far",      "medium",
     "同为交通工具，媒介（空vs水）和语义不同",
     "same_domain_different"),
    ("语文",   "体育",   18, "same_category_but_far",      "high",
     "同为学科，但这两门课相差极大",
     "same_domain_far"),
    ("篮球",   "足球",   28, "same_category_but_far",      "medium",
     "同为球类运动，但规则和特征不同",
     "same_domain_different"),
    ("钢琴",   "小提琴", 30, "same_category_but_far",      "medium",
     "同为乐器，外形和发声机制不同",
     "same_domain_different"),
    ("月亮",   "太阳",   25, "same_category_but_far",      "medium",
     "同为天体，是完全不同的对象",
     "same_domain_different"),
    ("猫",     "狗",     28, "same_category_but_far",      "medium",
     "同为常见宠物，语义核心不同",
     "same_domain_different"),
    ("火",     "水",     18, "same_category_but_far",      "high",
     "传统五行相克，语义对立且不近似",
     "antonym_like"),

    # ── cross_domain_negative: 跨域无关词被高估 ──────────────────────────────
    ("苹果",   "书法",   8,  "cross_domain_negative",      "high",
     "水果与书法艺术，无语义关联",
     "none"),
    ("海浪",   "化学",   8,  "cross_domain_negative",      "high",
     "自然现象与学科，无语义关联",
     "none"),
    ("行李",   "历史",   8,  "cross_domain_negative",      "high",
     "实物与学科，无语义关联",
     "none"),
    ("乒乓球", "哲学",   8,  "cross_domain_negative",      "high",
     "运动与学科，无语义关联",
     "none"),
    ("礼物",   "数学",   8,  "cross_domain_negative",      "high",
     "具体物品与学科，无语义关联",
     "none"),
    ("山峰",   "文学",   8,  "cross_domain_negative",      "high",
     "地理与学科，无语义关联",
     "none"),
    ("星球",   "不知道", 5,  "nonsense",                   "critical",
     "乱输入与答案词，完全无关，不应有任何分",
     "none"),

    # ── hint_like / collocation_not_equivalent ──────────────────────────────
    ("雨伞",   "下雨",       38, "collocation_not_equivalent", "medium",
     "下雨是使用雨伞的场景触发条件，不是同义词",
     "contextual_trigger"),
    ("图书馆", "安静",       32, "hint_like",                  "medium",
     "安静是图书馆的特征提示词，不是同义词",
     "attribute_hint"),
    ("医院",   "白大褂",     38, "hint_like",                  "medium",
     "白大褂是医院场景线索，不等于医院本身",
     "attribute_hint"),
    ("钢琴",   "黑白键",     40, "hint_like",                  "medium",
     "黑白键是钢琴的组成描述，属于提示级别的关联",
     "component_hint"),
    ("手机",   "手机壳",     28, "collocation_not_equivalent", "medium",
     "手机壳是配件，不是手机的近义词",
     "part_not_whole"),
    ("眼镜",   "近视",       35, "collocation_not_equivalent", "medium",
     "近视是配眼镜的原因，不是同义词",
     "cause_not_synonym"),
    ("铅笔",   "文具盒",     30, "collocation_not_equivalent", "medium",
     "文具盒是铅笔的存放容器，不是同义词",
     "container_collocation"),

    # ── near_synonym / alias underscored: 模型给低了 ──────────────────────────
    ("汽车",   "轿车",       72, "near_synonym",              "medium",
     "轿车是汽车的主要类型，语义非常接近，应在70以上",
     "near_equivalent"),
    ("大夫",   "医生",       82, "near_synonym",              "low",
     "大夫和医生在中文日常中几乎完全可互换",
     "alias_in_usage"),
    ("电视",   "电视机",     88, "alias",                     "low",
     "电视和电视机口语完全互换，应近90",
     "strong_alias"),
    ("诸葛亮", "孔明",       90, "alias",                     "low",
     "孔明是诸葛亮的字，是标准历史别名",
     "historical_alias"),
    ("孙悟空", "齐天大圣",   90, "alias",                     "low",
     "齐天大圣是孙悟空的封号别名",
     "title_alias"),
]

# ─── CSV helpers ──────────────────────────────────────────────────────────────

FIELDNAMES = [
    "case_id", "answer", "user_input",
    "current_score", "corrected_score",
    "error_type", "error_severity",
    "why_wrong", "natural_relation", "evidence",
    "review_status", "reviewer", "source", "created_at",
]

def load_existing():
    """Return set of (answer, user_input) already in CSV, and max case_id."""
    if not CSV_PATH.exists():
        return set(), 0
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    existing = {(r["answer"], r["user_input"]) for r in rows}
    max_id   = max((int(r["case_id"]) for r in rows if r["case_id"].isdigit()), default=0)
    return existing, max_id


# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Print rows without writing to CSV")
    args = parser.parse_args()

    xs, ys = load_calib()

    # Check server availability
    server_ok = False
    if _HAS_REQUESTS:
        try:
            r = requests.get(f"{SERVER_URL}/health", timeout=3)
            server_ok = r.status_code == 200
        except Exception:
            pass
    if server_ok:
        print("[server] embedding server is UP — scoring all pairs", file=sys.stderr)
    else:
        print("[server] embedding server is DOWN — current_score will be -1", file=sys.stderr)

    existing, next_id = load_existing()
    print(f"[csv] {len(existing)} existing rows, next id={next_id + 1}", file=sys.stderr)

    new_rows = []
    skipped  = 0

    for (answer, user_input, corrected, etype, severity, why, relation) in CANDIDATES:
        if (answer, user_input) in existing:
            skipped += 1
            continue

        current = -1
        if server_ok:
            try:
                current = score_pair(answer, user_input, xs, ys)
            except Exception as e:
                print(f"[warn] score failed for ({answer},{user_input}): {e}", file=sys.stderr)

        next_id += 1
        row = {
            "case_id":        next_id,
            "answer":         answer,
            "user_input":     user_input,
            "current_score":  current,
            "corrected_score": corrected,
            "error_type":     etype,
            "error_severity": severity,
            "why_wrong":      why,
            "natural_relation": relation,
            "evidence":       "generate_bad_cases_v1",
            "review_status":  "pending",
            "reviewer":       "",
            "source":         "curated_bad_cases",
            "created_at":     TODAY,
        }
        new_rows.append(row)
        status = f"current={current}" if current >= 0 else "current=N/A"
        print(f"  [{next_id:3d}] {answer:8s} vs {user_input:8s}  {status:15s}  corrected={corrected}  {etype}")

    print(f"\n[summary] new={len(new_rows)}  skipped_dup={skipped}")

    if args.dry_run:
        print("[dry-run] Not writing CSV.")
        return

    if not new_rows:
        print("[done] Nothing new to add.")
        return

    write_header = not CSV_PATH.exists()
    with CSV_PATH.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            w.writeheader()
        w.writerows(new_rows)

    print(f"[done] Appended {len(new_rows)} rows → {CSV_PATH}")


if __name__ == "__main__":
    main()
