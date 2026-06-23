# manzai-studio

漫才台本から M-1 風の映像付きネタ動画を作るパイプライン。

```
台本 JSON ──> ① TTS (ElevenLabs v3) ──> ② 間・かぶせ調整 + 結合 ──> ③ 映像化
              1セリフ = 1音声ファイル      完成音声 + 話者別ステム      カット割り / 2人立ち絵 /
                                          + タイムライン               音声駆動アバター(LongCat)
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
    { "speaker": "boke", "text": "いきなりやけどな", "gap_ms": 250 },
    // <...> は非言語の効果音キュー。TTSせず別途SFXを差し込む（例: <叩く> <リップ音>）
    { "speaker": "tsukkomi", "text": "<叩く>", "gap_ms": -100 }
  ]
}
```

- 各行・各話者に `voice_settings`（`stability` / `style` 等）を持たせて上書き可。
  後半ほど `stability`↓ / `style`↑ にランプさせると、エスカレーションが少し付く
- **かぶせ（負 `gap_ms`）の区間は、被せられる側を自動でダッキング**（`assemble_audio.py` の `DUCK`）
- `<...>` の行は効果音キュー扱い（`generate_lines.py` はTTSせずスキップ。別途 `sound-generation` 等で当てる）
- ⚠ ElevenLabs v3 は `[laughs]` 等の角括弧タグを**読み上げてしまう**ことがある。
  抑揚は角括弧タグでなく `voice_settings`＋句読点・「…」で表現する
- 漫才のテンポの目安: ボケ→ツッコミは 100–250ms、強いツッコミは -150ms 前後のかぶせ、
  天丼や転換の前は 600ms 以上空ける

## ④ 本番映像（音声駆動アバター / リップシンク）

現在の主力は **[LongCat-Video-Avatar-1.5](https://huggingface.co/meituan-longcat/LongCat-Video-Avatar-1.5)**
（MultiTalk 後継）の **multi-audio**（2話者同時）モード。2人ツーショットの参照画像と
話者別ステムを渡すと、話者ごとにリップシンクした掛け合い動画を1本で生成できる。

```
2人ツーショット参照画像 + person1=stem_boke.wav + person2=stem_tsukkomi.wav (audio_type=para)
  └─> run_demo_avatar_multi_audio_to_video.py ─> video_continue_N.mp4（音声 mux 済み）
```

- 参照画像は実写素材から1フレーム抜く / 画像生成 AI で用意（白背景・上半身ツーショット推奨）。
- 駆動音声は `assemble_audio.py` が出す `stem_<speaker>.wav` を 16kHz mono に変換して使う。
- 長尺は `num_segments` を伸ばす（1セグメント ≈ 先頭3.7s + 以降3.2s/seg）。
- セットアップ・実行コマンド・**共有マシンでの OOM 回避（bf16＋単一プロセス）**等のハマりどころは
  **[docs/SETUP.md](docs/SETUP.md)** を参照。
- 既知の弱点: 長時間生成での**顔の identity ドリフト**、左下のウォーターマーク幻影、
  極端な同時発話下でのリップシンク不安定（→ [docs/research_fullduplex_manzai.md](docs/research_fullduplex_manzai.md)）。

**代替（商用 API）**: [Hedra](https://www.hedra.com) / OmniHuman / Kling の lip-sync に
「キャラ画像 + `stem_<speaker>.wav`」を渡して話者ごとに生成し、`timeline.json` の時刻で
カットを切り替えて編集する方法もある。

## ドキュメント / リサーチ

| ファイル | 内容 |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | フルセットアップ（Blackwell GPU・LongCat/MultiTalk・既知のハマりどころ） |
| [docs/research_fullduplex_manzai.md](docs/research_fullduplex_manzai.md) | フルデュプレックス漫才（重なり・大動作）の動画生成リサーチと到達点 |
| [docs/RELATED_WORK.md](docs/RELATED_WORK.md) | 関連研究（talking-head / 対話音声 / ジェスチャー生成） |
| [docs/MULTITALK.md](docs/MULTITALK.md) | MultiTalk 用の入力生成・実行メモ |

実績の目安: 令和ロマン風ネタ ~108秒、かまいたち実ネタ ~285秒（全ネタ通し）を
本パイプラインで生成済み（ターン型・重なり型いずれも一本完走を確認）。
