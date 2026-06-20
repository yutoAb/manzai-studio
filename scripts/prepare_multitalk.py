"""MultiTalk（音声駆動の複数人会話動画生成）用の入力一式を作る。

使い方: uv run python scripts/prepare_multitalk.py

MultiTalk は「2人が写った参照画像 + 話者ごとの音声 → 最大 ~8秒(200f@25fps)の
動画」しか作れないので、台本タイムラインを自然な間で区切って約8秒の
セグメントに分割し、各セグメントの入力 JSON と話者別 wav を出力する。
サーバ側で run_multitalk.sh を回すと、全セグメントを生成して連結し、
完成音声(笑い声入り)を被せた manzai_multitalk.mp4 ができる。

出力: output/multitalk/
  reference.png            2人のツーショット参照画像（groundtruth から抽出）
  full_mix.wav             完成音声（笑い声入り・最終トラック）
  segNN/input.json         セグメントの MultiTalk 入力
  segNN/p1.wav             person1=ボケ(左) の駆動音声 16kHz mono
  segNN/p2.wav             person2=ツッコミ(右) の駆動音声 16kHz mono
  manifest.json            各セグメントの時間とセリフ
  run_multitalk.sh         サーバ側で回す実行スクリプト

フォルダごと MultiTalk リポジトリ直下に PREFIX(=manzai) として置く前提。
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMELINE = ROOT / "output" / "audio" / "timeline.json"
STEM_BOKE = ROOT / "output" / "audio" / "stem_boke.wav"
STEM_TSUKKOMI = ROOT / "output" / "audio" / "stem_tsukkomi.wav"
MIX = ROOT / "output" / "audio" / "manzai_audience.wav"
GROUNDTRUTH = ROOT / "assets" / "groundtruth" / "milkboy" / "videoplayback.mp4"
OUT = ROOT / "output" / "multitalk"

PREFIX = "manzai"          # サーバ側で MultiTalk リポジトリ直下に置くフォルダ名
MAX_SEC = 8.0             # 1セグメントの上限（200f@25fps 以内）
FPS = 25
REF_T = 30.0             # 参照ツーショットを抜くフレーム時刻（秒）

# MultiTalk は英語プロンプトで学習されているので英語で情景を書く
PROMPT = (
    "Two Japanese male comedians performing manzai stand-up comedy on a "
    "brightly lit theater stage, both standing close together at a single "
    "center microphone, talking and reacting to each other with natural "
    "facial expressions and lively hand gestures, upper-body two-shot, "
    "festival stage background, sharp focus."
)


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def make_reference() -> None:
    """groundtruth の2人ツーショットを参照画像に。少し拡大して鮮明にする。"""
    ffmpeg("-ss", f"{REF_T:.3f}", "-i", str(GROUNDTRUTH), "-frames:v", "1",
           "-vf", "scale=960:540:flags=lanczos", str(OUT / "reference.png"))
    print(f"ref   reference.png  (t={REF_T}s, 960x540)")


def build_segments(lines: list[dict]) -> list[dict]:
    """セリフをまたいで約 MAX_SEC ごとに区切る。境界は「間」の中点に置いて
    声を切らない。先頭から末尾まで隙間なくタイル状に並べる。"""
    max_ms = MAX_SEC * 1000
    segs: list[dict] = []
    seg_start = 0
    first = 0
    for i, ln in enumerate(lines):
        if ln["end_ms"] - seg_start > max_ms and i > first:
            prev = lines[i - 1]
            boundary = (prev["end_ms"] + ln["start_ms"]) // 2
            segs.append({"start_ms": seg_start, "end_ms": boundary,
                         "lines": lines[first:i]})
            seg_start = boundary
            first = i
    segs.append({"start_ms": seg_start, "end_ms": lines[-1]["end_ms"],
                 "lines": lines[first:]})
    return segs


def slice_wav(src: Path, start_ms: int, end_ms: int, dst: Path) -> None:
    dur = (end_ms - start_ms) / 1000
    ffmpeg("-ss", f"{start_ms / 1000:.3f}", "-i", str(src),
           "-t", f"{dur:.3f}", "-ar", "16000", "-ac", "1", str(dst))


RUN_SH = """#!/usr/bin/env bash
# MultiTalk リポジトリ直下にこのフォルダ（{prefix}/）を置いて、リポジトリ直下から実行する:
#   bash {prefix}/run_multitalk.sh
# 重みは README の通り weights/ に落としておくこと。生成済みセグメントはスキップ。
set -euo pipefail
PREFIX={prefix}
STEPS=${{STEPS:-40}}
FPS={fps}

