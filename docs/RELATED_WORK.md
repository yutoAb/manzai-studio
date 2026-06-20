# 関連研究メモ

manzai-studio を OSS 化・記事化・研究発表するときに参照できる既存研究の整理。
現時点の立ち位置は、新しい基盤モデルの提案ではなく、漫才台本を音声・タイムライン・話者別ステム・音声駆動アバター動画へ接続する制作支援パイプラインである。

## 現在の生成バックエンド

このリポジトリの `README.md` と `docs/MULTITALK.md` は MultiTalk を中心に書かれているが、実際の出力履歴を見ると `output/longcat_manzai_v*.mp4` が継続的に作られており、現行の実験・制作上のメインは LongCat-Video-Avatar-1.5 側と見るのが妥当。

一方で、コードとして残っている自動化は `scripts/prepare_multitalk.py` が中心で、LongCat 用の入力生成・実行手順はまだドキュメント化されていない。OSS 化するなら、README の「本番映像」節を LongCat-Video-Avatar-1.5 前提に更新し、MultiTalk は旧ルートまたは代替バックエンドとして分けるのがよい。

## 近い研究領域

### 1. 日本語ユーモア評価・大喜利

Oogiri-Master は、大喜利を使って LLM のユーモア理解を評価するベンチマークである。約100個の候補回答を約100人が独立評価し、人気バイアスを避けた面白さ評価を設計している。manzai-studio とは「日本語ユーモア」という点で近いが、目的は制作ではなく評価である。

- Oogiri-Master: Benchmarking Humor Understanding via Oogiri
- URL: https://arxiv.org/abs/2512.21494

Assessing the Capabilities of LLMs in Humor は、大喜利生成・評価を Novelty, Clarity, Relevance, Intelligence, Empathy, Overall Funniness の複数観点で評価する。漫才台本の主観評価を設計する際の尺度として参考になる。

- Assessing the Capabilities of LLMs in Humor: A Multi-dimensional Analysis of Oogiri Generation and Evaluation
- URL: https://arxiv.org/abs/2511.09133

### 2. 漫才・視聴者反応データセット

ManzaiSet は、日本語漫才を見ている視聴者の顔動画・音声反応を集めたマルチモーダルデータセットである。241人の参加者がプロの漫才を視聴し、その反応を分析している。生成ではなく視聴反応の研究だが、「漫才 + マルチモーダル + 評価」という点で最もドメインが近い。

- ManzaiSet: A Multimodal Dataset of Viewer Responses to Japanese Manzai Comedy
- URL: https://arxiv.org/abs/2510.18014

manzai-studio 側で研究化する場合、ManzaiSet 的な視聴者反応評価を小規模に取り入れると説得力が出る。たとえば、同じ台本について「間・かぶせあり」と「均等間隔」の動画を比較し、面白さ・自然さ・テンポを評価する。

### 3. 掛け合い芸・台本生成

Chinese Comical Crosstalk の研究は、中国の相声という二人掛け合い芸のスクリプト生成を扱っている。データセットを作り、言語モデルで生成し、人間評価しているため、漫才台本生成の先行研究としてかなり近い。

- Can Language Models Make Fun? A Case Study in Chinese Comical Crosstalk
- URL: https://arxiv.org/abs/2207.00735

ただし、この研究の主眼はテキスト台本生成であり、音声化、話者別ステム、リップシンク、カメラ・映像化までは扱わない。manzai-studio の差分は、台本を最終的な会話動画制作へ接続する実装にある。

### 4. 音声駆動の複数人会話動画生成

MultiTalk は、複数人の音声入力から会話動画を生成する研究で、複数音声と人物の対応付け問題を扱う。manzai-studio の MultiTalk ルートはこの研究を下流の生成器として使う設計である。

- Let Them Talk: Audio-Driven Multi-Person Conversational Video Generation
- URL: https://arxiv.org/abs/2505.22647

TAVID は、テキスト対話と参照画像から会話音声と対話映像を同時生成する枠組みである。manzai-studio の理想形に近いが、対象は汎用会話であり、漫才特有のボケ・ツッコミ、間、かぶせ、観客笑いなどは中心ではない。

- TAVID: Text-Driven Audio-Visual Interactive Dialogue Generation
- URL: https://arxiv.org/abs/2512.20296

### 5. LongCat-Video-Avatar-1.5 周辺

LongCat-Video-Avatar-1.5 は、音声駆動アバター動画生成の OSS フレームワークで、商用品質に近い安定性を重視している。論文上は、Whisper Large への音声エンコーダ更新、長尺動画での identity consistency、全身の時間的一貫性、8 NFE への高速化、500件超の評価ベンチマークなどが主張されている。

