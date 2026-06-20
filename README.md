# manzai-studio

漫才台本から M-1 風の映像付きネタ動画を作るパイプライン。

```
台本 JSON ──> ① TTS (ElevenLabs v3) ──> ② 間・かぶせ調整 + 結合 ──> ③ 映像化
              1セリフ = 1音声ファイル      完成音声 + タイムライン        カット割り / 2人立ち絵動画
```

## セットアップ（uv）

```sh
uv sync
cp .env.example .env   # ELEVENLABS_API_KEY を記入
```

> 動画生成（MultiTalk / LongCat-Video-Avatar）まで含むフルセットアップ手順は
> **[docs/SETUP.md](docs/SETUP.md)** を参照（Blackwell GPU 対応・既知のハマりどころ含む）。

`assets/scripts/manjaro.json` の `voice_id` を自分の ElevenLabs ボイスに差し替える
（[Voice Library](https://elevenlabs.io/app/voice-library) で日本語男性ボイスを2つ選ぶ。
ツッコミは張りのある声、ボケは飄々とした声が合う）。

## 使い方

```sh
# ① セリフごとに TTS 音声を生成（生成済みはスキップされる）
uv run python scripts/generate_lines.py assets/scripts/manjaro.json

# ② 間 (gap_ms) を反映して1本に結合。タイムラインと話者別ステムも出力
uv run python scripts/assemble_audio.py assets/scripts/manjaro.json

# ③a 話者カット割りのプレビュー動画
uv run python scripts/make_cut_video.py

# ③b 客の笑い声を生成（任意・1回だけでよい）→ 2人立ち絵の引き画動画
uv run python scripts/generate_sfx.py
uv run python scripts/make_duo_video.py            # --preview 5,30,60 で静止画確認

# ③c (任意) 実写の漫才動画から立ち絵・舞台を切り出して差し替える
#    assets/groundtruth/ に固定カメラの引き画動画を置き、
#    extract_sprites.py の FRAMES/CROP を口開き・口閉じの時刻に合わせる
uv run python scripts/extract_sprites.py
```

成果物:

| パス | 内容 |
|---|---|
| `output/lines/*.mp3` | セリフ単位の TTS 音声 |
| `output/audio/manzai.wav` | 完成音声（全体ミックス） |
| `output/audio/manzai_audience.wav` | 笑い声入りミックス（duo 動画用） |
| `output/audio/stem_<speaker>.wav` | 話者別ステム（口パク・リップシンク用） |
| `output/audio/timeline.json` | 各セリフの開始/終了時刻と話者 |
| `output/video/manzai_cut.mp4` | 話者カット割り動画 |
| `output/video/manzai_duo.mp4` | 2人立ち絵・口パク・笑い声入りの引き画動画 |

`make_duo_video.py` はステムの音量で口パクと体の揺れを駆動し、カメラが話者側へ
ゆっくり寄る。立ち絵・舞台は `assets/images/` に画像を置けば差し替わる
（`stage.png`, `<speaker>_open.png`, `<speaker>_closed.png`, 任意で `_blink.png`。
無ければフラットデザインを自動描画）。`layout.json` があれば立ち位置・身長も
それに従う（`extract_sprites.py` が実写から自動生成する）。笑い声は
`assets/sfx/*.mp3` があるときだけツッコミの決めゼリフ（〜やないかい 等）の
直後にミックスされる。

実写素材は私的利用の範囲で。切り出した立ち絵・舞台や本人の声まねボイスを
含む動画を公開すると、著作権・肖像権に触れるので注意。

## 台本フォーマット

```jsonc
{
  "title": "ネタ名",
  "speakers": {
    "boke":     { "name": "ボケ",     "voice_id": "..." },
    "tsukkomi": { "name": "ツッコミ", "voice_id": "..." }
  },
  "lines": [
    // gap_ms: 直前のセリフ終わりからの間。負値で「かぶせ」（食い気味ツッコミ）
    { "speaker": "tsukkomi", "text": "どうもー", "gap_ms": 0 },
    { "speaker": "boke", "text": "[laughs] いきなりやけどな", "gap_ms": 250 }
  ]
}
```

- `[laughs]` `[sighs]` などの ElevenLabs v3 オーディオタグがそのまま使える
- 漫才のテンポの目安: ボケ→ツッコミは 100–250ms、強いツッコミは -150ms 前後のかぶせ、
  天丼や転換の前は 600ms 以上空ける

## ④ 本番映像（リップシンク）

プレビューの先、M-1 風の実写質感にする手順:

1. 漫才師風の立ち姿画像を2枚用意（画像生成 AI 可）→ `assets/images/boke.png` / `tsukkomi.png`
2. [Hedra](https://www.hedra.com) / OmniHuman / Kling の lip-sync に
   「キャラ画像 + `stem_<speaker>.wav`」を渡して話者ごとのリップシンク動画を生成
3. `output/audio/timeline.json` の時刻でカットを切り替えて編集
   （CapCut でもいいし、`make_cut_video.py` の concat リストを流用してもよい）
