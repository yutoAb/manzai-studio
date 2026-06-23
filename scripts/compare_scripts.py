"""2つの台本JSONを比較する（自動生成 vs 手修正の研究用）。

使い方:
  python scripts/compare_scripts.py <base.json> <edited.json>
  例) python scripts/compare_scripts.py \
        assets/scripts/<neta>.auto.json \
        assets/scripts/<neta>.json

出力:
  ① 定量メトリクス（行数/文字数/フィラー/相槌/笑い/ミラーリング/かぶせ）の左右比較
  ② 行単位の unified diff（"話者: 台詞" 表現、追加/削除/並べ替えに対応）
"""

import json
import re
import sys
from difflib import unified_diff
from pathlib import Path

# ライブ感を測るための簡易語彙（必要に応じて足す）
FILLERS = ["えー", "えーと", "あの", "あのー", "まあ", "まー", "うーん", "その", "なんか", "ほんで", "でね", "あー"]
AIZUCHI = ["うん", "はい", "へえ", "へー", "そうそう", "なるほど", "せやな", "ああ", "おお", "うわ"]
LAUGH_RE = re.compile(r"\(笑\)|（笑）|ははは|わはは|w(?:ww+)")


def load(path):
    return json.loads(Path(path).read_text())


def lines_as_text(d):
    """各行を 'spk: text' に。diff 用。"""
    out = []
    for ln in d["lines"]:
        spk = ln["speaker"]
        out.append(f"{spk:8s}| {ln['text']}")
    return out


def metrics(d):
    lines = d["lines"]
    texts = [ln["text"] for ln in lines]
    joined = "".join(texts)
    n_filler = sum(joined.count(w) for w in FILLERS)
    n_aizuchi = sum(joined.count(w) for w in AIZUCHI)
    n_laugh = len(LAUGH_RE.findall(joined))
    # ミラーリング: 直前の行と（ほぼ）同一の短い台詞（反復・オウム返し）
    n_mirror = 0
    for i in range(1, len(lines)):
        a, b = texts[i - 1].strip("！。、?？ "), texts[i].strip("！。、?？ ")
        if a and len(a) <= 8 and a == b:
            n_mirror += 1
    n_kabuse = sum(1 for ln in lines if ln.get("gap_ms", 0) < 0)
    return {
        "行数": len(lines),
        "総文字数": len(joined),
        "フィラー": n_filler,
        "相槌": n_aizuchi,
        "笑い": n_laugh,
        "ミラーリング": n_mirror,
        "かぶせ(負gap)": n_kabuse,
    }


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    base_p, edit_p = sys.argv[1], sys.argv[2]
    base, edit = load(base_p), load(edit_p)

    print("=" * 60)
    print(f"BASE : {base_p}")
    print(f"EDIT : {edit_p}")
    print("=" * 60)

    mb, me = metrics(base), metrics(edit)
    print(f"\n【定量メトリクス】 {'指標':<14}{'BASE':>8}{'EDIT':>8}{'差分':>8}")
    for k in mb:
        diff = me[k] - mb[k]
        print(f"  {k:<14}{mb[k]:>8}{me[k]:>8}{diff:>+8}")

    print("\n【行単位 diff（- BASE / + EDIT）】")
    diff = unified_diff(lines_as_text(base), lines_as_text(edit),
                        fromfile=base_p, tofile=edit_p, lineterm="")
    any_diff = False
    for line in diff:
        any_diff = True
        print("  " + line)
    if not any_diff:
        print("  （差分なし＝2ファイルは同一）")


if __name__ == "__main__":
    main()
