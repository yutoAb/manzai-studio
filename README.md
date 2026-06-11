# manzai-studio

漫才台本から M-1 風の映像付きネタ動画を作るパイプライン。

```
台本 JSON ──> ① TTS (ElevenLabs v3) ──> ② 間・かぶせ調整 + 結合 ──> ③ 映像化
              1セリフ = 1音声ファイル      完成音声 + タイムライン        カット割り動画 / リップシンク
```

## セットアップ

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # ELEVENLABS_API_KEY を記入
```

`assets/scripts/manjaro.json` の `voice_id` を自分の ElevenLabs ボイスに差し替える
（[Voice Library](https://elevenlabs.io/app/voice-library) で日本語男性ボイスを2つ選ぶ。
ツッコミは張りのある声、ボケは飄々とした声が合う）。

## 使い方

```sh
# ① セリフごとに TTS 音声を生成（生成済みはスキップされる）
python scripts/generate_lines.py assets/scripts/manjaro.json

# ② 間 (gap_ms) を反映して1本に結合。タイムラインと話者別ステムも出力
python scripts/assemble_audio.py assets/scripts/manjaro.json

# ③ 立ち絵カット割りのプレビュー動画を生成（画像が無ければプレースホルダを自動生成）
python scripts/make_cut_video.py
```

成果物:

| パス | 内容 |
|---|---|
| `output/lines/*.mp3` | セリフ単位の TTS 音声 |
| `output/audio/manzai.wav` | 完成音声（全体ミックス） |
| `output/audio/stem_<speaker>.wav` | 話者別ステム（リップシンク用） |
| `output/audio/timeline.json` | 各セリフの開始/終了時刻と話者 |
| `output/video/manzai_cut.mp4` | 立ち絵カット割り動画 |

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
