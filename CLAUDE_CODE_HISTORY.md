# Claude Code 会話履歴の活用方法

## 最新の進捗状況（2026-01-08）

### 現在の構成
- **検索**: ローカル（Sentence Transformers + ChromaDB）- 無料
- **回答生成**: Groq API（Llama 3.3 70B）- 無料・高精度

### 完了した改善
1. Word埋め込みExcelの抽出対応（勤務時間表など）
2. 部門ごとに分割して抽出（検索精度向上）
3. ハイブリッド検索（ベクトル + キーワード）
4. Groq APIへの切り替え（無料・高精度）
5. キャッシュ機能（同じ質問は再利用）
6. 回答フォーマットの改善（見やすい表示）

### APIキー設定済み
- GROQ_API_KEY: .envファイルに保存済み

### 再開時にClaude Codeに伝えること
```
company-chatbotフォルダで作業を続けます。
前回はGroq APIを使った社内規定チャットボットを構築中でした。
現在の状態を確認してください。
```

---

このドキュメントでは、Claude Codeの会話履歴を他のPCで参照・活用する方法を説明します。

---

## Claude Codeの会話履歴について

Claude Codeは、すべての会話をローカルに保存しています。この履歴を使って：
- 過去の作業内容を確認
- 同じ問題が発生した時に参照
- 他のメンバーと知識を共有

---

## 方法1: 会話履歴の再開（同じPC内）

### 最新の会話を再開

```bash
# このプロジェクトディレクトリで
cd /Users/h.yusuke/company-chatbot
claude --continue
```

### 会話履歴から選択して再開

```bash
claude --resume
```

対話的なピッカーが表示され、過去の会話を選択できます。

---

## 方法2: 会話履歴を他のPCで参照

### ステップ1: 会話履歴の場所を確認

Claude Codeの会話履歴は以下の場所に保存されています：

```bash
# macOS/Linux
~/.claude/sessions/

# Windows
%USERPROFILE%\.claude\sessions\
```

### ステップ2: このプロジェクトの会話を特定

```bash
# 会話一覧を表示
claude --resume

# このプロジェクト（company-chatbot）に関連する会話を探す
# 「社内規定」「チャットボット」などのキーワードで識別
```

### ステップ3: 会話履歴をエクスポート

現在のClaude Codeには直接エクスポート機能はありませんが、以下の方法で内容を保存できます：

#### 方法A: 会話を再開してコピー

```bash
# 会話を再開
claude --resume

# ターミナルの出力をファイルに保存
# （会話再開後、/logコマンドが使えるか確認）
```

#### 方法B: セッションファイルをコピー

```bash
# セッションディレクトリ内の該当ファイルをコピー
# （具体的なファイル構造はClaude Codeのバージョンによる）
```

---

## 方法3: このドキュメントとコードで再現

最も確実な方法は、以下のドキュメントを使って他のPCで同じ環境を再現することです：

### 必要なドキュメント

1. **SETUP_GUIDE.md** - 詳細なセットアップ手順
2. **このファイル (CLAUDE_CODE_HISTORY.md)** - 構築の背景
3. **README.md** - 基本的な使い方
4. **コード一式** - app.py, vector_store.py, document_processor.py など

### 実装の主要なポイント

#### 1. 完全ローカル化の実現

**課題:** Gemini APIのレート制限

**解決策:**
- ドキュメント埋め込み: Sentence Transformers（ローカル）
- 質問応答: Ollama（ローカルLLM）

**実装:**
```python
# vector_store.py
from sentence_transformers import SentenceTransformer
self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

# app.py
import ollama
response = ollama.chat(model=model_name, messages=[...])
```

#### 2. 同義語検索機能

**課題:** 「休暇」と「休業」が別の用語として扱われる

**解決策:** クエリ拡張機能

**実装:**
```python
# app.py
def expand_query(query: str) -> str:
    synonyms = {
        "休暇": ["休暇", "休業"],
        "休業": ["休暇", "休業"],
    }
    # クエリに同義語を追加
```

#### 3. .doc形式の問題

**課題:** python-docxが古い.doc形式に非対応

**解決策:**
- .docxに変換を推奨
- または.docファイルを除外

```bash
mkdir -p documents/old_doc_format
mv documents/*.doc documents/old_doc_format/
```

#### 4. デバッグ機能

**課題:** 検索結果が適切か確認できない

**解決策:** デバッグモード追加

