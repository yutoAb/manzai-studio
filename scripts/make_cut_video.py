"""timeline.json をもとに、話しているほうの立ち絵を映すカット割り動画を作る。

使い方: python scripts/make_cut_video.py

assets/images/<speaker>.png があればそれを使い、無ければ
ラベル入りのプレースホルダ画像を自動生成する（1280x720）。
かぶせ区間（両者が同時に話す）はツッコミ側を優先して映す。
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT / "output" / "audio"
VIDEO_DIR = ROOT / "output" / "video"
IMAGES_DIR = ROOT / "assets" / "images"
SIZE = "1280x720"


def ensure_image(speaker: str, color: str) -> Path:
    path = IMAGES_DIR / f"{speaker}.png"
    if path.exists():
        return path
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    label = f"drawtext=text='{speaker.upper()}':fontsize=96:" \
            "fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2"
    for font in ["/System/Library/Fonts/Helvetica.ttc", "/Library/Fonts/Arial.ttf", None]:
        vf = f"{label}:fontfile={font}" if font else label
        result = subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi",
             "-i", f"color=c={color}:s={SIZE}:d=1",
             "-vf", vf, "-frames:v", "1", str(path)],
            capture_output=True,
        )
        if result.returncode == 0:
            return path
    # フォントが見つからなければ無地で妥協
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s={SIZE}:d=1",
         "-frames:v", "1", str(path)],
        check=True, capture_output=True,
    )
    return path


def main() -> None:
    timeline = json.loads((AUDIO_DIR / "timeline.json").read_text())
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    speakers = sorted({e["speaker"] for e in timeline})
    colors = ["0x2c3e50", "0x7f1d1d", "0x14532d", "0x4c1d95"]
    images = {s: ensure_image(s, colors[i % len(colors)]) for i, s in enumerate(speakers)}

    # セリフ開始時刻でカットを切り替える。次のセリフまでの間（gap）も今の話者を映し続ける
    end_ms = max(e["end_ms"] for e in timeline) + 500
    cuts = []  # (image, duration_ms)
    for cur, nxt in zip(timeline, timeline[1:] + [None]):
        cut_end = nxt["start_ms"] if nxt else end_ms
        prev_end = cuts[-1][2] if cuts else 0
        if cut_end <= prev_end:  # かぶせ: 直前カットが食い込んでいたら短いカットは捨てる
            continue
        cuts.append((images[cur["speaker"]], max(prev_end, cur["start_ms"]), cut_end))

    concat = VIDEO_DIR / "cuts.txt"
    lines = []
    pos = 0
    for img, _start, cut_end in cuts:
        lines.append(f"file '{img}'\nduration {(cut_end - pos) / 1000:.3f}")
        pos = cut_end
    lines.append(f"file '{cuts[-1][0]}'")  # concat demuxer は最後に duration 無し行が要る
    concat.write_text("\n".join(lines))

    out = VIDEO_DIR / "manzai_cut.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-i", str(AUDIO_DIR / "manzai.wav"),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
         "-c:a", "aac", "-shortest", str(out)],
        check=True, capture_output=True,
    )
    print(f"done: {out}")


if __name__ == "__main__":
    main()
