"""
社内規定検索チャットボット
Streamlit + Groq API + ChromaDB（ハイブリッド）
"""
import os
import hashlib
import json
import streamlit as st
from dotenv import load_dotenv
from groq import Groq
from document_processor import DocumentProcessor
from vector_store import VectorStore

# 環境変数の読み込み
load_dotenv()

# ページ設定
st.set_page_config(
    page_title="社内規定検索チャットボット",
    page_icon="📚",
    layout="wide"
)


def check_password():
    """パスワード認証を行う"""

    def get_password():
        """パスワードを取得（Streamlit Secrets または 環境変数）"""
        # Streamlit Secretsから取得を試みる
        try:
            return st.secrets["APP_PASSWORD"]
        except (KeyError, FileNotFoundError):
            pass
        # 環境変数から取得
        return os.getenv("APP_PASSWORD", "")

    correct_password = get_password()

    # パスワードが設定されていない場合は認証をスキップ（ローカル開発用）
    if not correct_password:
        return True

    # 既にログイン済みの場合
    if st.session_state.get("authenticated", False):
        return True

    # ログイン画面を表示
    st.title("🔐 社内規定検索チャットボット")
    st.markdown("---")
    st.markdown("このアプリは社内専用です。パスワードを入力してください。")

    password = st.text_input("パスワード", type="password", key="password_input")

    if st.button("ログイン", use_container_width=True):
        if password == correct_password:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("パスワードが正しくありません")

    return False

