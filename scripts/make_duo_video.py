"""2人が舞台に立ち続ける引き画の漫才動画を作る（ミルクボーイ的な構図）。

使い方: uv run python scripts/make_duo_video.py [--preview 5,30,60]

話者別ステム (output/audio/stem_*.wav) の音量で、喋っている側の口パクと
体の揺れを駆動する。聞いている側も呼吸・まばたきで静止しない。
カメラは話者側へゆっくり寄る疑似ワーク。

素材は差し替え可能:
  assets/images/stage.png                 舞台背景 (1920x1080)
  assets/images/<speaker>_closed.png      口閉じ立ち絵 (RGBA, 足元下端基準)
  assets/images/<speaker>_open.png        口開き立ち絵
  assets/images/<speaker>_blink.png       まばたき立ち絵 (省略可)
無ければフラットデザインの立ち絵と M-1 風の舞台をプログラム描画する。
assets/sfx/*.mp3 があれば客の笑い声をツッコミの決めゼリフ後にミックスする。
"""

import json
import math
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT / "output" / "audio"
VIDEO_DIR = ROOT / "output" / "video"
IMAGES_DIR = ROOT / "assets" / "images"
SFX_DIR = ROOT / "assets" / "sfx"

SR = 44100
FPS = 30
CANVAS = (1920, 1080)   # 内部キャンバス
OUT = (1280, 720)       # 出力解像度
FLOOR_Y = 1020          # 立ち位置（足元）
CHAR_H = 680            # 立ち絵の表示高さ
POS_X = {"boke": 760, "tsukkomi": 1160}  # 客席から見てボケ左・ツッコミ右

# 笑い声: ツッコミのセリフに含まれる決めフレーズ -> 効果音名
LAUGH_RULES = [
    ("もうええわ", "laugh_big"),
    ("どっちやねん", "laugh_big"),
    ("やないかい", "laugh_mid"),
    ("やのよ", "laugh_small"),
    ("ありがとうございました", "applause_end"),
]
LAUGH_GAIN = {"laugh_small": 0.30, "laugh_mid": 0.40,
              "laugh_big": 0.52, "applause_end": 0.55}


# ---------------------------------------------------------------- 立ち絵

CHAR_STYLE = {
    "boke": {        # 飄々: 明るいジャケット + 白T
        "jacket": (108, 128, 168), "inner": (245, 245, 242),
        "pants": (52, 58, 78), "shoes": (235, 235, 235),
        "skin": (242, 201, 164), "hair": (38, 32, 30),
        "body_w": 1.0, "head_w": 170, "brow_tilt": -4, "tie": False,
    },
    "tsukkomi": {    # どっしり: オリーブのスーツ + ネクタイ
        "jacket": (104, 99, 70), "inner": (250, 250, 248),
        "pants": (94, 89, 64), "shoes": (72, 52, 38),
        "skin": (236, 192, 152), "hair": (24, 22, 22),
        "body_w": 1.18, "head_w": 186, "brow_tilt": 7, "tie": True,
    },
}


