# フルデュプレックス漫才の動画自動生成 — 解決策リサーチ

> 対象: かまいたち型（発話の重なり・割り込み・相槌が多く、身体の動きも大きいフルデュプレックス漫才）の、リップシンク付き動画自動生成。
> ミルクボーイ型（ターン制・低動作・重なり少）は現行パイプラインで成立するが、かまいたち型は破綻する、という観測が出発点。
> 手法: deep research（5角度の並列検索 → 21ソース取得 → 97主張抽出 → 上位25を3票の敵対的検証 → 24/25確認・1棄却 → 6知見に統合）。

---

## 結論（要約）

現行の `LongCat-Video-Avatar-1.5` パイプラインは**アーキテクチャ的には正解に近い**が、3点でミスマッチがあり、それぞれに 2024–2026 の具体的な解決候補がある。

1. **映像**: 正しいモデル種別は「マルチパーソン会話動画生成」。**音声↔人物の binding** と **インタラクティビティ（反応・タイミング）** を明示的に扱う系へアップグレードすべき。
   → MultiTalk（L-RoPE binding、LongCat para モードの源流）／AnyTalker（2025-11、interactivity 改良＋ベンチ）／InterDyad（2026-03、MLLM で反応タイミング）。大きな身体動作は audio-to-gesture 系（EMO2 / Cosh-DiT / SynTalker / CVPR2025 IMAE / Meta Seamless Interaction）。
2. **音声**: セリフ単位の孤立 TTS が cross-turn 韻律を平板化している（実測 F0 トレンド 生成 r=−0.26 vs 本物 r=+0.86、レンジ 12.3 vs 15.8 半音）。**重なり・無音・話者間コヒーレンスを同時生成する dialogue-aware / full-duplex 系**へ置き換えるべき。
   → CoVoMix2（実時間より速い・話者別ストリームで重なり/無音を明示制御）／MoonCast（長文2話者ポッドキャスト・cross-turn コヒーレンス）／Moshi（真の full-duplex 二重ストリーム）／CSM（文脈条件付きだが**英語専用で日本語不可**）。
3. **全体設計**: 「孤立 TTS＋機械的 amix → 単話者寄りアバター」という完全分離方式から、**重なり対応のマルチストリーム音声 →（マルチパーソン・インタラクティビティ対応アバター）** の二段構成へ寄せるのが evidence の収束方向。

**次に試すべき実験（推奨）**: 日本語の**重なり対応マルチストリーム対話音声**を CoVoMix2 / MoonCast 系で試作し、それを AnyTalker か LongCat の「真の multi-audio multi-person スクリプト（`run_demo_avatar_multi_audio_to_video.py` + 話者別 bbox）」に流し込む。評価指標は **F0 エスカレーション（目標 r≈+0.86・約15.8半音レンジ）** と **重なり忠実度**。

---

## 軸① 映像（動き＋リップシンク）

### A. マルチパーソン会話動画生成（本命の種別） — 確度: 高（3-0）

音声↔人物 binding と反応モデリングを明示的に解く系。現行の弱点そのものを狙っている。

| モデル | 出自 | 効くポイント |
|---|---|---|
| **MultiTalk** | arXiv:2505.22647, NeurIPS 2025 | 「Multi-Person Conversational Video Generation」タスクを定義。**L-RoPE（Label Rotary Position Embedding）** でマルチストリーム音声の「音声と人物の binding 問題」を解く。**LongCat の para 2ストリームの源流**。 |
| **AnyTalker** | arXiv:2511.23475 / HKUST-C4G, 2025-11 | 「multi-stream 構造で identity をスケールしつつ inter-identity interaction を保つ」。音声リスト長で**単/多話者を自動切替**。専用の **Interactivity ベンチ**（`calculate_interactivity.py`）同梱。タイトルが文字通り "Scaling Multi-Person Talking Video Generation with **Interactivity Refinement**"。 |
| **InterDyad** | arXiv:2603.23132v1 / Baidu, 2026-03 | 単一の2人参照フレーム＋デュアルトラック音声から自然な dyadic interaction を生成。**MLLM が音声から linguistic intent を抽出し、反応の「正確なタイミングと適切さ」を指示** → cross-turn の反応・相槌タイミングを直接ターゲット。 |

- ソース: arxiv.org/abs/2505.22647 ・ github.com/HKUST-C4G/AnyTalker ・ arxiv.org/abs/2511.23475 ・ arxiv.org/abs/2603.23132v1

