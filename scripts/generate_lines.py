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


def synthesize(api_key: str, voice_id: str, text: str, out_path: Path,
               voice_settings: dict | None = None) -> None:
    resp = requests.post(
        API_URL.format(voice_id=voice_id),
        headers={"xi-api-key": api_key},
        json={
            "text": text,
            "model_id": MODEL_ID,
            "voice_settings": {**DEFAULT_VOICE_SETTINGS, **(voice_settings or {})},
        },
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

    for i, line in enumerate(script["lines"]):
        speaker = script["speakers"][line["speaker"]]
        out_path = LINES_DIR / f"{i:03d}_{line['speaker']}.mp3"
        if out_path.exists():
            print(f"skip  {out_path.name}")
            continue
        if speaker["voice_id"].startswith("REPLACE"):
            sys.exit(f"speakers.{line['speaker']}.voice_id を台本 JSON に設定してください")
        print(f"tts   {out_path.name}  {line['text'][:30]}…")
        # 話者既定 + その行の上書き（line.voice_settings）をマージ
        vs = {**speaker.get("voice_settings", {}), **line.get("voice_settings", {})}
        synthesize(api_key, speaker["voice_id"], line["text"], out_path, vs)

    print(f"done: {LINES_DIR}")


if __name__ == "__main__":
    main()