- LongCat-Video-Avatar 1.5 Technical Report
- URL: https://arxiv.org/abs/2605.26486

manzai-studio の現行メインを LongCat とするなら、研究上の位置付けは「LongCat を漫才制作へ応用したツール」ではなく、「漫才台本の構造を LongCat などの音声駆動アバター生成へ渡せる制作中間表現とパイプライン」とする方が強い。特定モデル依存を薄められ、MultiTalk / LongCat / HunyuanVideo-Avatar などに差し替えやすい。

近い競合・関連として HunyuanVideo-Avatar もある。こちらは複数キャラクター、感情制御、マルチキャラクター音声駆動アニメーションを扱っている。

- HunyuanVideo-Avatar: High-Fidelity Audio-Driven Human Animation for Multiple Characters
- URL: https://arxiv.org/abs/2505.20156

### 6. 単一人物のリップシンク・ポートレート生成

Wav2Lip, SadTalker, Hallo2 などは、単一人物のリップシンクや talking head 生成の代表的な関連研究である。manzai-studio の主目的は二人会話なので直接の競合ではないが、話者ごとのステムを作る設計の妥当性を説明する背景になる。

- A Lip Sync Expert Is All You Need for Speech to Lip Generation In The Wild
- URL: https://arxiv.org/abs/2008.10010
- SadTalker: Learning Realistic 3D Motion Coefficients for Stylized Audio-Driven Single Image Talking Face Animation
- URL: https://arxiv.org/abs/2211.12194
- Hallo2: Long-Duration and High-Resolution Audio-Driven Portrait Image Animation
- URL: https://arxiv.org/abs/2410.07718

### 7. 笑い声合成・観客反応

Laughter Synthesis は、日本語の in-the-wild 笑い声コーパスと笑い声合成手法を扱う。manzai-studio の観客笑い挿入は現状 SFX ベースだが、将来的に台本や間に合わせて笑い声を生成・配置する研究へ拡張するなら関連する。

- Laughter Synthesis using Pseudo Phonetic Tokens with a Large-scale In-the-wild Laughter Corpus
- URL: https://arxiv.org/abs/2305.12442

## manzai-studio の差別化ポイント

既存研究と比べたときの差分は、漫才特有の制作中間表現にある。

- 台本 JSON に `speaker`, `text`, `gap_ms` を持たせ、セリフ単位でタイミングを制御する。
- `gap_ms < 0` によってツッコミの「かぶせ」を表現できる。
- 1セリフ1音声ファイルにして、差し替え・再生成・テンポ調整を容易にする。
- 話者別ステムを作り、音声駆動アバター生成器に入力できる。
- 完成ミックス、話者ステム、タイムライン JSON を同時に出力する。
- 観客笑い・拍手などの SFX を台本タイミングに沿って挿入できる。
- MultiTalk や LongCat のような重い動画生成器の前段として、分割・整形・同期を担当する。

## 研究化する場合の打ち出し方

論文としては、新しい動画生成モデルではなく、Human-AI co-creation / creative support system / computational humor production tool として出すのが自然。

仮タイトル例:

- Manzai Studio: A Script-to-Avatar Pipeline for Japanese Comedy Dialogue Video Production
- Timing-Aware Co-Creation of Japanese Manzai Videos with Audio-Driven Avatars
- Controlling Ma and Overlap in AI-Assisted Japanese Manzai Video Production

評価実験を足すなら、次の比較が有効。

- `gap_ms` 制御あり vs 均等間隔
- かぶせあり vs かぶせなし
- 観客笑いあり vs なし
- LongCat 生成動画 vs 静止画口パク動画
- 台本だけ提示 vs 音声付き vs 動画付き

評価項目は、面白さ、テンポの自然さ、掛け合いらしさ、視聴継続意欲、制作時間短縮、編集しやすさなどが候補。

## OSS 化時の注意

- 実在芸人の画像・音声・台本・生成動画を含めない。
- `output/` の実験生成物は基本的に公開対象から外す。
- サンプル台本・サンプル画像・サンプル音声は権利クリアな架空キャラクターにする。
- README で LongCat をメイン、MultiTalk を代替バックエンドとして整理する。
- LongCat 用の入力生成・実行手順を `docs/LONGCAT.md` として追加する。
- API キー、ボイス ID、サーバパス、私的利用素材のパスを `.env.example` と `.gitignore` で分離する。
