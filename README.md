# 社内規定検索チャットボット

就業規則、旅費規定などの社内規定を検索できるRAG（Retrieval-Augmented Generation）ベースのチャットボットです。

## ✨ 特徴

- 🔒 **完全ローカル実行**: API不要、インターネット接続不要
- 💰 **完全無料**: すべてのコンポーネントが無料、無制限
- 🔐 **プライバシー保護**: 社内規定が外部に送信されない
- 📄 **複数形式対応**: PDF、Word、Excelファイルに対応
- 🔍 **高精度検索**: Sentence Transformersによるベクトル検索
- 💬 **自然な対話**: Ollamaによる日本語対応LLM
- 🔄 **同義語検索**: 「休暇」「休業」などを自動的に同一視
- 🐛 **デバッグモード**: 検索結果の詳細を確認可能

## システム構成

```
[PDF/Word/Excel ファイル]
    ↓
[document_processor.py] テキスト抽出
    ↓
[Sentence Transformers] ローカル埋め込み
    ↓
[ChromaDB] ベクトルデータベース
    ↓
[Streamlit UI] ユーザーからの質問
    ↓
[同義語拡張 + ベクトル検索]
    ↓
[Ollama (qwen2.5:7b)] ローカルLLM
    ↓
[回答表示 + 参考資料]
```

## 必要な環境

### ハードウェア
- **メモリ**: 最低8GB（推奨16GB以上）
- **ストレージ**: 10GB以上の空き容量
- **CPU**: Intel Core i5以上（またはApple Silicon）

### ソフトウェア
- **Python 3.9以上**（3.11推奨）
- **Ollama**（最新版）

## クイックスタート

### 1. 依存パッケージのインストール

```bash
cd company-chatbot
pip install -r requirements.txt
```

### 2. Ollamaのインストール

#### macOS
```bash
# 公式サイトからダウンロード（推奨）
# https://ollama.com/download

# または Homebrew
brew install ollama
```

#### Linux
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 3. LLMモデルのダウンロード

```bash
# 推奨モデル（高性能、約4GB）
ollama pull qwen2.5:7b

# または軽量モデル（約2GB）
ollama pull qwen2.5:3b
```

### 4. アプリケーションの起動

```bash
streamlit run app.py
```

ブラウザが自動的に開き、`http://localhost:8501` でアプリが表示されます。

### 5. ドキュメントの配置と読み込み

1. `documents` フォルダに社内規定ファイル（PDF/Word/Excel）を配置
2. サイドバーの「ドキュメントを読み込む」ボタンをクリック
3. ベクトル化が完了するまで待つ
4. 質問を入力して使用開始！

## 対応ファイル形式

- ✅ **PDF** (.pdf)
- ✅ **Word** (.docx) ※.doc形式は要変換
- ✅ **Excel** (.xlsx, .xls)

**注意:** 古いWord形式（.doc）は非対応です。Wordで開いて.docx形式で保存し直してください。

## 使い方

### 基本的な質問

```
「有給休暇の日数は？」
「出張旅費の上限を教えて」
「育児休業の期間は？」
```

### デバッグモード

検索結果の詳細を確認したい場合：
1. サイドバーの「🔍 デバッグモード」にチェック
2. 質問を入力
3. 検索結果の詳細が展開表示されます

### チャット履歴のクリア

サイドバーの「チャット履歴をクリア」ボタンをクリック

## カスタマイズ

### 同義語の追加

`app.py` の70-76行目を編集：

```python
synonyms = {
    "休暇": ["休暇", "休業"],
    "休業": ["休暇", "休業"],
    "給与": ["給与", "給料", "賃金"],  # ← 追加
}
```

### 検索結果数の調整

`app.py` の232行目を編集：

```python
search_results = st.session_state.vector_store.search(expanded_prompt, n_results=10)
# n_results を 15-20 に増やすとより多くの情報を取得
```

### チャンクサイズの調整

`vector_store.py` の54行目を編集：

```python
def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200):
    # chunk_size: 小さくすると細かく分割、大きくすると大きな単位で分割
    # overlap: チャンク間の重複文字数
```

## ファイル構成

```
company-chatbot/
├── app.py                      # Streamlitメインアプリ
├── document_processor.py       # PDF/Word/Excel処理
├── vector_store.py            # ベクトル検索
├── requirements.txt           # 依存パッケージ
├── README.md                 # このファイル
├── SETUP_GUIDE.md           # 詳細セットアップガイド
├── CLAUDE_CODE_HISTORY.md   # 開発履歴と技術的決定
├── documents/               # 社内規定ファイルを配置
└── data/                    # データベース（自動生成）
```

## トラブルシューティング

### ドキュメントが読み込めない

```bash
# ファイル形式を確認
ls -la documents/

# .doc形式の場合は別フォルダに移動
mkdir -p documents/old_doc_format
mv documents/*.doc documents/old_doc_format/
```

### モデルが見つからない

```bash
# インストール済みモデルを確認
ollama list

# モデルをダウンロード
ollama pull qwen2.5:7b
```

### データベースをリセット

```bash
# データベースを削除
rm -rf data/

# アプリを再起動してドキュメントを再読み込み
```

### メモリ不足

より軽量なモデルを使用：
```bash
ollama pull qwen2.5:3b
```

アプリのサイドバーで`qwen2.5:3b`を選択

## 詳細ドキュメント

- **[SETUP_GUIDE.md](SETUP_GUIDE.md)** - 詳細なセットアップ手順とカスタマイズ方法
- **[CLAUDE_CODE_HISTORY.md](CLAUDE_CODE_HISTORY.md)** - 開発履歴、技術的決定、トラブルシューティング

## 技術スタック

- **UI**: Streamlit
- **埋め込み**: Sentence Transformers (paraphrase-multilingual-MiniLM-L12-v2)
- **ベクトルDB**: ChromaDB
- **LLM**: Ollama (qwen2.5:7b)
- **ドキュメント処理**: python-docx, PyPDF2, openpyxl

## なぜ完全ローカルなのか？

1. **プライバシー**: 社内規定という機密情報を外部に送信しない
2. **コスト**: APIコストがかからない
3. **制限なし**: レート制限を気にせず無制限に使用可能
4. **オフライン**: インターネット接続不要で使用可能

## ライセンス

各コンポーネントのライセンスを確認してください：
- Streamlit: Apache 2.0
- Sentence Transformers: Apache 2.0
- ChromaDB: Apache 2.0
- Ollama: MIT License
- Qwen2.5: Apache 2.0

---

**開発日**: 2026-01-07
**開発ツール**: Claude Code