# 1) 各セグメントを生成（※ flag は使用中の MultiTalk のバージョンに合わせて調整）
for d in "$PREFIX"/seg*/; do
  name=$(basename "$d")
  raw="$PREFIX/raw_$name"
  [ -f "$raw.mp4" ] && {{ echo "skip $name"; continue; }}
  python generate_multitalk.py \\
    --ckpt_dir weights/Wan2.1-I2V-14B-480P \\
    --wav2vec_dir weights/chinese-wav2vec2-base \\
    --input_json "$d/input.json" \\
    --sample_steps "$STEPS" \\
    --mode streaming \\
    --use_teacache \\
    --num_persistent_param_in_dit 0 \\
    --save_file "$raw"
done

# 2) 各セグメントを台本どおりの長さに正確に合わせる（足りなければ末尾フレームで補完）
:> "$PREFIX/concat.txt"
while IFS=$'\\t' read -r name dur; do
  raw="$PREFIX/raw_$name.mp4"
  fix="$PREFIX/fix_$name.mp4"
  # -nostdin 必須: 無いと ffmpeg が while-read の stdin(durations.tsv) を食って次行が壊れる
  ffmpeg -nostdin -y -v error -i "$raw" \\
    -vf "tpad=stop_mode=clone:stop_duration=3,fps=$FPS" -t "$dur" \\
    -an "$fix"
  echo "file 'fix_$name.mp4'" >> "$PREFIX/concat.txt"
done < "$PREFIX/durations.tsv"

# 3) 連結して完成音声（笑い声入り）を被せる
ffmpeg -y -v error -f concat -safe 0 -i "$PREFIX/concat.txt" -c copy "$PREFIX/video_only.mp4"
# 音声(142s)が映像より長い分は最後のフレームを静止させて受ける
VDUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$PREFIX/video_only.mp4")
ADUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$PREFIX/full_mix.wav")
PAD=$(python -c "print(max(0.0, $ADUR-$VDUR))")
ffmpeg -y -v error -i "$PREFIX/video_only.mp4" -i "$PREFIX/full_mix.wav" \\
  -vf "tpad=stop_mode=clone:stop_duration=$PAD" \\
  -map 0:v -map 1:a -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest \\
  "$PREFIX/manzai_multitalk.mp4"
echo "done: $PREFIX/manzai_multitalk.mp4"
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lines = json.loads(TIMELINE.read_text())
    segs = build_segments(lines)

    make_reference()
    ffmpeg("-i", str(MIX), "-c", "copy", str(OUT / "full_mix.wav"))

    manifest = []
    durations = []
    for i, seg in enumerate(segs):
        name = f"seg{i:02d}"
        d = OUT / name
        d.mkdir(exist_ok=True)
        slice_wav(STEM_BOKE, seg["start_ms"], seg["end_ms"], d / "p1.wav")
        slice_wav(STEM_TSUKKOMI, seg["start_ms"], seg["end_ms"], d / "p2.wav")
        (d / "input.json").write_text(json.dumps({
            "prompt": PROMPT,
            "cond_image": f"{PREFIX}/reference.png",
            "audio_type": "add",   # 掛け合い(交互)なので加算。同時発話なら "para"
            "cond_audio": {
                "person1": f"{PREFIX}/{name}/p1.wav",   # 左=ボケ
                "person2": f"{PREFIX}/{name}/p2.wav",   # 右=ツッコミ
            },
        }, ensure_ascii=False, indent=2) + "\n")
        dur = (seg["end_ms"] - seg["start_ms"]) / 1000
        durations.append(f"{name}\t{dur:.3f}")
        manifest.append({
            "name": name, "start_ms": seg["start_ms"],
            "end_ms": seg["end_ms"], "dur_s": round(dur, 3),
            "lines": [{"speaker": l["speaker"], "text": l["text"]}
                      for l in seg["lines"]],
        })
        print(f"seg   {name}  {seg['start_ms']/1000:6.2f}-{seg['end_ms']/1000:6.2f}s"
              f"  ({dur:4.1f}s, {len(seg['lines'])} lines)")

    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    (OUT / "durations.tsv").write_text("\n".join(durations) + "\n")
    run = OUT / "run_multitalk.sh"
    run.write_text(RUN_SH.format(prefix=PREFIX, fps=FPS))
    run.chmod(0o755)
    print(f"\ndone: {len(segs)} segments -> {OUT}")
    print(f"  サーバの MultiTalk リポジトリ直下に {OUT}/ を {PREFIX}/ として置き、")
    print(f"  リポジトリ直下から `bash {PREFIX}/run_multitalk.sh` を実行")


if __name__ == "__main__":
    main()
