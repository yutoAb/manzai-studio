"""セリフ音声を gap_ms（負値=かぶせ）どおりに配置して1本にミックスする。

使い方: python scripts/assemble_audio.py assets/scripts/manjaro.json

出力:
  output/audio/manzai.wav          全体ミックス
  output/audio/stem_<speaker>.wav  話者別ステム（リップシンク素材）
  output/audio/timeline.json       各セリフの開始/終了時刻
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINES_DIR = ROOT / "output" / "lines"
AUDIO_DIR = ROOT / "output" / "audio"


def duration_ms(path: Path) -> int:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return round(float(out) * 1000)


# 被せ区間で「被せられる側」を潜らせる量（0=据置, 0.5≈-6dB）。割り込みを明瞭に。
DUCK = 0.5


def mix(entries: list[dict], out_path: Path, total_ms: int) -> None:
    """adelay で各セリフを開始時刻に置き、amix で重ねる（かぶせ対応）。
    次のセリフが食い込む区間は、被せられる側の語尾をダッキングして自然にする。"""
    cmd = ["ffmpeg", "-y"]
    filters = []
    for i, e in enumerate(entries):
        cmd += ["-i", str(e["file"])]
        # mono 音声なので all=1 は不要（古い ffmpeg は all 未対応のため付けない）
        chain = f"[{i}:a]adelay={e['start_ms']}"
        nxt = entries[i + 1] if i + 1 < len(entries) else None
        if nxt and nxt["start_ms"] < e["end_ms"]:  # 次が食い込む＝被せられる
            ov_s, end_s = nxt["start_ms"] / 1000, e["end_ms"] / 1000
            chain += f",volume=enable='between(t,{ov_s:.3f},{end_s:.3f})':volume={DUCK}"
        filters.append(chain + f"[a{i}]")
    inputs = "".join(f"[a{i}]" for i in range(len(entries)))
    filters.append(
        f"{inputs}amix=inputs={len(entries)}:normalize=0,"
        f"apad=whole_dur={total_ms + 500}ms[out]"
    )
    cmd += ["-filter_complex", ";".join(filters), "-map", "[out]",
            "-ar", "44100", "-ac", "1", str(out_path)]
    subprocess.run(cmd, check=True, capture_output=True)


def main() -> None:
    script_path = Path(sys.argv[1] if len(sys.argv) > 1 else "assets/scripts/manjaro.json")
    script = json.loads(script_path.read_text())
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    timeline = []
    cursor = 0  # 直前セリフの終了時刻
    for i, line in enumerate(script["lines"]):
        path = LINES_DIR / f"{i:03d}_{line['speaker']}.mp3"
        if not path.exists():
            sys.exit(f"{path.name} がありません。先に generate_lines.py を実行してください")
        dur = duration_ms(path)
        start = max(0, cursor + line.get("gap_ms", 200))
        timeline.append({
            "index": i, "speaker": line["speaker"], "text": line["text"],
            "file": path, "start_ms": start, "end_ms": start + dur,
        })
        cursor = start + dur

    mix(timeline, AUDIO_DIR / "manzai.wav", cursor)
    for spk in script["speakers"]:
        entries = [e for e in timeline if e["speaker"] == spk]
        if entries:
            mix(entries, AUDIO_DIR / f"stem_{spk}.wav", cursor)

    (AUDIO_DIR / "timeline.json").write_text(json.dumps(
        [{k: v for k, v in e.items() if k != "file"} for e in timeline],
        ensure_ascii=False, indent=2,
    ))
    print(f"done: manzai.wav ({cursor / 1000:.1f}s), stems, timeline.json -> {AUDIO_DIR}")


if __name__ == "__main__":
    main()
