# MultiTalk で漫才動画を作る（研究室サーバ手順）

[MultiTalk](https://github.com/MeiGen-AI/MultiTalk)（NeurIPS 2025, MeiGen-AI）は
「2人が写った参照画像 + 話者ごとの音声」から複数人の会話動画を生成する OSS。
本物の体の動き・ジェスチャー込みでリップシンクするので、現状の2コマ口パク
（issue #1, #3）を一気に解決できる。CUDA GPU 必須で Mac では動かないため、
研究室サーバ（RTX 4090 / A100 等, 24GB+）で回す。

## 0. Mac 側で入力を作る（済んでいれば不要）

```sh
uv run python scripts/prepare_multitalk.py
```

`output/multitalk/` に以下が出る（合計 ~21MB）。これをサーバに送る。

| 中身 | 説明 |
|---|---|
| `reference.png` | 2人のツーショット参照画像（960x540, groundtruth t=30s） |
| `full_mix.wav` | 完成音声（笑い声入り・最終トラック） |
| `segNN/input.json` | セグメントの MultiTalk 入力 |
| `segNN/p1.wav` / `p2.wav` | person1=ボケ(左) / person2=ツッコミ(右) の駆動音声 16kHz mono |
| `manifest.json` | 各セグメントの時間・セリフ |
| `durations.tsv` / `run_multitalk.sh` | 連結用の尺と実行スクリプト |

台本は約8秒ごと20セグメントに分割済み（境界はセリフ間の「間」の中点なので声を切らない）。

## 1. サーバに MultiTalk を用意

```sh
git clone https://github.com/MeiGen-AI/MultiTalk && cd MultiTalk

conda create -n multitalk python=3.10 -y && conda activate multitalk
pip install torch==2.4.1 torchvision==0.19.1 torchaudio==2.4.1 --index-url https://download.pytorch.org/whl/cu121
pip install -U xformers==0.0.28 --index-url https://download.pytorch.org/whl/cu121
pip install flash_attn==2.7.4.post1
pip install -r requirements.txt          # リポジトリ付属
conda install -c conda-forge ffmpeg -y

# 重み（HuggingFace）
pip install "huggingface_hub[cli]"
huggingface-cli download Wan-AI/Wan2.1-I2V-14B-480P --local-dir weights/Wan2.1-I2V-14B-480P
huggingface-cli download TencentGameMate/chinese-wav2vec2-base --local-dir weights/chinese-wav2vec2-base
huggingface-cli download MeiGen-AI/MeiGen-MultiTalk --local-dir weights/MeiGen-MultiTalk
# MeiGen-MultiTalk の重みを Wan のフォルダに組み込む手順は本家 README の
# 「Link or Copy MultiTalk Model」節に従うこと（バージョンで変わるため要確認）
```

## 2. 入力を送って実行

```sh
# Mac 側からサーバの MultiTalk リポジトリ直下へ。フォルダ名は manzai/ にする
scp -r output/multitalk/ user@server:/path/to/MultiTalk/manzai

# サーバ側・リポジトリ直下から
cd /path/to/MultiTalk
bash manzai/run_multitalk.sh          # STEPS=8 で高速版(LoRA併用時)
```

`run_multitalk.sh` がやること:
1. 各セグメントを `generate_multitalk.py --mode streaming` で生成（生成済みはスキップ）
2. 各動画を台本どおりの尺に正確に合わせる（足りない分は末尾フレームで補完）
3. 連結し、完成音声 `full_mix.wav`（笑い声入り）を被せて `manzai/manzai_multitalk.mp4` を出力

できた `manzai_multitalk.mp4` を Mac に戻せば完成。

## 3. 調整ポイント

- **flag はバージョン差あり**: `generate_multitalk.py` の引数名（`--ckpt_dir` 等）は
  使う MultiTalk のコミットで変わることがある。まず seg00 だけ手で1回流して通してから全体を回す。
- **左右が入れ替わる**: person1 が右に出たら、`input.json` に `bbox` を足して
  person1=左 / person2=右 を固定する（書式は本家 example を参照）。
- **同時発話**: 掛け合いは `audio_type: "add"`（加算）。被せ／同時に喋らせたい所だけ `"para"`。
- **VRAM 不足**: `--num_persistent_param_in_dit 0` 指定済み。それでも厳しければ
  解像度 480 のまま `--sample_steps` を 8〜10（LoRA 加速）に下げる。
- **品質 vs 速度**: `STEPS=40` が既定。1セグメント数分（4090・480p）×20 で数十分〜数時間。
- **参照画像の差し替え**: 別フレームにしたいなら `prepare_multitalk.py` の `REF_T` を変える。
  オリジナルの立ち絵に変えれば権利面もクリア（下記）。

## 4. 権利の注意

参照画像・駆動音声に実在の漫才師（groundtruth）の素材を使う版は **私的利用に限る**。
公開する場合は、参照画像をオリジナルの立ち絵に、声を別ボイスに差し替えること
（肖像権・著作権・ElevenLabs 規約）。関連: issue #2（ボイスクローン）, #3（体の動き）。
