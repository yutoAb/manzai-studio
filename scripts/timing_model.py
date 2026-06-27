"""漫才の「間（gap_ms）」を自動付与するタイミングモデル（MVP①: 学習可能な間の基盤）。

狙い: 人手で1行ずつ gap_ms を設計する代わりに、遷移タイプ（つかみ/ボケ→ツッコミ/かぶせ/天丼前 等）
ごとの分布から gap_ms を自動割当する。事前分布は漫才の経験則＋full-duplex研究の知見で初期化し、
将来 diarization 済みの2話者タイムライン（実演データ）から fit_from_timeline() で学習して上書きできる。

使い方:
  python scripts/timing_model.py assets/scripts/cloud.json            # -> cloud.timed.json を出力
  python scripts/timing_model.py assets/scripts/cloud.json --seed 7 --backchannel

設計メモ（研究との対応）:
- full-duplexの自然さは「ターンテイキング＋かぶせ＋相槌」を確率的に扱うことが核（arXiv 2509.14515 ほか）。
- ここはまだ Engineered Synchronization 側（学習した分布で間を“設計”）。Learned側(end-to-end生成)はMVP②③。
- かぶせ（負gap）は食い気味ツッコミの決め台詞で発生しやすい → 内容キューで検出。
"""

import argparse
import json
import random
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 食い気味ツッコミ（かぶせ＝負gap）になりやすい決め台詞のキュー
KABUSE_CUES = ["やないかい", "ちゃうやないか", "なんでやねん", "どっちやねん",
               "もうええわ", "ええわ！", "ちゃうわ", "わけないやろ", "あるかい"]
# 天丼/転換前の“溜め”が入りやすいボケの切り出し
TAME_CUES = ["ほんで", "でな", "それでな", "あとな", "もう一個", "ほんでオトン", "次は"]

# 遷移タイプごとの gap_ms 事前分布（平均, 標準偏差）。経験則＋研究知見で初期化。
PRIORS = {
    "opening":        (0,    0),     # 1行目
    "boke2tsukkomi":  (170,  60),    # 通常: 食い気味でない受け
    "tsukkomi2boke":  (300,  90),    # ボケが次を繰り出す前の軽い間
    "kabuse":         (-130, 40),    # 食い気味（負gap）
    "tame":           (450,  120),   # 天丼/転換前の溜め
    "closing":        (200,  60),    # 締めの挨拶前
    "same_speaker":   (250,  80),    # 同一話者の連続
}


def classify(prev, cur, is_first, is_last):
    """直前→現在のセリフ遷移タイプを判定する。"""
    if is_first:
        return "opening"
    text = cur.get("text", "")
    if is_last and ("ありがとうございました" in text):
        return "closing"
    if prev and prev["speaker"] == cur["speaker"]:
        return "same_speaker"
    # 食い気味ツッコミ（かぶせ）
    if cur["speaker"] == "tsukkomi" and any(c in text for c in KABUSE_CUES):
        return "kabuse"
    # ボケが溜めてから繰り出す（天丼/転換）
    if cur["speaker"] == "boke" and any(text.startswith(c) or c in text[:6] for c in TAME_CUES):
        return "tame"
    if prev and prev["speaker"] == "boke" and cur["speaker"] == "tsukkomi":
        return "boke2tsukkomi"
    if prev and prev["speaker"] == "tsukkomi" and cur["speaker"] == "boke":
        return "tsukkomi2boke"
    return "boke2tsukkomi"


class TimingModel:
    def __init__(self, priors=None, seed=0):
        self.priors = dict(PRIORS if priors is None else priors)
        self.rng = random.Random(seed)

    def sample_gap(self, ttype):
        mu, sigma = self.priors.get(ttype, PRIORS["boke2tsukkomi"])
        if sigma == 0:
            return int(mu)
        g = self.rng.gauss(mu, sigma)
        # かぶせは負を保ち、それ以外は過度な負値にしない
        if ttype == "kabuse":
            return int(max(-300, min(-40, g)))
        return int(max(0, g))

    def assign(self, lines, backchannel=False):
        """各行に gap_ms を割当てて返す（既存値は上書き）。任意で相槌行を挿入。"""
        out = []
        n = len(lines)
        for i, ln in enumerate(lines):
            prev = lines[i - 1] if i > 0 else None
            ttype = classify(prev, ln, i == 0, i == n - 1)
            new = dict(ln)
            new["gap_ms"] = self.sample_gap(ttype)
            new["_ttype"] = ttype  # デバッグ用（assemble側は無視）
            out.append(new)
        if backchannel:
            out = self._insert_backchannels(out)
        return out

    def _insert_backchannels(self, lines, prob=0.18):
        """ボケの長セリフ中に相手の短い相槌（<相槌>）を確率的に差し込む雛形。
        実SFX/TTSは別途。ここではタイミング設計として位置だけ与える。"""
        res = []
        for ln in lines:
            res.append(ln)
            if ln["speaker"] == "boke" and len(ln.get("text", "")) > 28 and self.rng.random() < prob:
                other = "tsukkomi"
                res.append({"speaker": other, "text": "<相槌>", "gap_ms": -200, "_ttype": "backchannel"})
        return res

    def fit_from_timeline(self, timelines):
        """diarization済みの2話者タイムライン（[{speaker,start_ms,end_ms,text}...]）から
        遷移タイプ別の gap_ms 分布を推定して priors を上書きする（将来の学習フック）。
        gap = 現在start - 直前end（負値=オーバーラップ＝かぶせ）。"""
        buckets = {k: [] for k in PRIORS}
        for tl in timelines:
            tl = sorted(tl, key=lambda x: x["start_ms"])
            for i, e in enumerate(tl):
                prev = tl[i - 1] if i > 0 else None
                ttype = classify(prev, e, i == 0, i == len(tl) - 1)
                if prev is not None:
                    buckets[ttype].append(e["start_ms"] - prev["end_ms"])
        for k, vals in buckets.items():
            if len(vals) >= 5:
                mu = statistics.mean(vals)
                sigma = statistics.pstdev(vals) if len(vals) > 1 else PRIORS[k][1]
                self.priors[k] = (mu, sigma)
        return self.priors


def main():
    ap = argparse.ArgumentParser(description="漫才台本に gap_ms を自動付与（タイミングモデル）")
    ap.add_argument("script", help="台本JSON")
    ap.add_argument("-o", "--out", help="出力（既定: <script>.timed.json）")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--backchannel", action="store_true", help="相槌(<相槌>)を確率的に挿入")
    args = ap.parse_args()

    data = json.loads(Path(args.script).read_text(encoding="utf-8"))
    model = TimingModel(seed=args.seed)
    data["lines"] = model.assign(data["lines"], backchannel=args.backchannel)

    out = Path(args.out) if args.out else Path(args.script).with_suffix(".timed.json")
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # サマリ
    from collections import Counter
    c = Counter(l["_ttype"] for l in data["lines"])
    print(f"done: {out}  ({len(data['lines'])}行)")
    print("  遷移タイプ:", dict(c))
    print("  gap_ms:", [l["gap_ms"] for l in data["lines"]])


if __name__ == "__main__":
    main()