**実装:**
```python
# app.py
debug_mode = st.checkbox("🔍 デバッグモード（検索結果を表示）")

if debug_mode and search_results:
    # 検索結果の詳細を表示
```

#### 5. ユーザビリティ改善

**実装内容:**
- チャット履歴クリア機能
- 参照資料の簡素化（ファイル名のみ表示）
- デバッグモードによる透明性向上

---

## 主要な技術的決定

### なぜSentence Transformersを選んだか

- ✅ 完全ローカルで動作
- ✅ API制限なし
- ✅ 多言語対応（日本語も高精度）
- ✅ 約100MBと軽量

### なぜOllamaを選んだか

- ✅ セットアップが簡単
- ✅ 様々なモデルに対応
- ✅ GPU自動対応
- ✅ 無料・無制限

### なぜqwen2.5:7bを選んだか

- ✅ 日本語性能が高い
- ✅ 7Bパラメータで精度と速度のバランスが良い
- ✅ RAGタスクに適している

---

## トラブルシューティングの履歴

### 問題1: Gemini APIのレート制限

**発生:** ドキュメント読み込み時に429エラー

**原因:**
- Gemini Embedding APIを使用していた
- 無料枠が厳しい（15 RPM）

**解決:**
```python
# 変更前
genai.embed_content(model="models/embedding-001", ...)

# 変更後
self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
self.model.encode(texts)
```

### 問題2: モデル名エラー

**発生:** "NotFound: 404 models/gemini-pro"

**原因:**
- 古いモデル名を使用
- APIバージョンが古い

**解決:**
```python
# 変更前
model = genai.GenerativeModel('gemini-pro')

# 変更後（最終的にOllamaに移行）
ollama.chat(model='qwen2.5:7b', ...)
```

### 問題3: .doc形式の文字化け

**発生:** 古いWord形式で文字化け

**原因:** python-docxは.docx形式のみ対応

**解決:**
- .docファイルを別フォルダに移動
- .docx形式への変換を推奨

### 問題4: APIキーの保存問題

**発生:** .envファイルにAPIキーが途中で切れる

**原因:** nanoエディタでの入力問題

**解決:**
- Streamlit UIで直接入力
- 最終的にAPI不要に（Ollama採用）

### 問題5: 検索精度の問題

**発生:** 「休暇」で検索しても「休業」が見つからない

**解決:** 同義語検索機能を追加

---

## パフォーマンス調整の履歴

### チャンク設定

```python
# vector_store.py
chunk_size: int = 1000  # 1チャンクの文字数
overlap: int = 200      # 重複部分
```

### 検索結果数

```python
# app.py
n_results=10  # 5から10に増やした
```

---

## 他のPCでの再現手順（まとめ）

### 1. 環境構築

```bash
# リポジトリをコピー
cp -r /Users/h.yusuke/company-chatbot /new/location

# Python環境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Ollama
brew install ollama  # または公式サイトから
ollama pull qwen2.5:7b
```

### 2. ドキュメント配置

```bash
# .docx形式のファイルをdocumentsフォルダに配置
# .doc形式は事前に変換
```

### 3. 起動

```bash
streamlit run app.py
```

### 4. 初期設定

1. サイドバーで「ドキュメントを読み込む」
2. デバッグモードで動作確認
3. 同義語を必要に応じて追加（app.py 70-76行目）

---

## カスタマイズポイント

他のメンバーが調整する可能性が高い箇所：

### 1. 同義語の追加
**ファイル:** app.py
**行:** 70-76

### 2. チャンクサイズ
**ファイル:** vector_store.py
**行:** 54

### 3. 検索結果数
**ファイル:** app.py
**行:** 232

### 4. プロンプト
**ファイル:** app.py
**行:** 107-121

---

## 参考リソース

- [Ollama公式](https://ollama.com/)
- [Sentence Transformers](https://www.sbert.net/)
- [ChromaDB](https://www.trychroma.com/)
- [Streamlit](https://streamlit.io/)
- [Qwen2.5モデル](https://huggingface.co/Qwen)

---

## 質問がある場合

SETUP_GUIDE.mdのトラブルシューティングセクションを参照してください。

それでも解決しない場合は、Claude Codeで以下のように質問できます：

```bash
cd company-chatbot
claude

# 例:
# 「同義語を追加したいのですが、どのファイルを編集すればいいですか？」
# 「検索精度を上げるにはどうすればいいですか？」
```
