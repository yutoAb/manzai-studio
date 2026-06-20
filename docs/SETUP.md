# セットアップ手順（OSS向け）

漫才台本 → 音声(TTS) → 音声駆動の会話動画、までを再現するための手順。
構成は3パート:

- **A. 音声パイプライン**（このリポジトリ） … 台本JSON→TTS→ミックス＋話者別ステム
- **B. 動画生成**（外部モデル：MultiTalk もしくは LongCat-Video-Avatar） … 参照画像＋話者別音声→リップシンク動画
- **C. 仕上げ** … 連続生成・完成音声を被せ

> NVIDIA **Blackwell (sm_120)** GPU では上流READMEの torch 指定が動かないため、本書の指定（cu128 系）に従うこと。検証環境: RTX PRO 6000 Blackwell (97GB), CUDA 12.8, Python 3.10/3.12, uv。

---

## 前提

| 必要なもの | 補足 |
|---|---|
| NVIDIA GPU（24GB+、Blackwellなら下記注意） | 動画生成に必須 |
| [uv](https://docs.astral.sh/uv/) | Python環境管理 |
| ffmpeg **5以降** | 旧4.x は `adelay all=` / `amix normalize=` / `apad whole_dur=` 等が無く assemble が失敗。古い場合は `imageio-ffmpeg` 同梱の ffmpeg を使う（後述） |
| ElevenLabs API キー | TTS / 効果音生成 |
| HuggingFace アカウント（`hf` CLI） | 重みDL |

---

## A. 音声パイプライン（このリポジトリ）

```sh
git clone <this-repo> manzai-studio && cd manzai-studio
uv sync
cp .env.example .env      # ELEVENLABS_API_KEY を記入
```

台本 `assets/scripts/<name>.json`（話者ごとの `voice_id` / `voice_settings`、各セリフの `gap_ms`＝間。負値で「かぶせ」）を用意して:

```sh
uv run python scripts/generate_lines.py assets/scripts/<name>.json   # セリフ別 mp3
uv run python scripts/assemble_audio.py assets/scripts/<name>.json   # manzai.wav + stem_<spk>.wav + timeline.json
```

出力 `output/audio/`:
- `manzai.wav` … 完成ミックス（被せ用）
- `stem_boke.wav` / `stem_tsukkomi.wav` … 話者別ステム（**動画生成の駆動音声**）
- `timeline.json` … 各セリフの開始/終了

> **ffmpeg が古い場合**: imageio-ffmpeg の同梱版（7.0.2）を使う。
> ```sh
> uv run python -c "import imageio_ffmpeg,os,subprocess;print(imageio_ffmpeg.get_ffmpeg_exe())"
> mkdir -p ~/.local/ffbin && ln -sf <上のパス> ~/.local/ffbin/ffmpeg
> PATH="$HOME/.local/ffbin:$PATH" uv run python scripts/assemble_audio.py ...
> ```

参照画像（2人のツーショット）は実写動画から抽出する。`assets/groundtruth/<名>/videoplayback.mp4` を置き、`prepare_multitalk.py`（`REF_T` 秒のフレーム）等で `reference.png` を得る。`groundtruth/` は `.gitignore` 済み（著作権・肖像権に注意、私的利用の範囲で）。

---

## B-1. MultiTalk（MeiGen-AI）

```sh
git clone https://github.com/MeiGen-AI/MultiTalk && cd MultiTalk
uv venv --python 3.10 .venv
# Blackwell: 上流READMEの torch2.4.1+cu121 ではなく cu128 を使う
uv pip install --python .venv/bin/python torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 \
  --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv/bin/python xformers==0.0.32.post1 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv/bin/python -r requirements.txt "misaki[en]" librosa
```

### Blackwell 用パッチ（flash_attn を使わない）

`nvcc` 無し環境では flash-attn をビルドできないため、xformers + SDPA で代替する。

1. `wan/modules/attention.py`
   - `import xformers.ops` の `memory_efficient_attention(..., op=None)` を **`op=xformers.ops.MemoryEfficientAttentionCutlassOp`** に変更（Blackwellは既定で壊れたHopper FA3に振られるため）。
   - `flash_attention()` を、FA未導入時は SDPA(`scaled_dot_product_attention`) にフォールバックさせる（`k_lens` のパディングは attn_mask で再現）。
2. `wan/modules/clip.py` … `flash_attention(...)` 直呼びを、フォールバック付きの `attention(...)` に変更。
3. `generate_multitalk.py` … `Wav2Vec2Model.from_pretrained(..., attn_implementation="eager")`（transformers 5系で `output_attentions` が sdpa拒否になるため）。

### 重み

```sh
# 標準(fp16)。ディスクが厳しければ int8(MeiGen-MultiTalk の quant_models) を使う
hf download Wan-AI/Wan2.1-I2V-14B-480P --local-dir weights/Wan2.1-I2V-14B-480P
hf download TencentGameMate/chinese-wav2vec2-base --local-dir weights/chinese-wav2vec2-base
hf download TencentGameMate/chinese-wav2vec2-base model.safetensors --revision refs/pr/1 --local-dir weights/chinese-wav2vec2-base
hf download MeiGen-AI/MeiGen-MultiTalk --local-dir weights/MeiGen-MultiTalk
# 本家 README「Link or Copy MultiTalk Model」に従い index.json / multitalk.safetensors を Wan2.1 dir に組込む
```

高速化は **FusionX LoRA（8ステップ蒸留）** が有効。int8+FusionX なら `--quant int8 --quant_dir weights/MeiGen-MultiTalk --lora_dir .../quant_model_int8_FusionX.safetensors --sample_steps 8 --sample_text_guide_scale 1 --sample_audio_guide_scale 2 --sample_shift 2`。VRAMに余裕があれば `--offload_model False`（既定は単GPUでTrue＝遅い）。

実行は本リポジトリ `scripts/prepare_multitalk.py` が `manzai/` フォルダ一式と `run_multitalk.sh` を生成するので、それを MultiTalk リポジトリ直下に置いて回す。詳細は [`docs/MULTITALK.md`](./MULTITALK.md)（※conda/cu121の記述は本書の cu128 で読み替え）。

---

## B-2. LongCat-Video-Avatar-1.5（推奨 / MultiTalkの後継）

長尺安定・分割不要・最速。複数人（マルチストリーム音声）対応。

```sh
git clone --single-branch --branch main https://github.com/meituan-longcat/LongCat-Video && cd LongCat-Video
uv venv --python 3.10 .venv
uv pip install --python .venv/bin/python torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 \
  --index-url https://download.pytorch.org/whl/cu128
# requirements は torch==2.6 / flash-attn / tritonserverclient(存在しない) / sympy ピンを除外して入れる
grep -viE '^torch==|^flash[-_]attn|^libsndfile1|^tritonserverclient|^sympy==' requirements.txt requirements_avatar.txt > /tmp/lc_req.txt
uv pip install --python .venv/bin/python --index-strategy unsafe-best-match -r /tmp/lc_req.txt \
  xformers==0.0.32.post1 accelerate --extra-index-url https://download.pytorch.org/whl/cu128
```

### Blackwell 用パッチ

1. **attention（xformers + Cutlass op固定）**: `longcat_video/modules/attention.py`（2箇所）と `longcat_video/modules/avatar/attention.py`（2箇所）の `memory_efficient_attention(..., op=None)` を **`op=xformers.ops.MemoryEfficientAttentionCutlassOp`** に。
2. **モデル設定で xformers を有効化**: 使う DiT の `config.json`（fp16 なら `base_model/config.json`、int8 なら `base_model_int8/config.json`）で `enable_flashattn2=false`, `enable_xformers=true`。
3. **CPUメモリOOM対策（重要）**: `run_demo_avatar_multi_audio_to_video.py` の text_encoder / vae を**読み込み直後にGPUへ**移す（`from_pretrained(..., low_cpu_mem_usage=True).to(f"cuda:{local_rank}")`）。
4. **int8は使わずfp16を使う**: int8ローダ(`load_quantized_dit`)は14Bを**fp32実体でCPUに確保(~56GB)**しOOMしやすい。**`--use_int8` を付けず fp16 `base_model`** を使う（diffusersの from_pretrained は meta初期化でCPUピーク~32GB）。GPUは97GBあるのでfp16が載る。

### 重み（NASなど大容量先へ）

```sh
# text_encoder/vae/tokenizer/scheduler のみ（dit本体60GBは不要）
hf download meituan-longcat/LongCat-Video --local-dir weights/LongCat-Video --exclude "dit/*"
# avatar 本体（fp16 base_model + whisper + distill LoRA + vocal_separator）
hf download meituan-longcat/LongCat-Video-Avatar-1.5 --local-dir weights/LongCat-Video-Avatar-1.5
# ※ weights/LongCat-Video と weights/LongCat-Video-Avatar-1.5 を兄弟ディレクトリに置く
#   （avatarデモが ../LongCat-Video から text_encoder/vae を参照する）
```

### 入力と実行

`input.json` を作る（**話者別ステムを16k monoで、audio_type は `para`**＝同一タイムライン）:

```json
{
  "prompt": "Static camera, two Japanese comedians ... upper-body two-shot, sharp focus.",
  "cond_image": "manzai_input/reference.png",
  "cond_audio": { "person1": "manzai_input/p1.wav", "person2": "manzai_input/p2.wav" },
  "audio_type": "para"
}
```

```sh
.venv/bin/torchrun run_demo_avatar_multi_audio_to_video.py \
  --input_json manzai_input/input.json \
  --checkpoint_dir weights/LongCat-Video-Avatar-1.5 \
  --model_type avatar-v1.5 --use_distill \
  --num_segments <尺×25/80+1 程度> --resolution 480p \
  --output_dir ./outputs
```

> 補足:
> - `--use_distill` で 8ステップ。`outputs/video_continue_N.mp4` の最大Nが完成動画（音声は駆動音声がミックス済み）。
> - **片方を黙らせたい区間**（挨拶など）は、ボーカル分離が純無音を拒否するため person 側に**極小ノイズ**(`anoisesrc=a=0.004`)を渡す。
> - 入退場の礼は別生成（プロンプト＋`--text_guidance_scale 7`）し、**前パートの最終フレームを次の `cond_image`** にして繋ぐと動作が地続きになる。

---

## C. 仕上げ（音声を被せて完成）

生成動画に完成音声 `manzai.wav` を被せる（webview再生用に faststart 推奨）:

```sh
ffmpeg -i outputs/video_continue_N.mp4 -i output/audio/manzai.wav \
  -map 0:v -map 1:a -c:v copy -c:a aac -shortest -movflags +faststart final.mp4
```

---

## 既知のハマりどころ（早見表）

| 症状 | 原因 / 対処 |
|---|---|
| `no kernel image available` | Blackwell に cu121/cu124 torch → **cu128 系**に |
| xformers `invalid argument`(hopper) | 既定opがFA3 → **Cutlass op固定** |
| `No module named flash_attn` | configを xformers有効化 / SDPAフォールバック |
| wav2vec `output_attentions ... sdpa` | `attn_implementation="eager"` |
| 学習/生成中に `SIGKILL`(OOM) | int8ローダのfp32確保 → **fp16**＋text_encoder早期GPU移動 |
| 口パクが2倍長/ズレ | `audio_type` を **`para`**（`add`は逐次連結で2倍長） |
| assemble が ffmpeg で失敗 | 旧ffmpeg → **imageio-ffmpeg(7.0.2)** |
| `while read` ループ中に行が壊れる | ループ内 ffmpeg に **`-nostdin`** |
| v3タグ(`[curious]`等)が読み上げられる | タグを外し `voice_settings`＋句読点で表現 |
| VS Codeで動画が `Failed to load` | `-movflags +faststart` 化、もしくはブラウザ/ローカル再生 |