def draw_character(kind: str, mouth_open: bool, eyes_closed: bool) -> Image.Image:
    """600x1100 RGBA、下端中央が足元。フラットデザインの漫才師立ち絵。"""
    s = CHAR_STYLE[kind]
    img = Image.new("RGBA", (600, 1100), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, bw = 300, s["body_w"]

    def w(x: float) -> float:  # 体格による横スケール（中心基準）
        return cx + (x - cx) * bw

    # 脚・靴
    for sign in (-1, 1):
        x0, x1 = cx + sign * 14, cx + sign * 62
        d.polygon([(w(x0), 700), (w(x1), 700), (w(x1) + sign * 6, 1042),
                   (w(x0) + sign * 2, 1042)], fill=s["pants"])
        sx = w(cx + sign * 38)
        d.rounded_rectangle([sx - 40, 1038, sx + 40, 1078],
                            radius=14, fill=s["shoes"])

    # 腕（ジャケット袖、体の脇に下ろす）+ 手
    for sign in (-1, 1):
        ax = w(cx + sign * 118)
        d.rounded_rectangle([ax - 26, 460, ax + 26, 706], radius=26,
                            fill=tuple(int(c * 0.92) for c in s["jacket"]))
        d.ellipse([ax - 20, 690, ax + 20, 730], fill=s["skin"])

    # 胴体（ジャケット）
    d.polygon([(w(208), 452), (w(392), 452), (w(404), 716), (w(196), 716)],
              fill=s["jacket"])
    d.ellipse([w(208), 420, w(392), 500], fill=s["jacket"])  # 肩の丸み
    # インナー（Vネックに見える襟元）
    d.polygon([(w(262), 444), (w(338), 444), (cx, 560)], fill=s["inner"])
    if s["tie"]:
        d.polygon([(cx - 13, 452), (cx + 13, 452), (cx + 9, 600), (cx, 622),
                   (cx - 9, 600)], fill=(70, 48, 34))
    # ラペル
    lap = tuple(int(c * 0.82) for c in s["jacket"])
    d.polygon([(w(262), 444), (cx, 560), (w(252), 560), (w(238), 470)], fill=lap)
    d.polygon([(w(338), 444), (cx, 560), (w(348), 560), (w(362), 470)], fill=lap)

    # 首・頭
    d.rectangle([cx - 17, 372, cx + 17, 440], fill=s["skin"])
    hw, hh = s["head_w"], 198
    head = [cx - hw / 2, 196, cx + hw / 2, 196 + hh]
    d.ellipse(head, fill=s["skin"])
    # 髪（前髪のあるショート）
    d.pieslice([head[0] - 4, 188, head[2] + 4, 196 + hh * 0.66],
               start=180, end=360, fill=s["hair"])
    d.ellipse([head[0] - 4, 252, head[0] + 26, 330], fill=s["skin"])   # こめかみ
    d.ellipse([head[2] - 26, 252, head[2] + 4, 330], fill=s["skin"])
    # 耳
    d.ellipse([head[0] - 12, 290, head[0] + 12, 334], fill=s["skin"])
    d.ellipse([head[2] - 12, 290, head[2] + 12, 334], fill=s["skin"])

    # 眉（ツッコミは吊り眉、ボケは下がり眉）
    bt = s["brow_tilt"]
    for sign in (-1, 1):
        ex = cx + sign * 38
        d.line([(ex - 20, 292 + sign * bt), (ex + 20, 292 - sign * bt)],
               fill=(40, 34, 30), width=7)
    # 目
    for sign in (-1, 1):
        ex = cx + sign * 38
        if eyes_closed:
            d.line([(ex - 13, 322), (ex + 13, 322)], fill=(40, 34, 30), width=5)
        else:
            d.ellipse([ex - 9, 310, ex + 9, 334], fill=(34, 30, 28))
    # 鼻
    d.line([(cx, 340), (cx + 6, 356)], fill=(205, 158, 122), width=4)
    # 口
    if mouth_open:
        d.ellipse([cx - 24, 364, cx + 24, 402], fill=(94, 44, 38))
        d.ellipse([cx - 14, 384, cx + 14, 400], fill=(168, 88, 78))
    else:
        d.arc([cx - 22, 352, cx + 22, 384], start=15, end=165,
              fill=(120, 66, 52), width=5)
    return img


def load_or_draw_sprites(speaker: str, char_h: int) -> dict[str, Image.Image]:
    """state -> 表示サイズへ縮小済み RGBA。外部画像があれば優先する。"""
    states = {}
    ext = {st: IMAGES_DIR / f"{speaker}_{st}.png"
           for st in ("closed", "open", "blink")}
    if ext["closed"].exists() and ext["open"].exists():
        states["closed"] = Image.open(ext["closed"]).convert("RGBA")
        states["open"] = Image.open(ext["open"]).convert("RGBA")
        states["blink"] = (Image.open(ext["blink"]).convert("RGBA")
                           if ext["blink"].exists() else states["closed"])
        states["open_blink"] = states["open"]
        print(f"img   {speaker}: assets/images/{speaker}_*.png を使用")
    else:
        states["closed"] = draw_character(speaker, False, False)
        states["open"] = draw_character(speaker, True, False)
        states["blink"] = draw_character(speaker, False, True)
        states["open_blink"] = draw_character(speaker, True, True)
    for k, im in states.items():
        scale = char_h / im.height
        states[k] = im.resize((round(im.width * scale), char_h),
                              Image.LANCZOS)
    return states


# ---------------------------------------------------------------- 舞台

def draw_stage() -> Image.Image:
    custom = IMAGES_DIR / "stage.png"
    if custom.exists():
        print("img   stage: assets/images/stage.png を使用")
        return Image.open(custom).convert("RGB").resize(CANVAS)

    W, H = CANVAS
    img = Image.new("RGB", CANVAS)
    d = ImageDraw.Draw(img)
    wall_h = 880

    # 後壁: 暖色グラデーション
    top, bottom = np.array([246, 234, 210]), np.array([226, 196, 142])
    for y in range(wall_h):
        c = top + (bottom - top) * (y / wall_h)
        d.line([(0, y), (W, y)], fill=tuple(c.astype(int)))

    # 中央のアールデコ風サンバースト
    gold, deep = (201, 161, 78), (176, 134, 56)
    for r in range(180, 1000, 90):
        d.arc([960 - r, wall_h - r, 960 + r, wall_h + r],
              start=180, end=360, fill=gold, width=10)
    for deg in range(186, 360, 12):
        a = math.radians(deg)
        x, y = 960 + 980 * math.cos(a), wall_h + 980 * math.sin(a)
        d.line([(960, wall_h), (x, y)], fill=deep, width=5)
    # サンバーストの中心飾り
    d.pieslice([960 - 130, wall_h - 130, 960 + 130, wall_h + 130],
               start=180, end=360, fill=(214, 178, 96))

    # 左右の袖パネル + 六角形アクセント
    side_w = 330
    for x0 in (0, W - side_w):
        d.rectangle([x0, 0, x0 + side_w, wall_h], fill=(86, 38, 30))
        d.rectangle([x0 + (side_w - 14 if x0 == 0 else 0), 0,
                     x0 + (side_w if x0 == 0 else 14), wall_h],
                    fill=(214, 178, 96))
        hx = x0 + side_w // 2
        for i, hy in enumerate(range(140, wall_h - 60, 240)):
            rr = 66 if i % 2 == 0 else 44
            pts = [(hx + rr * math.cos(math.radians(60 * k - 30)),
                    hy + rr * math.sin(math.radians(60 * k - 30)))
                   for k in range(6)]
            d.polygon(pts, outline=(224, 150, 56), width=9)

    # 上部の幕
    d.rectangle([0, 0, W, 64], fill=(86, 38, 30))
    d.rectangle([0, 64, W, 76], fill=(214, 178, 96))

    # 床: 暗色グラデーション + センターのスポットライト
    f_top, f_bot = np.array([62, 44, 34]), np.array([24, 17, 13])
    for y in range(wall_h, H):
        c = f_top + (f_bot - f_top) * ((y - wall_h) / (H - wall_h))
        d.line([(0, y), (W, y)], fill=tuple(c.astype(int)))
    spot = Image.new("L", CANVAS, 0)
    sd = ImageDraw.Draw(spot)
    for i in range(28, 0, -1):
        rx, a = 30 * i, int(60 * (1 - i / 28) + 8)
        sd.ellipse([960 - rx, 985 - rx * 0.18, 960 + rx, 985 + rx * 0.18],
                   fill=a)
    img.paste(Image.new("RGB", CANVAS, (255, 236, 190)), (0, 0),
              spot.filter(ImageFilter.GaussianBlur(18)))
    return img


def draw_mic() -> Image.Image:
    """センターマイク（前景、RGBA）。"""
    img = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = 960
    d.ellipse([cx - 64, 1036, cx + 64, 1064], fill=(28, 28, 30, 255))
    d.rectangle([cx - 5, 668, cx + 5, 1050], fill=(52, 52, 56, 255))
    d.rectangle([cx - 3, 668, cx, 1050], fill=(96, 96, 102, 255))  # ハイライト
    d.rounded_rectangle([cx - 24, 596, cx + 24, 676], radius=22,
                        fill=(36, 36, 40, 255))
    for gy in range(608, 668, 12):  # グリル
        d.line([(cx - 17, gy), (cx + 17, gy)], fill=(88, 88, 96, 255), width=3)
    return img


# ---------------------------------------------------------------- 音声

def load_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as f:
        assert f.getframerate() == SR and f.getnchannels() == 1
        data = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)
    return data.astype(np.float32) / 32768.0