### B. 音声駆動ジェスチャー／身体動作（大きな動きの担保） — 確度: 高（3-0）

漫才の「体の振り」を作る系。ただし多くは**単話者**、かつ動画でなく **motion/上半身出力**で、別途レンダ段が要る点に注意。

| モデル | 種別 | 注意 |
|---|---|---|
| **EMO2** | arXiv:2501.10687 / Alibaba, 2025-01 | 表情＋手ジェスチャーを同時生成（stage1: 音声→手ポーズ、stage2: 拡散で動画）。**単話者**。 |
| **Cosh-DiT** | arXiv:2503.09942 | 音声 Diffusion Transformer で発話リズム同期のジェスチャー。上半身＋顔＋手 → 動画レンダ。**単話者**。 |
| **CVPR2025 IMAE**（Li ら） | CVPR2025 | 単一参照画像＋音声から co-speech gesture 動画。推論時にポーズ/keypoint 不要、SMPL-X の Implicit Motion-Audio Entanglement で弱い音声制御を補強し手のボケを回避。**単話者**。 |
| **SynTalker** | arXiv:2410.00464 | 音声＋テキストで制御できる**全身** co-speech motion（上半身限定を超える）。出力は 3D/SMPL-X → 別レンダ要。 |
| **Meta Seamless Interaction** | arXiv:2506.22554 | **dyadic（2人）motion** を、相手の発話＋視覚挙動の双方で条件付け。出力は motion → 別レンダ要。 |

- 注意（caveat）: EMO2/Cosh-DiT/IMAE は単話者、SynTalker/Seamless は motion 出力で end-to-end の two-shot lip-sync 動画ではない。

### C. 現行 LongCat の位置づけ — 確度: 高（3-0）

- HF カードより: avatar-v1.5 は **Whisper-large-v3 audio encoder**（英語寄りの Wav2Vec2 を置換、日本語韻律に有利）。
- デュアル音声は **para（等長加算）** と **add（無音パディングの逐次連結）** をサポート、マルチパーソン会話可。**真の話者独立 lip-sync は別スクリプト** `run_demo_avatar_multi_audio_to_video.py`＋話者別 bbox。
- **棄却された主張（1-2）**: 「LongCat が大きな two-shot 動作でも full-body の時間的安定を保証する」は否決 → **大動作下の body-motion 安定性が弱点**。本リサーチの観測（大ジェスチャー・同時発話で破綻）と整合。
- ソース: huggingface.co/meituan-longcat/LongCat-Video-Avatar-1.5

→ **gap は「基本的なマルチストリーム能力」ではなく「重なり・大動作・インタラクティビティの品質」**。audio-driven アバター路線を捨てるのでなく、インタラクティビティ対応モデル＋重なり対応音声へ寄せるのが妥当。

---

## 軸② 音声（掛け合いの自然さ）

### 孤立 TTS → dialogue-aware / full-duplex 同時生成 — 確度: 高（3-0）

| モデル | 重なり | 強み | 日本語 |
|---|---|---|---|
| **CoVoMix2** (arXiv:2506.00885v1) | ◎ 明示制御 | 完全非自己回帰の flow-matching。**話者別ストリーム**が active-speech 区間と無音トークンを符号化し「重なり・無音の精密な時間制御」。**実時間より速い**（RTF 0.30 vs MoonCast 1.37 / Sesame 2.08）。 | 未確認 |
| **MoonCast** (arXiv:2503.14345) | △ 主張なし | 長文・2話者・自発的ポッドキャストを zero-shot 生成。**長文脈 2話者モジュールで cross-turn コヒーレンス**。 | 未確認 |
| **Moshi** (arXiv:2410.00037v2 / Kyutai) | ◎ full-duplex | 2並列音声トークンストリームで**「話者ターンの概念を排除」→ 重なり・割り込みを含む自然会話で学習**。実時間 full-duplex（~200ms）。ただし**人間-AI（system+user）向け**で、台本駆動の任意2話者 TTS ではない。 | 未確認 |
| **CSM** (Sesame, github) | × | 話者ID＋直前 Segment 履歴で文脈付き（孤立解消）。だが README FAQ 明記で**非英語は弱く日本語非対応**、逐次ターンのみで**重なり・意図的 F0 エスカレーション非対応**。**そのままでは漫才に不適**。 | ✕（明示） |

- ソース: arxiv.org/html/2506.00885v1 ・ arxiv.org/pdf/2503.14345 ・ arxiv.org/html/2410.00037v2 ・ github.com/SesameAILabs/csm

---

