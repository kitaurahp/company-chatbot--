# 社内規定検索チャットボット - 詳細セットアップガイド

このドキュメントは、他のPCでも同じ環境を構築できるように、詳細な手順を記載しています。

## 📋 目次

1. [システム概要](#システム概要)
2. [必要な環境](#必要な環境)
3. [セットアップ手順](#セットアップ手順)
4. [カスタマイズ方法](#カスタマイズ方法)
5. [トラブルシューティング](#トラブルシューティング)

---

## システム概要

### アーキテクチャ

```
[PDF/Word/Excel]
    ↓
[document_processor.py] テキスト抽出
    ↓
[Sentence Transformers] ローカル埋め込み（API不要）
    ↓
[ChromaDB] ベクトルデータベース（ローカル保存）
    ↓
[Streamlit UI] ユーザーからの質問
    ↓
[ベクトル検索] + [同義語拡張]
    ↓
[Ollama (qwen2.5:7b)] ローカルLLM
    ↓
[回答表示]
```

### 主な特徴

- ✅ **完全ローカル実行**: インターネット不要、API制限なし
- ✅ **無料**: すべてのコンポーネントが無料
- ✅ **プライバシー保護**: 社内規定が外部に送信されない
- ✅ **同義語検索**: 「休暇」「休業」などを自動的に同一視

---

## 必要な環境

### ハードウェア要件

- **メモリ**: 最低8GB（推奨16GB以上）
- **ストレージ**: 10GB以上の空き容量
- **CPU**: Intel Core i5以上（またはApple Silicon）

### ソフトウェア要件

- **OS**: macOS、Linux、Windows（macOSで動作確認済み）
- **Python**: 3.9以上（3.11推奨）
- **Ollama**: 最新版

---

## セットアップ手順

### ステップ1: リポジトリのクローン

```bash
# このディレクトリをコピー
cp -r /Users/h.yusuke/company-chatbot /path/to/new/location

# または、GitHubリポジトリからクローン（リポジトリがある場合）
git clone <repository-url>
cd company-chatbot
```

### ステップ2: Python環境のセットアップ

```bash
# 仮想環境の作成（推奨）
python3 -m venv venv

# 仮想環境の有効化
source venv/bin/activate  # macOS/Linux
# または
venv\Scripts\activate  # Windows

# 依存パッケージのインストール
pip install -r requirements.txt
```

### ステップ3: Ollamaのインストール

#### macOS

```bash
# 方法1: 公式サイトからダウンロード（推奨）
# https://ollama.com/download からダウンロードしてインストール

# 方法2: Homebrewでインストール
brew install ollama
```

#### Linux

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

#### Windows

公式サイトからインストーラーをダウンロード：
https://ollama.com/download

### ステップ4: LLMモデルのダウンロード

```bash
# 推奨モデル（約4GB、高性能）
ollama pull qwen2.5:7b

# または軽量モデル（約2GB）
ollama pull qwen2.5:3b
```

**確認:**
```bash
ollama list
# qwen2.5:7b が表示されればOK
```

### ステップ5: 初回起動

```bash
# Streamlitアプリを起動
streamlit run app.py
```

ブラウザが自動的に開き、`http://localhost:8501` でアプリが表示されます。

### ステップ6: ドキュメントの配置

```bash
# 社内規定ファイルを配置
# documents フォルダに PDF/Word/Excel ファイルをコピー

# 対応形式:
# - PDF (.pdf)
# - Word (.docx) ※.doc形式は要変換
# - Excel (.xlsx, .xls)
```

**重要: .doc形式について**

古いWord形式（.doc）は非対応です。以下のいずれかを実施：
- Wordで開いて.docx形式で保存し直す
- LibreOfficeで変換する

### ステップ7: ドキュメントの読み込み

1. サイドバーの「ドキュメントを読み込む」ボタンをクリック
2. ベクトル化が完了するまで待つ（数分）
3. 「登録済みチャンク数」が表示されれば成功

---

## カスタマイズ方法

### 1. 同義語の追加

`app.py` の70-76行目を編集：

```python
synonyms = {
    "休暇": ["休暇", "休業"],
    "休業": ["休暇", "休業"],
    # ↓ 追加例
    "給与": ["給与", "給料", "賃金"],
    "賞与": ["賞与", "ボーナス"],
}
```

### 2. チャンクサイズの調整

`vector_store.py` の54行目を編集：

```python
def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200):
    # chunk_size: 1つのチャンクの文字数（デフォルト1000）
    # overlap: チャンク間の重複文字数（デフォルト200）
```

**小さくする場合（より細かく分割）:**
```python
chunk_size: int = 500, overlap: int = 100
```

**大きくする場合（より大きな単位で分割）:**
```python
chunk_size: int = 2000, overlap: int = 400
```

### 3. 検索結果数の調整

`app.py` の232行目を編集：

```python
search_results = st.session_state.vector_store.search(expanded_prompt, n_results=10)
# n_results: 検索結果の数（デフォルト10）
# より多くの情報を取得したい場合は15-20に増やす
```

### 4. LLMモデルの変更

別のモデルを使いたい場合：

```bash
# モデル一覧を確認
ollama list

# 新しいモデルをダウンロード
ollama pull <model-name>
```

`app.py` の147-150行目を編集：

```python
model_name = st.selectbox(
    "使用するモデル",
    ["qwen2.5:7b", "qwen2.5:3b", "新しいモデル名"],  # ← ここに追加
    ...
)
```

### 5. プロンプトのカスタマイズ

`app.py` の107-121行目を編集：

```python
prompt = f"""あなたは社内規定に詳しいアシスタントです。以下の社内規定の情報を基に、質問に正確に答えてください。

【社内規定の情報】
{context}

【質問】
{query}

【回答の注意事項】
- 提供された情報のみを基に回答してください
- 情報にない内容は「提供された規定には記載がありません」と回答してください
- 該当する規定名や文書名を明示してください
- 具体的で分かりやすく説明してください

回答:"""
```

この部分を会社の方針に合わせて調整できます。

---

## トラブルシューティング

### Q1: ドキュメントが読み込めない

**症状:** 「0件のドキュメントを読み込みました」と表示される

**原因と対処法:**

1. **ファイル形式の確認**
   ```bash
   ls -la documents/
   ```
   対応形式：.pdf, .docx, .xlsx

2. **.doc形式の場合**
   Wordで開いて.docx形式で保存し直す

3. **ファイルが空の場合**
   ファイルにテキストが含まれているか確認

### Q2: 文字化けする

**原因:** 古い.doc形式（Word 97-2003）

**対処法:**
```bash
# .docファイルを別フォルダに移動
mkdir -p documents/old_doc_format
mv documents/*.doc documents/old_doc_format/

# Wordで開いて.docx形式で保存し直す
```

### Q3: 検索結果が適切でない

**対処法:**

1. **デバッグモードを有効化**
   - サイドバーの「🔍 デバッグモード」にチェック
   - 検索結果の詳細を確認

2. **同義語を追加**
   - `app.py` の70-76行目に同義語を追加

3. **検索結果数を増やす**
   - `app.py` の232行目の`n_results`を15-20に増やす

### Q4: Ollamaモデルが見つからない

**症状:** "ResponseError: モデル 'qwen2.5:7b' が見つかりません"

**対処法:**
```bash
# インストール済みモデルを確認
ollama list

# モデルが無い場合はダウンロード
ollama pull qwen2.5:7b
```

### Q5: メモリ不足エラー

**症状:** Ollamaが起動しない、応答が遅い

**対処法:**
1. より軽量なモデルに変更
   ```bash
   ollama pull qwen2.5:3b
   ```

2. アプリのモデル選択で`qwen2.5:3b`を選択

### Q6: データベースがおかしい

**対処法:**
```bash
# データベースを完全削除
rm -rf data/

# アプリを再起動してドキュメントを再読み込み
```

---

## ファイル構成

```
company-chatbot/
├── app.py                      # Streamlitメインアプリ
├── document_processor.py       # PDF/Word/Excel処理
├── vector_store.py            # ベクトル検索（Sentence Transformers + ChromaDB）
├── requirements.txt           # 依存パッケージ
├── .env.example              # 環境変数サンプル（現在未使用）
├── .gitignore                # Git除外設定
├── README.md                 # 基本説明
├── SETUP_GUIDE.md           # このファイル（詳細セットアップガイド）
├── documents/               # 社内規定ファイルを配置
│   └── README.md
└── data/                    # データベース（自動生成）
    └── chroma_db/
```

---

## 次のステップ

### 本番運用に向けて

1. **Streamlit Cloudへのデプロイ**（推奨しない）
   - 理由: ローカルモデル（Ollama）が使えない
   - 代替: 社内サーバーでホスティング

2. **社内サーバーでのホスティング**
   ```bash
   # ポート指定で起動
   streamlit run app.py --server.port 8501 --server.address 0.0.0.0
   ```

3. **定期的なドキュメント更新フロー**
   - 規定が更新されたら、documentsフォルダを更新
   - 「データベースをクリア」→「ドキュメントを読み込む」

### パフォーマンス最適化

1. **より高性能なモデルを試す**
   ```bash
   ollama pull qwen2.5:14b
   ollama pull qwen2.5:32b
   ```

2. **GPU対応**
   - GPUがある場合、Ollamaが自動的に使用
   - より高速な推論が可能

---

## サポート情報

### 開発履歴

このツールはClaude Codeを使用して構築されました。

**主な実装内容:**
- ローカル埋め込みモデル（Sentence Transformers）の採用
- Ollama統合による完全ローカル実行
- 同義語検索機能
- デバッグモード
- チャット履歴管理

### 技術スタック

- **フロントエンド**: Streamlit
- **埋め込み**: Sentence Transformers (paraphrase-multilingual-MiniLM-L12-v2)
- **ベクトルDB**: ChromaDB
- **LLM**: Ollama (qwen2.5:7b)
- **ドキュメント処理**: python-docx, PyPDF2, openpyxl

---

## ライセンス

各コンポーネントのライセンスを確認してください：
- Streamlit: Apache 2.0
- Sentence Transformers: Apache 2.0
- ChromaDB: Apache 2.0
- Ollama: MIT License
- Qwen2.5: Apache 2.0

---

## 更新履歴

- 2026-01-07: 初版作成
  - 基本機能実装
  - ローカル埋め込み対応
  - Ollama統合
  - 同義語検索
  - デバッグモード
