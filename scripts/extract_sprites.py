"""groundtruth 動画から実写の立ち絵スプライトと舞台背景を切り出す。

使い方: uv run python scripts/extract_sprites.py

FRAMES の時刻のフレームを rembg (u2net_human_seg) で人物切り抜きし、
make_duo_video.py がそのまま読める形式で出力する:
  assets/images/<speaker>_open.png / _closed.png   立ち絵 (RGBA, 同一矩形)
  assets/images/stage.png                          人物を inpaint で消した舞台
  assets/images/layout.json                        実写の立ち位置・身長

注意:
- 元動画のカメラはネタ中にゆっくり寄っていくので、スプライト・舞台とも
  「同じ時間帯」のフレームから取らないと縮尺が合わない。
- 口開き/閉じは「同じ人物が静止して喋っている近い時刻の2フレーム」を選ぶ。
- 人物の切り抜き枠は基準フレーム (STAGE_T) から自動検出する。
"""

import io
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from rembg import new_session, remove

ROOT = Path(__file__).resolve().parent.parent
VIDEO = ROOT / "assets" / "groundtruth" / "milkboy" / "videoplayback.mp4"
IMAGES_DIR = ROOT / "assets" / "images"

# 各スプライトに使うフレームの時刻（秒）。すべて同じ時間帯から選ぶこと
FRAMES = {
    "boke": {"open": 110.400, "closed": 110.167},      # 駒場（左）
    "tsukkomi": {"open": 117.900, "closed": 110.700},  # 内海（右）
}
STAGE_T = 110.167   # 舞台背景 + 人物枠の自動検出に使う基準フレーム
PAD = 24            # 自動検出した人物枠に足す余白 px
MIC_X = (308, 340)  # センターマイクの x 範囲（inpaint で消さずに残す）
SCALE = 3.0         # 640x360 -> 1920x1080


def grab(t: float) -> Image.Image:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(VIDEO),
         "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
        check=True, capture_output=True).stdout
    return Image.open(io.BytesIO(raw)).convert("RGB")


def clean_cut(orig: Image.Image, cut: Image.Image) -> Image.Image:
    """rembg のマスクを掃除して立ち絵にする。
    最大の連結成分だけ残してゴミを捨て、人物内側の抜け（白シャツ等）を
    埋める。色は rembg の出力ではなく元フレームの画素を使う。"""
    a = np.array(cut)[:, :, 3]
    solid = (a > 128).astype(np.uint8)
    n, labels = cv2.connectedComponents(solid)
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    body = (labels == sizes.argmax()).astype(np.uint8)
    h, w = body.shape
    # 1px の余白を足してから流し込むことで「全外周から到達可能か」を判定する
    reach = cv2.copyMakeBorder(body, 1, 1, 1, 1,
                               cv2.BORDER_CONSTANT, value=0)
    cv2.floodFill(reach, np.zeros((h + 4, w + 4), np.uint8), (0, 0), 1)
    reach = reach[1:-1, 1:-1]
    mask = ((body == 1) | (reach == 0)).astype(np.uint8) * 255
    alpha = cv2.GaussianBlur(mask, (5, 5), 1.1)
    return Image.fromarray(np.dstack([np.array(orig), alpha]))


def main() -> None:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    session = new_session("u2net_human_seg")

    # 基準フレームから2人の枠を自動検出（左がボケ、右がツッコミ）
    stage = grab(STAGE_T)
    full = (np.array(remove(stage, session=session))[:, :, 3] > 128)
    n, labels = cv2.connectedComponents(full.astype(np.uint8))
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    comps = []
    for i in sizes.argsort()[-2:]:
        ys, xs = np.where(labels == i)
        comps.append((int(xs.min()), int(ys.min()),
                      int(xs.max()), int(ys.max())))
    comps.sort()
    crop = {s: (max(b[0] - PAD, 0), max(b[1] - PAD, 0),
                min(b[2] + PAD, 640), min(b[3] + PAD, 360))
            for s, b in zip(("boke", "tsukkomi"), comps)}
    print(f"box   {crop}")

    layout: dict[str, dict] = {}
    for speaker, times in FRAMES.items():
        box = crop[speaker]
        cuts = {}
        for state, t in times.items():
            c = grab(t).crop(box)
            cuts[state] = clean_cut(c, remove(c, session=session))

        # 口開き/閉じ共通の矩形に切って、サイズと足元を完全に一致させる
        alphas = [np.array(im)[:, :, 3] > 24 for im in cuts.values()]
        union = alphas[0] | alphas[1]
        ys, xs = np.where(union)
        x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        for state, im in cuts.items():
            out = IMAGES_DIR / f"{speaker}_{state}.png"
            im.crop((x0, y0, x1, y1)).save(out)
            print(f"cut   {out.name}  {x1 - x0}x{y1 - y0}")

        layout[speaker] = {
            "pos_x": round((box[0] + (x0 + x1) / 2) * SCALE),
            "char_h": round((y1 - y0) * SCALE),
            "floor_y": round((box[1] + y1) * SCALE),
        }

    # 舞台: 基準フレームの人物を膨張マスクで消して inpaint。
    # 消した跡はどうせ立ち絵の後ろに隠れるので、輪郭まわりが埋まれば十分
    stage_mask = cv2.dilate(full.astype(np.uint8) * 255,
                            np.ones((15, 15), np.uint8))
    stage_mask[:, MIC_X[0]: MIC_X[1]] = 0  # マイクは実物を残す
    inpainted = cv2.inpaint(
        cv2.cvtColor(np.array(stage), cv2.COLOR_RGB2BGR),
        stage_mask, 8, cv2.INPAINT_TELEA)
    big = cv2.resize(inpainted, (1920, 1080), interpolation=cv2.INTER_LANCZOS4)
    cv2.imwrite(str(IMAGES_DIR / "stage.png"), big)
    print("cut   stage.png  1920x1080 (人物は inpaint で除去)")

    (IMAGES_DIR / "layout.json").write_text(
        json.dumps(layout, indent=2) + "\n")
    print(f"done: {IMAGES_DIR}/layout.json  {json.dumps(layout)}")


if __name__ == "__main__":
    main()
