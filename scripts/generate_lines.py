"""台本 JSON の各セリフを ElevenLabs v3 で音声化して output/lines/ に保存する。

使い方: python scripts/generate_lines.py assets/scripts/manjaro.json
生成済みのファイルはスキップする（台本を直したら該当 mp3 を消して再実行）。
"""

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
MODEL_ID = "eleven_v3"
ROOT = Path(__file__).resolve().parent.parent
LINES_DIR = ROOT / "output" / "lines"


# 漫才向けの既定: stability を下げて抑揚を出し、style を上げて演技を強める。
# 話者ごとに台本 JSON の speakers.<spk>.voice_settings で上書きできる。
DEFAULT_VOICE_SETTINGS = {
    "stability": 0.3,
    "similarity_boost": 0.8,
    "style": 0.5,
    "use_speaker_boost": True,
}


import re

# <リップ音> <叩く> のような非言語キューは TTS せず効果音として別途差し込む
CUE_RE = re.compile(r"^\s*[<＜].*[>＞]\s*$")


def is_cue(text: str) -> bool:
    return bool(CUE_RE.match(text or ""))


def synthesize(api_key: str, voice_id: str, text: str, out_path: Path,
               voice_settings: dict | None = None,
               previous_text: str | None = None,
               next_text: str | None = None) -> None:
    # 掛け合いの自然さ向上: 前後のセリフを文脈として渡し、抑揚を会話として繋ぐ
    payload = {
        "text": text,
        "model_id": MODEL_ID,
        "voice_settings": {**DEFAULT_VOICE_SETTINGS, **(voice_settings or {})},
    }
    # previous_text/next_text は eleven_v3 では未対応（400）。v3以外でのみ付与。
    if MODEL_ID != "eleven_v3":
        if previous_text:
            payload["previous_text"] = previous_text
        if next_text:
            payload["next_text"] = next_text
    resp = requests.post(
        API_URL.format(voice_id=voice_id),
        headers={"xi-api-key": api_key},
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    out_path.write_bytes(resp.content)


def main() -> None:
    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        sys.exit("ELEVENLABS_API_KEY が .env にありません")

    script_path = Path(sys.argv[1] if len(sys.argv) > 1 else "assets/scripts/manjaro.json")
    script = json.loads(script_path.read_text())
    LINES_DIR.mkdir(parents=True, exist_ok=True)

    lines = script["lines"]

    def ctx(idx: int) -> str | None:
        """前後の文脈テキスト（非言語キューは除外）。"""
        if 0 <= idx < len(lines) and not is_cue(lines[idx]["text"]):
            return lines[idx]["text"]
        return None

    for i, line in enumerate(lines):
        out_path = LINES_DIR / f"{i:03d}_{line['speaker']}.mp3"
        if is_cue(line["text"]):
            # 効果音キュー（<...>）は TTS しない（別途 SFX を差し込む）
            print(f"cue   {out_path.name}  {line['text']}  → SFXで差し込み")
            continue
        if out_path.exists():
            print(f"skip  {out_path.name}")
            continue
        speaker = script["speakers"][line["speaker"]]
        if speaker["voice_id"].startswith("REPLACE"):
            sys.exit(f"speakers.{line['speaker']}.voice_id を台本 JSON に設定してください")
        print(f"tts   {out_path.name}  {line['text'][:30]}…")
        # 話者既定 + その行の上書き（line.voice_settings）をマージ
        vs = {**speaker.get("voice_settings", {}), **line.get("voice_settings", {})}
        synthesize(api_key, speaker["voice_id"], line["text"], out_path, vs,
                   previous_text=ctx(i - 1), next_text=ctx(i + 1))

    print(f"done: {LINES_DIR}")


if __name__ == "__main__":
    main()