## 軸③ パイプライン全体設計 — 確度: 中（軸横断の統合）

単一ソースで全体像を規定するものは無いが、一次 evidence は収束する:

- **音声の失敗**（F0 r=−0.26 vs +0.86、12.3 vs 15.8 半音）は孤立 per-line TTS 由来 → dialogue-aware マルチストリーム（CoVoMix2 / MoonCast）が**重なり・無音ストリームの同時モデリング**で是正しうる。
- **映像の失敗**は binding/interactivity の限界 → MultiTalk の L-RoPE、AnyTalker の interactivity refinement、InterDyad の MLLM 反応タイミングがターゲット。

→ **二段構成（重なり対応の同時対話音声 → マルチパーソン・インタラクティビティ対応アバター）** が、現行の完全分離方式より妥当。
ただし「二段 vs 単一 end-to-end（InterDyad 型 speech-to-video）のどちらが反応タイミングで優るか」は直接の evidence なし（後述の open question）。

- ソース: arxiv.org/html/2506.00885v1 ・ github.com/HKUST-C4G/AnyTalker ・ arxiv.org/abs/2603.23132v1 ・ arxiv.org/abs/2505.22647

---

## 推奨アクション（このリポジトリ向け）

### 次の実験（最優先）
1. **重なり対応の日本語対話音声を試作**: CoVoMix2 / MoonCast 系で、台本→話者別ストリーム（active/無音/重なり）を生成。
   - 評価: F0 トレンド r（目標 +0.86 接近）、F0 レンジ（目標 ~15.8 半音）、重なり区間の忠実度。
   - 既存の `compare_scripts.py` / F0 分析ツールをそのまま流用可能。
2. **映像へ流す**: ①AnyTalker（interactivity ベンチ付き）か、②LongCat の真の `run_demo_avatar_multi_audio_to_video.py`（話者別 bbox・add/para）に投入し、現行 para 加算ミックスと比較。
3. **A/B**: 「現行（孤立 TTS＋amix＋para）」 vs 「重なり対応音声＋multi-audio スクリプト」で、かまいたち型ネタの掛け合い自然さを定量比較。

### 中期
- 大動作が要るネタは、audio-to-gesture（EMO2 / SynTalker）で body motion を別途駆動 → レンダ統合する hybrid を検討（単話者・別レンダ段のコストに注意）。
- InterDyad の weights/コードが公開・Blackwell で動くなら、end-to-end dyadic の反応タイミングを評価する価値あり。

---

## 注意点（caveats）

- **時間的鮮度が高い**: AnyTalker(2025-11)・InterDyad(2026-03)・LongCat-Avatar-1.5(~2026-05) は新しいプレプリント中心で、**コード成熟度・再現性・Blackwell sm_120/torch cu128 互換は未検証**。多くは研究リリースで OSS としての堅牢性は不明。
- **性能数値は著者自己申告**（CoVoMix2 RTF 0.30 / Moshi 200ms 等）。
- **日本語はほぼ未検証**: CoVoMix2 / MoonCast の日本語品質は未確認、CSM は日本語不可が確定。**cross-turn F0 エスカレーションを明示制御できるモデルは現状どれも未確認**。
- 多くのジェスチャー系（SynTalker / Seamless）は**動画でなく motion 出力**で別レンダ段が要る。talking-head 系の大半は**単話者**。
- **商用 API（Hedra / Kling / Runway / OmniHuman / Veo / ElevenLabs）は検証済み主張として残らなかった** → 重なり・大動作 two-shot の品質・コスト・統合容易性の OSS 比較は本リサーチでは未評価。

## 未解決の問い（open questions）

1. CoVoMix2 / MoonCast は**日本語**で、上昇する cross-turn F0 エスカレーション（目標 r≈+0.86・~15.8半音）を伴う重なり対話を出せるか。エスカレーションは明示条件付け可能か。
2. **同時2話者 lip-sync かつ大きな body/gesture** を上半身 two-shot で両立できるアバターは、ローカル Blackwell で AnyTalker / LongCat multi-audio / InterDyad のどれか。公開 weights は実際に動くか。
3. 二段構成（同時音声→アバター） vs end-to-end dyadic（InterDyad 型）、漫才の反応タイミングにどちらが自然か。
4. 商用 API は OSS に対し、重なり・大動作 two-shot 品質／コスト／統合容易性でどう比較されるか（本リサーチ未評価）。

---

*出典は本文中に併記。全21ソース・検証ログは deep research 実行ログ（wf_6e0c9bcb-653）参照。*