# CSSで入力欄の位置を調整
st.markdown("""
<style>
    /* チャット入力欄を画面内に表示 */
    [data-testid="stBottom"] {
        bottom: 80px !important;
    }

    /* メインエリアに下部余白を追加 */
    .main .block-container {
        padding-bottom: 150px;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """セッション状態の初期化"""
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    if 'vector_store' not in st.session_state:
        st.session_state.vector_store = None
    if 'initialized' not in st.session_state:
        st.session_state.initialized = False
    if 'guide_step' not in st.session_state:
        st.session_state.guide_step = 'department'  # department, category, subcategory, question
    if 'selected_department' not in st.session_state:
        st.session_state.selected_department = None
    if 'selected_category' not in st.session_state:
        st.session_state.selected_category = None
    if 'selected_subcategory' not in st.session_state:
        st.session_state.selected_subcategory = None


# 部署リスト
DEPARTMENTS = [
    {"name": "診療部", "icon": "🏥"},
    {"name": "看護部門", "icon": "👩‍⚕️"},
    {"name": "放射線科", "icon": "📡"},
    {"name": "リハビリテーション科", "icon": "🏃"},
    {"name": "栄養科", "icon": "🍽️"},
    {"name": "検査科", "icon": "🔬"},
    {"name": "薬局", "icon": "💊"},
    {"name": "地域連携室", "icon": "🤝"},
    {"name": "事務部門", "icon": "📋"},
    {"name": "訪問看護ステーション", "icon": "🚗"},
    {"name": "パートタイマー", "icon": "👥"},
]


# カテゴリとサブカテゴリの定義
QUESTION_GUIDE = {
    "勤務・労働時間": {
        "icon": "⏰",
        "subcategories": {
            "勤務時間": [
                "勤務時間は何時から何時までですか？",
                "休憩時間は何分ですか？",
                "遅番・早番のシフトについて教えてください",
            ],
            "残業": [
                "残業の申請方法を教えてください",
                "残業手当はどのように計算されますか？",
                "残業の上限時間はありますか？",
            ],
            "出退勤": [
                "遅刻した場合の手続きは？",
                "早退する場合はどうすればいいですか？",
                "直行直帰の申請方法は？",
            ],
        }
    },
    "休暇・休業": {
        "icon": "🏖️",
        "subcategories": {
            "有給休暇": [
                "有給休暇は何日もらえますか？",
                "有給休暇の申請方法を教えてください",
                "有給休暇の繰り越しはできますか？",
            ],
            "特別休暇": [
                "慶弔休暇について教えてください",
                "夏季休暇・年末年始休暇について",
                "リフレッシュ休暇はありますか？",
            ],
            "育児・介護休業": [
                "育児休業の取得条件は？",
                "介護休業はどのくらい取れますか？",
                "育児短時間勤務について教えてください",
            ],
        }
    },
    "給与・手当": {
        "icon": "💰",
        "subcategories": {
            "給与": [
                "給与の支払日はいつですか？",
                "給与明細の見方を教えてください",
                "昇給はいつ行われますか？",
            ],
            "手当": [
                "通勤手当について教えてください",
                "住宅手当はありますか？",
                "資格手当の対象資格は？",
            ],
            "賞与・評価": [
                "賞与の支給時期と回数は？",
                "ベースアップ評価料について教えてください",
                "人事評価の基準は？",
            ],
        }
    },
    "出張・経費": {
        "icon": "✈️",
        "subcategories": {
            "出張": [
                "出張の申請方法を教えてください",
                "出張旅費の精算方法は？",
                "日当・宿泊費の規定を教えてください",
            ],
            "経費精算": [
                "経費精算の手順を教えてください",
                "領収書が必要な場合は？",
                "経費精算の締め日はいつですか？",
            ],
        }
    },
    "パートタイマー": {
        "icon": "👥",
        "subcategories": {
            "雇用条件": [
                "パートタイマーの勤務時間について",
                "パートタイマーの契約更新について",
                "正社員登用制度はありますか？",
            ],
            "待遇": [
                "パートタイマーの有給休暇について",
                "パートタイマーの社会保険について",
                "パートタイマーの賞与はありますか？",
            ],
        }
    },
}


def reset_guide():
    """ガイドをリセット"""
    st.session_state.guide_step = 'department'
    st.session_state.selected_department = None
    st.session_state.selected_category = None
    st.session_state.selected_subcategory = None


def render_guide_ui():
    """ガイド付き質問選択UIを表示"""
    step = st.session_state.guide_step

    # 選択中の部署を表示
    if st.session_state.selected_department:
        st.info(f"🏢 選択中の部署: **{st.session_state.selected_department}**")

    if step == 'department':
        st.markdown("### 🏢 あなたの部署を選んでください")
        st.caption("部署によって勤務時間などの規定が異なります")

        cols = st.columns(3)
        for idx, dept in enumerate(DEPARTMENTS):
            with cols[idx % 3]:
                if st.button(f"{dept['icon']} {dept['name']}", key=f"dept_{idx}", use_container_width=True):
                    st.session_state.selected_department = dept['name']
                    st.session_state.guide_step = 'category'
                    st.rerun()

    elif step == 'category':
        st.markdown("### 📋 どのカテゴリについて知りたいですか？")
        st.caption("カテゴリを選択するか、下の入力欄に直接質問を入力できます")

        col1, col2 = st.columns([1, 5])
        with col1:
            if st.button("◀ 部署選択", key="back_to_dept"):
                st.session_state.guide_step = 'department'
                st.session_state.selected_department = None
                st.rerun()

        cols = st.columns(3)
        for idx, (category, data) in enumerate(QUESTION_GUIDE.items()):
            with cols[idx % 3]:
                if st.button(f"{data['icon']} {category}", key=f"cat_{idx}", use_container_width=True):
                    st.session_state.selected_category = category
                    st.session_state.guide_step = 'subcategory'
                    st.rerun()

    elif step == 'subcategory':
        category = st.session_state.selected_category
        data = QUESTION_GUIDE[category]

        st.markdown(f"### {data['icon']} {category}")

        col1, col2 = st.columns([1, 5])
        with col1:
            if st.button("◀ 戻る", key="back_to_cat"):
                st.session_state.guide_step = 'category'
                st.session_state.selected_category = None
                st.rerun()

        st.markdown("**詳しく知りたい項目を選んでください：**")

        cols = st.columns(3)
        for idx, subcategory in enumerate(data['subcategories'].keys()):
            with cols[idx % 3]:
                if st.button(f"📁 {subcategory}", key=f"subcat_{idx}", use_container_width=True):
                    st.session_state.selected_subcategory = subcategory
                    st.session_state.guide_step = 'question'
                    st.rerun()

    elif step == 'question':
        category = st.session_state.selected_category
        subcategory = st.session_state.selected_subcategory
        department = st.session_state.selected_department
        data = QUESTION_GUIDE[category]
        questions = data['subcategories'][subcategory]

        st.markdown(f"### {data['icon']} {category} > {subcategory}")

        col1, col2 = st.columns([1, 5])
        with col1:
            if st.button("◀ 戻る", key="back_to_subcat"):
                st.session_state.guide_step = 'subcategory'
                st.session_state.selected_subcategory = None
                st.rerun()

        st.markdown("**質問を選んでください：**")

        for idx, question in enumerate(questions):
            # 部署情報を質問に付加
            full_question = f"【{department}】{question}" if department else question
            if st.button(f"💬 {question}", key=f"q_{idx}", use_container_width=True):
                return full_question

        st.markdown("---")
        st.caption("💡 上記以外の質問は下の入力欄に直接入力してください")

    return None


def initialize_vector_store():
    """ベクトルストアの初期化"""
    if st.session_state.vector_store is None:
        st.session_state.vector_store = VectorStore()
        # 既存データがあれば自動的に初期化済みとする
        if st.session_state.vector_store.get_collection_count() > 0:
            st.session_state.initialized = True


def load_documents():
    """ドキュメントの読み込みとベクトル化"""
    with st.spinner("ドキュメントを読み込み中..."):
        processor = DocumentProcessor(documents_dir="documents")
        documents = processor.process_all_documents()

        if not documents:
            st.warning("documentsフォルダ内にドキュメントが見つかりませんでした。")
            return False

        st.info(f"{len(documents)} 件のドキュメントを読み込みました")

        # ベクトル化して保存
        with st.spinner("ドキュメントをベクトル化中..."):
            st.session_state.vector_store.add_documents(documents)

        st.success("ドキュメントの読み込みが完了しました！")
        st.session_state.initialized = True
        return True


def expand_query(query: str) -> str:
    """
    クエリを拡張して同義語を含める

    Args:
        query: 元のクエリ

    Returns:
        拡張されたクエリ
    """
    # 同義語マッピング（必要に応じて追加可能）
    synonyms = {
        "休暇": ["休暇", "休業", "年次有給休暇"],
        "休業": ["休暇", "休業"],
        "有給": ["有給", "年次有給休暇", "有休"],
        "勤務時間": ["勤務時間", "始業", "終業", "労働時間", "所定労働時間"],
        "始業": ["始業", "勤務時間", "出勤"],
        "終業": ["終業", "勤務時間", "退勤"],
        "残業": ["残業", "時間外労働", "時間外勤務"],
        "給与": ["給与", "賃金", "給料"],
        "賞与": ["賞与", "ボーナス"],
        "手当": ["手当", "諸手当"],
        "育児": ["育児", "育児休業", "育休"],
        "介護": ["介護", "介護休業"],
        "出張": ["出張", "旅費", "出張旅費"],
        "パート": ["パート", "パートタイマー", "パートタイム"],
        "遅刻": ["遅刻", "遅参"],
        "早退": ["早退"],
        "シフト": ["シフト", "勤務形態", "勤務パターン"],
    }

    expanded_query = query
    for key, values in synonyms.items():
        if key in query:
            # 元のキーワードを含む全ての同義語を追加
            for synonym in values:
                if synonym not in expanded_query:
                    expanded_query += f" {synonym}"

    return expanded_query


def get_cache_key(query: str, context_chunks: list) -> str:
    """キャッシュ用のキーを生成"""
    content_hash = hashlib.md5(
        (query + str([c['content'][:100] for c in context_chunks])).encode()
    ).hexdigest()
    return content_hash


def generate_answer(query: str, context_chunks: list, model_name: str = "llama-3.3-70b-versatile") -> str:
    """
    Groq APIを使用して回答を生成

    Args:
        query: ユーザーの質問
        context_chunks: 関連する文書チャンク
        model_name: 使用するGroqモデル名

    Returns:
        生成された回答
    """
    # キャッシュをチェック
    cache_key = get_cache_key(query, context_chunks)
    if 'response_cache' not in st.session_state:
        st.session_state.response_cache = {}

    if cache_key in st.session_state.response_cache:
        return st.session_state.response_cache[cache_key] + "\n\n_(キャッシュから取得)_"

    # Groq APIの設定（Streamlit Secrets または 環境変数から取得）
    try:
        api_key = st.secrets["GROQ_API_KEY"]
    except (KeyError, FileNotFoundError):
        api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        return "エラー: GROQ_API_KEYが設定されていません。"

    try:
        client = Groq(api_key=api_key)
    except Exception as e:
        return f"エラー: Groq APIの初期化に失敗しました。{str(e)}"

    # コンテキストを結合
    context = "\n\n---\n\n".join([
        f"【{chunk['metadata']['filename']}】\n{chunk['content']}"
        for chunk in context_chunks
    ])

    # プロンプトの作成
    prompt = f"""あなたは社内規定に詳しいアシスタントです。以下の社内規定の情報を基に、質問に正確に答えてください。

【社内規定の情報】
{context}

【質問】
{query}

【回答の注意事項】
- 提供された情報のみを基に回答してください
- 情報にない内容は「提供された規定には記載がありません」と回答してください
- 勤務時間などの表データは以下の形式で簡潔に表示してください：

  **日勤**: 8:30〜17:00（休憩1時間12分）
  **遅番**: 10:30〜19:00（休憩1時間12分）
  **土曜**: 8:30〜12:00（休憩なし）

- 時刻は「08:30:00」ではなく「8:30」のように簡潔に表示
- 箇条書きを使って見やすく整理してください

回答:"""

    try:
        # Groq APIで回答生成
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000
        )
        result = response.choices[0].message.content

        # キャッシュに保存
        st.session_state.response_cache[cache_key] = result

        return result
    except Exception as e:
        return f"エラーが発生しました: {str(e)}"


def main():
    """メイン処理"""

    # パスワード認証
    if not check_password():
        return

    init_session_state()

    # サイドバー
    with st.sidebar:
        st.title("⚙️ 設定")

        # Groqモデル選択
        st.subheader("🤖 LLMモデル")
        model_name = st.selectbox(
            "使用するモデル",
            ["llama-3.3-70b-versatile", "llama3-70b-8192", "mixtral-8x7b-32768"],
            help="Groq API（無料・高速）"
        )
        st.info("🔍 検索: ローカル（無料）\n🤖 回答: Groq API（高精度・無料）")

        # デバッグモード
        debug_mode = st.checkbox("🔍 デバッグモード（検索結果を表示）", value=False)

        # ベクトルストアを初期化
        initialize_vector_store()

        st.divider()

        # ドキュメント管理
        st.subheader("📄 ドキュメント管理")

        if st.session_state.vector_store:
            doc_count = st.session_state.vector_store.get_collection_count()
            st.info(f"登録済みチャンク数: {doc_count}")

        if st.button("ドキュメントを読み込む", use_container_width=True):
            load_documents()

        if st.button("データベースをクリア", use_container_width=True):
            if st.session_state.vector_store:
                st.session_state.vector_store.clear_collection()
                st.session_state.initialized = False
                st.success("データベースをクリアしました")

        if st.button("チャット履歴をクリア", use_container_width=True):
            st.session_state.messages = []
            reset_guide()  # ガイドもリセット
            st.success("チャット履歴をクリアしました")
            st.rerun()

        st.divider()

        # 使い方
        st.subheader("📖 使い方")
        st.markdown("""
        1. `documents` フォルダにPDF/Word/Excelファイルを配置
        2. 「ドキュメントを読み込む」ボタンをクリック
        3. チャット画面で質問を入力

        **✨ 特徴:**
        - 検索はローカル（無料・高速）
        - 回答生成はGemini API（高精度）
        - キャッシュで同じ質問は再利用
        """)

    # メインエリア
    st.title("📚 社内規定検索チャットボット")
    st.caption("🔍 ローカル検索 + 🤖 Groq API（高精度・無料）")

    if not st.session_state.initialized:
        st.info("左のサイドバーから「ドキュメントを読み込む」ボタンをクリックして、ドキュメントを登録してください")
        return

    # チャット履歴の表示
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            # 参照資料の表示
            if message["role"] == "assistant" and "sources" in message:
                # 重複を除いてファイル名のみ表示
                unique_files = list(set([source['filename'] for source in message["sources"]]))
                if unique_files:
                    st.caption("📚 参考資料: " + " / ".join(unique_files))

    # ガイド付き質問選択UIを表示
    guided_question = None

    # ガイドを直接表示
    st.markdown("---")
    guided_question = render_guide_ui()
    st.markdown("---")

    # ガイドから選択された質問を処理
    if guided_question:
        prompt = guided_question
        reset_guide()  # ガイドをリセット
    else:
        # ユーザー入力
        prompt = st.chat_input("質問を入力してください（例：有給休暇の申請方法は？）")

    if prompt:
        # ユーザーメッセージを表示
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # アシスタントの回答を生成
        with st.chat_message("assistant"):
            with st.spinner("検索中..."):
                # クエリを拡張（同義語を含める）
                expanded_prompt = expand_query(prompt)

                # ハイブリッド検索（ベクトル + キーワード）
                search_results = st.session_state.vector_store.search(expanded_prompt, n_results=15)

                # デバッグモード：検索結果を表示
                if debug_mode and search_results:
                    with st.expander("🔍 検索結果の詳細", expanded=True):
                        st.write(f"**拡張クエリ:** {expanded_prompt}")
                        st.write(f"**検索結果数:** {len(search_results)}")
                        for i, result in enumerate(search_results, 1):
                            st.markdown(f"**{i}. {result['metadata']['filename']}** (距離: {result['distance']:.3f})")
                            st.text(result['content'][:300] + "...")
                            st.divider()

                if not search_results:
                    response = "申し訳ございません。関連する情報が見つかりませんでした。"
                    st.markdown(response)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": response
                    })
                else:
                    # 回答を生成
                    with st.spinner("回答を生成中..."):
                        response = generate_answer(prompt, search_results, model_name)
                        st.markdown(response)

                    # 参照資料を表示（ファイル名のみ、重複除外）
                    unique_files = list(set([r['metadata']['filename'] for r in search_results]))
                    if unique_files:
                        st.caption("📚 参考資料: " + " / ".join(unique_files))

                    # メッセージを保存
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": response,
                        "sources": [
                            {
                                "filename": r['metadata']['filename'],
                                "chunk_index": r['metadata']['chunk_index'],
                                "total_chunks": r['metadata']['total_chunks'],
                                "content": r['content']
                            }
                            for r in search_results
                        ]
                    })


if __name__ == "__main__":
    main()
