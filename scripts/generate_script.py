"""お題（テーマ）から漫才台本 JSON を自動生成する（「お題 → 漫才動画」の母艦の最初の一段）。

使い方:
  python scripts/generate_script.py "コンビニ"
  python scripts/generate_script.py "回転寿司" -o assets/scripts/sushi.json --lines 24

出力した JSON はそのまま generate_lines.py → assemble_audio.py → 映像化に流せる。

LLM は Anthropic Messages API（Claude）を使う。.env に ANTHROPIC_API_KEY を入れること。
モデルは環境変数 MANZAI_LLM_MODEL で上書き可（既定: claude-opus-4-8）。

注意: オリジナルネタのみを生成させる。実在の芸人名・既存ネタの複製は出力しない方針を
プロンプトで強制している（公開・配布を想定）。
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "assets" / "scripts"

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = os.environ.get("MANZAI_LLM_MODEL", "claude-opus-4-8")

# 既定ボイス（ElevenLabs プロフェッショナル・ライブラリの漫才向け音。各自のボイスに差し替え可）。
# 明るめでテンポが出る組み合わせ。話者別 voice_settings も既定で付与する。
DEFAULT_VOICES = {
    "boke": {
        "voice_id": "J0lF1jpZbjGUH7LlGQfH",
        "voice_settings": {"stability": 0.4, "similarity_boost": 0.9, "style": 0.45},
    },
    "tsukkomi": {
        "voice_id": "tBfOvWrqvlfBiyUGpSAS",
        "voice_settings": {"stability": 0.2, "similarity_boost": 0.9, "style": 0.6},
    },
}

SYSTEM_PROMPT = """あなたは関西の漫才作家のプロです。与えられたお題で、ボケとツッコミ2人の
完全オリジナルの漫才台本を作ります。実在の芸人のネタ・名前・芸風の複製は絶対にしない
（公開・配布する前提）。

出力は必ず次のスキーマの JSON だけ。前後に説明文やコードフェンスを付けない。

{
  "title": "<お題に沿ったネタ名>",
  "speakers": {
    "boke":     { "name": "ボケ",     "voice_id": "" },
    "tsukkomi": { "name": "ツッコミ", "voice_id": "" }
  },
  "lines": [
    { "speaker": "tsukkomi" | "boke", "text": "<セリフ>", "gap_ms": <整数> }
  ]
}

最優先テンプレ（これが一番ウケる。原則これで作る）:
  「オカンが名前を忘れたもの当て」型。お題の語が"二重三重の意味"を持つことを利用する。
  1) つかみ「うちのオカンが、最近好きになったもんの名前を忘れた」
  2) ボケが特徴を1つ言う → ツッコミが「○○やないかい！」と一発で当てる（お題の意味その1）
  3) ボケ「俺も○○やと思てんけどな」→ お題と矛盾する特徴 → ツッコミ「ほな○○ちゃうやないかい！」
     （お題の意味その2＝意外な別解にスライド）
  4) もう一段ずらす（意味その3＝さらに意外な実在のもの）→ ツッコミ「もうええわ」でオチ
  5) 「どうもありがとうございましたー」で締める
  ※ お題（例: パイソン＝ニシキヘビ/Python言語/モンティ・パイソン、クラウド＝雲/クラウド保存/FF7）の
    「ぜんぜん違う3つの意味」を見つけるのがネタの心臓部。最低でも2つ、できれば3つ。

作劇ルール:
- 関西弁のしゃべくり漫才。**短く・キレ重視**（だらだら積まない。1ボケ=1意味=1ツッコミで畳む）。
- ツッコミの「○○やないかい！／ちゃうやないかい！」は食い気味の強いかぶせにする。
- gap_ms は「直前のセリフ終わりからの間」(ミリ秒)。
  - 通常のボケ→ツッコミ: 100〜250
  - 強いツッコミ(かぶせ): **-300〜-550** の負値（ここが効く）
  - つかみ後・転換の溜め: 250〜400
- 効果音を入れたい所だけ text を "<叩く>" のように < > で囲む（TTSされず効果音扱い）。基本使わない。
- voice_id は空文字のままでよい（呼び出し側が補完する）。
- 行数は指定に従う（短いほど良い。10〜14行が目安）。下ネタ・特定個人/企業への誹謗中傷は避ける。
- お題が二重の意味を持ちにくい場合のみ、勘違いを積むしゃべくり型にフォールバックしてよい。
"""


def extract_json(text: str) -> dict:
    """LLM 応答から JSON 本体を取り出してパースする。"""
    s = text.strip()
    # 念のためコードフェンスを除去
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    # 最初の { から最後の } まで
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("応答に JSON が見つかりません:\n" + text[:500])
    return json.loads(s[start : end + 1])


def validate_and_fill(data: dict, voices: dict) -> dict:
    """スキーマを軽く検証し、voice_id を補完する。"""
    if "lines" not in data or not isinstance(data["lines"], list) or not data["lines"]:
        raise ValueError("lines が空、または不正です")
    data.setdefault("speakers", {})
    for spk, cfg in voices.items():
        s = data["speakers"].setdefault(spk, {})
        s.setdefault("name", "ボケ" if spk == "boke" else "ツッコミ")
        s["voice_id"] = cfg["voice_id"]
        s.setdefault("voice_settings", cfg["voice_settings"])
    for i, ln in enumerate(data["lines"]):
        if ln.get("speaker") not in ("boke", "tsukkomi"):
            raise ValueError(f"{i}行目: speaker は boke/tsukkomi のみ")
        if not ln.get("text"):
            raise ValueError(f"{i}行目: text が空")
        ln.setdefault("gap_ms", 200)
        ln["gap_ms"] = int(ln["gap_ms"])
    return data


def generate(topic: str, n_lines: int, model: str, api_key: str) -> dict:
    user = (
        f"お題: 「{topic}」\n"
        f"このお題で、約{n_lines}行（締めのあいさつ含む）の漫才台本を JSON で出力してください。"
    )
    resp = requests.post(
        API_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 4000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=120,
    )
    if resp.status_code != 200:
        raise SystemExit(f"Anthropic API エラー {resp.status_code}: {resp.text[:300]}")
    text = resp.json()["content"][0]["text"]
    return extract_json(text)


def main() -> None:
    ap = argparse.ArgumentParser(description="お題から漫才台本JSONを生成")
    ap.add_argument("topic", help="お題（例: コンビニ）")
    ap.add_argument("-o", "--out", help="出力パス（既定: assets/scripts/<slug>.json）")
    ap.add_argument("--lines", type=int, default=12, help="目安の行数（既定12・短いほどキレが出る）")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"LLMモデル（既定{DEFAULT_MODEL}）")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY が未設定です（.env に追加してください）")

    data = generate(args.topic, args.lines, args.model, api_key)
    data = validate_and_fill(data, DEFAULT_VOICES)

    if args.out:
        out = Path(args.out)
    else:
        slug = re.sub(r"\s+", "_", args.topic.strip())
        out = SCRIPTS_DIR / f"{slug}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"done: {out}  ({len(data['lines'])}行, title={data.get('title')!r})")


if __name__ == "__main__":
    main()