def load_mp3(path: Path) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le",
         "-ac", "1", "-ar", str(SR), "-"],
        check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def frame_envelope(samples: np.ndarray, n_frames: int) -> np.ndarray:
    """フレームごとの RMS を 0..1 に正規化（口パク・揺れの駆動源）。"""
    hop = SR // FPS
    n = min(n_frames, len(samples) // hop)
    rms = np.sqrt(np.mean(
        samples[: n * hop].reshape(n, hop) ** 2, axis=1))
    env = np.zeros(n_frames, dtype=np.float32)
    env[:n] = rms
    active = env[env > 0.01]
    if len(active):
        env = np.clip(env / np.percentile(active, 95), 0, 1)
    smooth = np.empty_like(env)  # アタック即・リリース緩めの片極スムージング
    acc = 0.0
    for i, v in enumerate(env):
        acc = max(v, acc * 0.86)
        smooth[i] = acc
    return smooth


def mix_audience(base: np.ndarray, timeline: list[dict]) -> np.ndarray:
    """笑い声 SFX をツッコミの決めゼリフ直後に重ねる。素材が無ければ素通し。"""
    cues = []
    for e in timeline:
        if e["speaker"] != "tsukkomi":
            continue
        for phrase, name in LAUGH_RULES:
            if phrase in e["text"] and (SFX_DIR / f"{name}.mp3").exists():
                cues.append((e["end_ms"], name, e["text"][:16]))
                break
    if not cues:
        print("sfx   笑い声素材なし（assets/sfx/ 未生成）→ 素の音声を使用")
        return base

    tail = int(SR * 8)
    out = np.zeros(len(base) + tail, dtype=np.float32)
    out[: len(base)] = base
    last_end = len(base)
    for end_ms, name, head in cues:
        sfx = load_mp3(SFX_DIR / f"{name}.mp3") * LAUGH_GAIN[name]
        at = int((end_ms - 200) / 1000 * SR)
        seg = sfx[: len(out) - at]
        out[at: at + len(seg)] += seg
        if name == "applause_end":
            last_end = max(last_end, at + len(seg))
        print(f"laugh {name:13s} @ {end_ms / 1000:6.1f}s  ({head}…)")
    out = out[: last_end + int(SR * 0.5)]
    peak = np.abs(out).max()
    if peak > 0.98:
        out *= 0.98 / peak
    return out


# ---------------------------------------------------------------- 合成

def speaker_per_frame(timeline: list[dict], n_frames: int) -> list[str]:
    """各フレームでカメラが向くべき話者。かぶせは後から始まった側が勝つ。"""
    spk = [""] * n_frames
    for e in sorted(timeline, key=lambda x: x["start_ms"]):
        f0 = int(e["start_ms"] / 1000 * FPS)
        f1 = min(int(e["end_ms"] / 1000 * FPS) + 1, n_frames)
        for i in range(f0, f1):
            spk[i] = e["speaker"]
    cur = "tsukkomi"
    for i in range(n_frames):  # セリフ間の空白は直前の話者を見続ける
        cur = spk[i] = spk[i] or cur
    return spk


class CharAnimator:
    def __init__(self, speaker: str, env: np.ndarray, phase: float,
                 cfg: dict):
        self.sprites = load_or_draw_sprites(
            speaker, cfg.get("char_h", CHAR_H))
        self.env = env
        self.phase = phase
        self.x = cfg.get("pos_x", POS_X[speaker])
        self.floor_y = cfg.get("floor_y", FLOOR_Y)
        self.blink_period = 3.4 + phase  # 2人で周期をずらす

    def frame(self, i: int) -> tuple[Image.Image, int, int]:
        t = i / FPS
        e = float(self.env[i]) if i < len(self.env) else 0.0
        talking = e > 0.06
        blink = (t + self.phase * 2.1) % self.blink_period < 0.13
        if talking and (i // 3) % 2 == 0:
            key = "open_blink" if blink else "open"
        else:
            key = "blink" if blink else "closed"
        sp = self.sprites[key]
        # 体の揺れ: 喋り中は声に合わせて弾み、待機中はゆっくり呼吸
        tilt = 2.1 * math.sin(2 * math.pi * 1.5 * t + self.phase) * e
        if abs(tilt) > 0.2:
            sp = sp.rotate(tilt, resample=Image.BILINEAR, expand=False,
                           center=(sp.width // 2, sp.height))
        dx = round(3 * math.sin(2 * math.pi * 0.14 * t + self.phase * 3))
        dy = round(-7 * e + 2 * math.sin(2 * math.pi * 0.27 * t + self.phase))
        return sp, self.x - sp.width // 2 + dx, self.floor_y - sp.height + dy


def main() -> None:
    preview = []
    if "--preview" in sys.argv:
        preview = [float(s) for s in
                   sys.argv[sys.argv.index("--preview") + 1].split(",")]

    timeline = json.loads((AUDIO_DIR / "timeline.json").read_text())
    base = load_wav(AUDIO_DIR / "manzai.wav")
    mixed = mix_audience(base, timeline)
    n_frames = math.ceil(len(mixed) / SR * FPS)

    layout_path = IMAGES_DIR / "layout.json"
    layout = (json.loads(layout_path.read_text())
              if layout_path.exists() else {})
    stems = {s: load_wav(AUDIO_DIR / f"stem_{s}.wav")
             for s in ("boke", "tsukkomi")}
    chars = {s: CharAnimator(s, frame_envelope(stems[s], n_frames), ph,
                             layout.get(s, {}))
             for s, ph in (("boke", 0.0), ("tsukkomi", 1.7))}
    cam_target = speaker_per_frame(timeline, n_frames)

    stage = draw_stage()
    # 外部の舞台画像には実物のマイクが写っているので描き足さない
    mic = None if (IMAGES_DIR / "stage.png").exists() else draw_mic()
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    proc = None
    if not preview:
        mix_path = AUDIO_DIR / "manzai_audience.wav"
        with wave.open(str(mix_path), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(SR)
            f.writeframes((mixed * 32767).astype(np.int16).tobytes())
        out_path = VIDEO_DIR / "manzai_duo.mp4"
        proc = subprocess.Popen(
            ["ffmpeg", "-y", "-v", "error",
             "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{OUT[0]}x{OUT[1]}", "-r", str(FPS), "-i", "-",
             "-i", str(mix_path),
             "-c:v", "libx264", "-preset", "medium", "-crf", "19",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
             "-shortest", str(out_path)],
            stdin=subprocess.PIPE)

    cam_x = 960.0
    if layout:  # 実写素材は元動画の画角を活かしてほぼ引きのまま
        crop_w0, crop_h0, pan = 1840, 1035, 40
    else:
        crop_w0, crop_h0, pan = 1664, 936, 70
    targets = ({int(t * FPS) for t in preview} if preview
               else range(n_frames))
    for i in range(n_frames):
        # カメラ: 話者側へゆっくりパン + かすかな呼吸ズーム
        want = 960 + (-pan if cam_target[i] == "boke" else pan)
        cam_x += (want - cam_x) * 0.035
        if preview and i not in targets:
            continue
        zoom = 1 + 0.012 * math.sin(2 * math.pi * i / (FPS * 16))
        cw, ch = crop_w0 / zoom, crop_h0 / zoom

        frame = stage.copy()
        for s in ("boke", "tsukkomi"):
            sp, x, y = chars[s].frame(i)
            frame.paste(sp, (x, y), sp)
        if mic is not None:
            frame.paste(mic, (0, 0), mic)

        x0 = min(max(cam_x - cw / 2, 0), CANVAS[0] - cw)
        # 実写素材は足元が下端にあるので下基準で切る
        y0 = CANVAS[1] - ch if layout else min(max(516 - ch / 2, 0),
                                               CANVAS[1] - ch)
        frame = frame.crop((round(x0), round(y0),
                            round(x0 + cw), round(y0 + ch)))
        frame = frame.resize(OUT, Image.BILINEAR)

        if preview:
            p = VIDEO_DIR / f"preview_{i / FPS:.0f}s.png"
            frame.save(p)
            print(f"prev  {p.name}")
        else:
            proc.stdin.write(np.asarray(frame, dtype=np.uint8).tobytes())
            if i % (FPS * 10) == 0:
                print(f"render {i / FPS:5.1f}s / {n_frames / FPS:.1f}s")

    if proc:
        proc.stdin.close()
        proc.wait()
        if proc.returncode != 0:
            sys.exit("ffmpeg failed")
        print(f"done: {VIDEO_DIR / 'manzai_duo.mp4'}")


if __name__ == "__main__":
    main()
