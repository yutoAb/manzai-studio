"""客席の笑い声・拍手を ElevenLabs Sound Effects API で生成する。

使い方: python scripts/generate_sfx.py
assets/sfx/ に mp3 を出力する（生成済みはスキップ）。
"""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SFX_DIR = ROOT / "assets" / "sfx"

SOUNDS = {
    # 名前: (プロンプト, 長さ秒)
    "laugh_small": (
        "small chuckle from a theater audience of 300 people, comedy show, "
        "brief, natural room reverb, no music", 2.5),
    "laugh_mid": (
        "a theater audience of 300 people laughing at a joke, comedy show, "
        "hearty laughter that fades naturally, room reverb, no music", 3.5),
    "laugh_big": (
        "a large theater audience bursting into loud laughter at a punchline, "
        "comedy show, big wave of laughter fading naturally, no music", 5.0),
    "applause_end": (
        "theater audience applauding and laughing as a comedy act finishes, "
        "warm applause with some laughter, fades naturally, no music", 7.0),
}


def main() -> None:
    load_dotenv(ROOT / ".env")
    api_key = os.environ["ELEVENLABS_API_KEY"]
    SFX_DIR.mkdir(parents=True, exist_ok=True)

    for name, (prompt, seconds) in SOUNDS.items():
        path = SFX_DIR / f"{name}.mp3"
        if path.exists():
            print(f"skip  {path.name}")
            continue
        r = requests.post(
            "https://api.elevenlabs.io/v1/sound-generation",
            headers={"xi-api-key": api_key},
            json={"text": prompt, "duration_seconds": seconds},
            timeout=120,
        )
        r.raise_for_status()
        path.write_bytes(r.content)
        print(f"sfx   {path.name}  ({seconds}s)")

    print(f"done: {SFX_DIR}")


if __name__ == "__main__":
    main()
