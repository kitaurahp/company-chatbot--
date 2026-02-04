"""
社内規定検索チャットボット
Streamlit + Gemini + ChromaDB
"""
import os
import hashlib
import json
import time
import streamlit as st
from dotenv import load_dotenv
import google.generativeai as genai
from groq import Groq
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.api_core.exceptions import ResourceExhausted
from document_processor import DocumentProcessor
from vector_store import VectorStore

# 環境変数の読み込み
load_dotenv()

# デフォルトのAPIキー（後で変更可能）
DEFAULT_GEMINI_API_KEY = "AIzaSyAHVrTdzDcs7tzR8iP4qnUyQLz2dIhC0JA"
DEFAULT_GROQ_API_KEY = ""  # Groq APIキーはユーザーが設定する必要があります


def get_gemini_api_key():
    """Gemini APIキーを取得（優先順位: session_state > secrets > デフォルト）"""
    # 1. session_stateに保存されたキー（管理画面で設定）
    if 'gemini_api_key' in st.session_state and st.session_state.gemini_api_key:
        return st.session_state.gemini_api_key
    # 2. Streamlit Secretsから取得
    try:
        return st.secrets["GEMINI_API_KEY"]
    except (KeyError, FileNotFoundError):
        pass
    # 3. デフォルトキー
    return DEFAULT_GEMINI_API_KEY


def get_groq_api_key():
    """Groq APIキーを取得（優先順位: session_state > secrets > デフォルト）"""
    # 1. session_stateに保存されたキー（管理画面で設定）
    if 'groq_api_key' in st.session_state and st.session_state.groq_api_key:
        return st.session_state.groq_api_key
    # 2. Streamlit Secretsから取得
    try:
        return st.secrets["GROQ_API_KEY"]
    except (KeyError, FileNotFoundError):
        pass
    # 3. デフォルトキー
    return DEFAULT_GROQ_API_KEY

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
    /* メインエリアに下部余白を追加 */
    .main .block-container {
        padding-bottom: 100px;
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
    if 'selected_department' not in st.session_state:
        st.session_state.selected_department = None
    if 'pending_question' not in st.session_state:
        st.session_state.pending_question = None
    if 'admin_authenticated' not in st.session_state:
        st.session_state.admin_authenticated = False
    if 'show_admin' not in st.session_state:
        st.session_state.show_admin = False


def render_admin_page():
    """管理画面を表示"""
    st.title("🔧 管理画面")

    # 管理者パスワード認証
    if not st.session_state.admin_authenticated:
        st.markdown("### 管理者ログイン")
        admin_password = st.text_input("管理者パスワード", type="password", key="admin_pwd")
        if st.button("ログイン", key="admin_login"):
            if admin_password == "admin":
                st.session_state.admin_authenticated = True
                st.rerun()
            else:
                st.error("パスワードが正しくありません")

        if st.button("← 戻る", key="admin_back1"):
            st.session_state.show_admin = False
            st.rerun()
        return

    # 管理者認証済み
    st.success("管理者としてログイン中")

    # === Groq APIキー設定（推奨） ===
    st.markdown("---")
    st.markdown("### 🚀 Groq APIキー設定（推奨）")
    st.markdown("Groqは高速で安定したLLMサービスです。無料で利用できます。")

    # 現在のGroq APIキーの状態を表示
    groq_key = get_groq_api_key()
    if groq_key:
        st.success("✅ Groq APIキーが設定されています")
    else:
        st.warning("⚠️ Groq APIキーが未設定です。設定することを推奨します。")

    # 新しいGroq APIキーの入力
    new_groq_key = st.text_input(
        "Groq APIキー",
        type="password",
        placeholder="gsk_...",
        key="new_groq_key_input"
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Groqキーを更新", use_container_width=True, key="update_groq"):
            if new_groq_key:
                st.session_state.groq_api_key = new_groq_key
                st.success("Groq APIキーを更新しました")
                st.rerun()
            else:
                st.error("APIキーを入力してください")

    with col2:
        if st.button("Groqキーを削除", use_container_width=True, key="delete_groq"):
            if 'groq_api_key' in st.session_state:
                del st.session_state.groq_api_key
            st.success("Groq APIキーを削除しました")
            st.rerun()

    st.markdown("""
    **Groq APIキーの取得方法:**
    1. [console.groq.com](https://console.groq.com/keys) にアクセス
    2. アカウントを作成（無料）
    3. 「Create API Key」をクリック
    4. 生成されたキーをコピーして上に貼り付け
    """)

    # === Gemini APIキー設定（フォールバック） ===
    st.markdown("---")
    st.markdown("### Gemini APIキー設定（フォールバック用）")
    st.markdown("Groqが利用できない場合に使用されます。")

    # 現在のAPIキーの状態を表示
    current_key = get_gemini_api_key()
    if 'gemini_api_key' in st.session_state and st.session_state.gemini_api_key:
        st.info("現在: カスタムAPIキーを使用中")
    else:
        try:
            _ = st.secrets["GEMINI_API_KEY"]
            st.info("現在: Secrets設定のAPIキーを使用中")
        except (KeyError, FileNotFoundError):
            st.warning("現在: デフォルトAPIキーを使用中（不安定な場合があります）")

    # 新しいAPIキーの入力
    new_api_key = st.text_input(
        "Gemini APIキー",
        type="password",
        placeholder="AIzaSy...",
        key="new_api_key_input"
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Geminiキーを更新", use_container_width=True, key="update_gemini"):
            if new_api_key:
                st.session_state.gemini_api_key = new_api_key
                st.success("Gemini APIキーを更新しました")
                st.rerun()
            else:
                st.error("APIキーを入力してください")

    with col2:
        if st.button("デフォルトに戻す", use_container_width=True, key="reset_gemini"):
            if 'gemini_api_key' in st.session_state:
                del st.session_state.gemini_api_key
            st.success("デフォルトAPIキーに戻しました")
            st.rerun()

    st.markdown("---")
    st.markdown("### 注意事項")
    st.markdown("""
    - APIキーの変更はアプリ再起動まで有効です
    - 永続的に変更するには、Streamlit Cloudの「Secrets」設定で設定してください:
      - `GROQ_API_KEY` : Groq用
      - `GEMINI_API_KEY` : Gemini用
    """)

    st.markdown("---")
    if st.button("← チャットに戻る", use_container_width=True):
        st.session_state.show_admin = False
        st.rerun()


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
    {"name": "事務部門", "icon": "🗂️"},
    {"name": "訪問看護ステーション", "icon": "🚗"},
    {"name": "パートタイマー", "icon": "👥"},
]

# よくある質問（シンプルな1段階形式）
QUICK_QUESTIONS = [
    {"label": "⏰ 勤務時間", "question": "勤務時間を教えてください"},
    {"label": "🌴 有給・特別休暇", "question": "有給休暇と特別休暇の付与日数を教えてください"},
    {"label": "💰 時間外手当", "question": "時間外手当について教えてください"},
    {"label": "🏠 介護休業", "question": "介護休業について教えてください"},
    {"label": "👶 育児休業", "question": "育児休業について教えてください"},
    {"label": "🕯️ 忌引休暇", "question": "忌引き休暇について教えてください"},
]


def render_department_selector():
    """部署選択UIを表示"""
    st.markdown("### 🏢 あなたの部署を選んでください")
    st.caption("部署によって勤務時間などの規定が異なります")

    # 3列のグリッドで部署ボタンを表示
    cols = st.columns(3)
    for i, dept in enumerate(DEPARTMENTS):
        col_idx = i % 3
        with cols[col_idx]:
            if st.button(f"{dept['icon']} {dept['name']}", key=f"dept_{i}", use_container_width=True):
                st.session_state.selected_department = dept['name']
                st.rerun()

    st.divider()


def initialize_vector_store():
    """ベクトルストアの初期化"""
    if st.session_state.vector_store is None:
        st.session_state.vector_store = VectorStore()
        # 既存データがあれば自動的に初期化済みとする
        if st.session_state.vector_store.get_collection_count() > 0:
            st.session_state.initialized = True


def auto_load_documents():
    """ドキュメントの自動読み込み（初回起動時）"""
    # 既に読み込み済み、または自動読み込み実行済みならスキップ
    if st.session_state.initialized or st.session_state.get('auto_load_attempted', False):
        return

    st.session_state.auto_load_attempted = True

    # documentsフォルダにファイルがあるか確認
    from pathlib import Path
    docs_dir = Path("documents")
    if not docs_dir.exists():
        return

    supported_extensions = ['.pdf', '.docx', '.doc', '.xlsx', '.xls']
    doc_files = [f for f in docs_dir.rglob('*') if f.is_file() and f.suffix.lower() in supported_extensions]

    if not doc_files:
        return

    # ベクトルストアが空なら自動読み込み
    if st.session_state.vector_store and st.session_state.vector_store.get_collection_count() == 0:
        st.info(f"📚 {len(doc_files)}件のドキュメントを自動読み込み中...")
        load_documents()


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
    # 同義語マッピング（社内規定で使われる用語を網羅）
    synonyms = {
        "休暇": ["休暇", "休業", "年休", "有給", "特別休暇", "付与日数", "勤続年数"],
        "休業": ["休暇", "休業", "欠勤"],
        "有給": ["有給", "年休", "休暇", "年次有給休暇", "付与日数", "勤続年数", "10日", "11日", "12日", "14日", "16日", "18日", "20日"],
        "特別休暇": ["特別休暇", "慶弔", "結婚", "忌引", "付与日数", "3日", "2日", "1日"],
        "付与": ["付与", "日数", "付与日数", "勤続年数"],
        "付与日数": ["付与日数", "年次有給休暇", "勤続年数", "10日", "20日"],
        "勤務時間": ["勤務時間", "始業", "終業", "労働時間", "就業時間"],
        "始業": ["始業", "勤務時間", "出勤", "開始"],
        "終業": ["終業", "勤務時間", "退勤", "終了"],
        "給与": ["給与", "給料", "賃金", "報酬"],
        "手当": ["手当", "手当て", "支給"],
        "夜勤": ["夜勤", "夜間", "当直", "深夜"],
        "シフト": ["シフト", "勤務", "番", "交代"],
        "育児": ["育児", "育休", "子育て"],
        "介護": ["介護", "介休", "看護"],
        "出張": ["出張", "旅費", "交通費"],
        "届出": ["届出", "届け出", "申請", "手続き"],
        # 忌引き・慶弔関連
        "亡くなった": ["死亡", "忌引", "忌引き", "慶弔", "慶弔休暇", "特別休暇", "葬儀"],
        "亡くなる": ["死亡", "忌引", "忌引き", "慶弔", "慶弔休暇", "特別休暇", "葬儀"],
        "死亡": ["死亡", "忌引", "忌引き", "慶弔", "慶弔休暇", "特別休暇", "葬儀"],
        "忌引": ["忌引", "忌引き", "死亡", "慶弔", "慶弔休暇", "特別休暇", "葬儀"],
        "忌引き": ["忌引", "忌引き", "死亡", "慶弔", "慶弔休暇", "特別休暇", "葬儀"],
        "葬儀": ["葬儀", "忌引", "忌引き", "死亡", "慶弔", "慶弔休暇"],
        "親": ["父母", "配偶者", "家族"],
        "父": ["父母", "親", "家族"],
        "母": ["父母", "親", "家族"],
        # 結婚関連
        "結婚": ["結婚", "慶弔", "慶弔休暇", "特別休暇", "婚姻"],
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


# よくある質問の事前キャッシュ（APIを使わずに回答を返す）
PRECACHED_RESPONSES = {
    "有給休暇と特別休暇の付与日数を教えてください": """## 年次有給休暇

| 勤続年数 | 6か月 | 1年6か月 | 2年6か月 | 3年6か月 | 4年6か月 | 5年6か月 | 6年6か月以上 |
|----------|-------|---------|---------|---------|---------|---------|-------------|
| 付与日数 | 10日 | 11日 | 12日 | 14日 | 16日 | 18日 | 20日 |

## 特別休暇

### 慶弔休暇

| 事由 | 日数 |
|------|------|
| 本人が結婚したとき | 5日 |
| 配偶者・子・父母が死亡したとき | 3日 |
| 兄弟姉妹・祖父母が死亡したとき | 1日 |

### 新特別休暇（夏季休暇廃止後の制度）

| 入職時期 | 付与日数 |
|----------|----------|
| 4月～7月 | 3日 |
| 8月～11月 | 2日 |
| 12月～3月 | 1日 |

※半日単位から取得可能、有給扱い、年度内に取得（繰り越し不可）""",

    "介護休業について教えてください": """## 介護休業制度

### 基本情報

| 項目 | 内容 |
|:-----|:-----|
| 取得日数 | 対象家族1人につき **のべ93日間まで** |
| 取得回数 | **3回まで**分割取得可能 |
| 申出期限 | 休業開始予定日の **2週間前まで** |
| 申出方法 | 介護休業申出書を病院に提出 |

### 対象となる家族

| 対象家族 |
|:---------|
| 配偶者 |
| 父母 |
| 子 |
| 配偶者の父母 |
| 祖父母、兄弟姉妹又は孫 |
| 上記以外で病院が認めた者 |

### 対象者の条件

| 区分 | 条件 |
|:-----|:-----|
| 正職員 | 要介護状態の家族を介護する職員（日雇職員を除く） |
| 期間契約職員 | 入社1年以上、かつ休業開始から93日+6か月後まで契約継続見込み |

### 取得できない場合

| 除外される職員 |
|:---------------|
| 入社1年未満の職員 |
| 申出日から93日以内に雇用終了が明らかな職員 |
| 週の所定労働日数が2日以下の職員 |

※要介護状態とは、2週間以上の期間にわたり常時介護を必要とする状態をいいます""",

    "育児休業について教えてください": """## 育児休業制度

### 基本情報

| 項目 | 内容 |
|:-----|:-----|
| 対象 | 1歳に満たない子と同居し養育する職員（日雇職員を除く） |
| 申出期限 | 休業開始予定日の **1か月前まで**（1歳超の延長は2週間前まで） |
| 申出回数 | 一子につき **1回**（出生後8週間以内の最初の育児休業は回数に含めない） |
| 申出方法 | 育児休業申出書を病院に提出 |

### 取得可能期間

| 区分 | 期間 | 条件 |
|:-----|:-----|:-----|
| 原則 | 子が **1歳に達するまで** | - |
| 1歳2か月まで | 子が **1歳2か月に達するまで** | 配偶者が職員と同じ日から又は職員より先に育児休業をしている場合 |
| 1歳6か月まで | 子が **1歳6か月に達するまで** | 子の1歳の誕生日前日に育児休業中で、保育所等に入所できない場合等 |
| 2歳まで | 子が **2歳に達するまで** | 子の1歳6か月の誕生日応当日前日に育児休業中で、保育所等に入所できない場合等 |

### 期間契約職員の条件

| 条件 |
|:-----|
| 入社1年以上であること |
| 子が1歳6か月（2歳までの延長申出の場合は2歳）に達する日までに労働契約期間が満了し、更新されないことが明らかでないこと |

### 取得できない場合（労使協定により除外）

| 除外される職員 |
|:---------------|
| 入社1年未満の職員 |
| 申出の日から1年以内に雇用関係が終了することが明らかな職員 |
| 1週間の所定労働日数が2日以下の職員 |""",

    "時間外手当について教えてください": """## 時間外手当・割増賃金（全部署共通）

### 時間外労働の割増賃金

| 区分 | 条件 | 割増率 |
|:-----|:-----|:------:|
| 時間外労働 | 月45時間以下 | **25%** |
| 時間外労働 | 月45時間超〜60時間以下 | **35%** |
| 時間外労働 | 月60時間超の部分 | **50%** |
| 時間外労働 | 年360時間超の部分 | **40%** |

### 休日労働・深夜労働の割増賃金

| 区分 | 条件 | 割増率 |
|:-----|:-----|:------:|
| 休日労働 | 法定休日 | **35%** |
| 深夜労働 | 22:00〜5:00 | **25%** |

※時間外労働が深夜に及ぶ場合は、時間外割増＋深夜割増となります""",

    "忌引き休暇について教えてください": """## 忌引き休暇（慶弔休暇）

家族が亡くなった場合に取得できる特別休暇です。

### 忌引き休暇の日数

| 対象者 | 日数 |
|:-------|:----:|
| 配偶者が死亡したとき | **3日** |
| 子が死亡したとき | **3日** |
| 父母が死亡したとき | **3日** |
| 兄弟姉妹が死亡したとき | **1日** |
| 祖父母が死亡したとき | **1日** |

### 注意事項
- 有給扱いです
- 届出が必要です
- 連続して取得してください""",
}


def get_precached_response(query: str) -> str | None:
    """
    事前キャッシュされた回答を取得

    Args:
        query: ユーザーの質問

    Returns:
        キャッシュされた回答、なければNone
    """
    # 完全一致
    if query in PRECACHED_RESPONSES:
        return PRECACHED_RESPONSES[query]

    # 部分一致で検索
    query_lower = query.lower()
    for key, response in PRECACHED_RESPONSES.items():
        # キーワードベースのマッチング
        if '有給' in query and '特別休暇' in query:
            return PRECACHED_RESPONSES.get("有給休暇と特別休暇の付与日数を教えてください")
        if '介護休業' in query or ('介護' in query and '休' in query):
            return PRECACHED_RESPONSES.get("介護休業について教えてください")
        if '育児休業' in query or '育休' in query or ('育児' in query and '休' in query):
            return PRECACHED_RESPONSES.get("育児休業について教えてください")
        if '時間外手当' in query or ('残業' in query and '手当' in query) or '割増賃金' in query:
            return PRECACHED_RESPONSES.get("時間外手当について教えてください")
        # 忌引き・慶弔休暇関連
        if '亡くなった' in query or '亡くなり' in query or '死亡' in query or '忌引' in query or '葬儀' in query or '慶弔' in query:
            return PRECACHED_RESPONSES.get("忌引き休暇について教えてください")
        # 親が亡くなった場合も対応
        if '親' in query and ('亡' in query or '死' in query):
            return PRECACHED_RESPONSES.get("忌引き休暇について教えてください")

    return None


def call_groq_api(prompt: str, api_key: str, model_name: str = 'llama-3.3-70b-versatile'):
    """
    Groq APIを呼び出す

    Args:
        prompt: プロンプト
        api_key: APIキー
        model_name: 使用するモデル名

    Returns:
        回答テキスト
    """
    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        max_tokens=8000,
    )
    return response.choices[0].message.content


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    reraise=True
)
def call_groq_with_retry(prompt: str, api_key: str, model_name: str = 'llama-3.3-70b-versatile'):
    """
    リトライ機能付きでGroq APIを呼び出す
    エクスポネンシャルバックオフ: 4秒 → 8秒 → 16秒
    """
    return call_groq_api(prompt, api_key, model_name)


def call_gemini_api(prompt: str, api_key: str, model_name: str = 'gemini-2.0-flash'):
    """
    Gemini APIを呼び出す

    Args:
        prompt: プロンプト
        api_key: APIキー
        model_name: 使用するモデル名

    Returns:
        APIレスポンス
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=0.1,
            max_output_tokens=8000,
        )
    )
    return response


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    retry=retry_if_exception_type((ResourceExhausted, Exception)),
    reraise=True
)
def call_gemini_with_retry(prompt: str, api_key: str, model_name: str = 'gemini-2.0-flash'):
    """
    リトライ機能付きでGemini APIを呼び出す
    エクスポネンシャルバックオフ: 4秒 → 8秒 → 16秒
    """
    return call_gemini_api(prompt, api_key, model_name)


def generate_answer(query: str, context_chunks: list) -> str:
    """
    LLMを使用して回答を生成（Groqメイン、Geminiフォールバック）

    Args:
        query: ユーザーの質問
        context_chunks: 関連する文書チャンク

    Returns:
        生成された回答
    """
    # キャッシュをチェック
    cache_key = get_cache_key(query, context_chunks)
    if 'response_cache' not in st.session_state:
        st.session_state.response_cache = {}

    if cache_key in st.session_state.response_cache:
        return st.session_state.response_cache[cache_key] + "\n\n_(キャッシュから取得)_"

    # コンテキストを結合
    context = "\n\n---\n\n".join([
        f"【{chunk['metadata']['filename']}】\n{chunk['content']}"
        for chunk in context_chunks
    ])

    # 部署情報を取得
    department = st.session_state.get('selected_department', '')
    dept_context = f"\nユーザーの所属部署: {department}\n" if department else ""

    # プロンプトの作成
    prompt = f"""あなたは社内規定に詳しいアシスタントです。以下の参照情報を基に、質問に回答してください。

【ユーザーの所属部署】{department}

【参照情報】
{context}

【質問】
{query}

【回答ルール】
1. 質問されたことだけに回答すること
2. 参照情報にある表やデータは、そのままの形式で出力すること（まとめたり要約しない）
3. 「【{department}の勤務時間】」というセクションがあれば、その表をそのまま出力すること

【勤務時間について聞かれた場合 - 必ずMarkdown表形式で出力】
参照情報に「【{department}の勤務時間】」があれば、以下の形式で出力：

【{department}の勤務時間】

| 勤務種別 | 始業～終業 | 拘束時間 | 休憩時間 | 勤務時間 |
|----------|------------|----------|----------|----------|
| （参照情報の各行をここに記載） |

★重要：必ず上記のMarkdown表形式（|で区切り、各行を改行）で出力すること
★参照情報にある勤務種別（日勤、早番、遅番、夜勤、土曜など）を全て含めること
★1行にまとめず、必ず改行して表形式にすること

【有給休暇について聞かれた場合】
以下の表のみを出力すること：

| 勤続年数 | 6か月 | 1年6か月 | 2年6か月 | 3年6か月 | 4年6か月 | 5年6か月 | 6年6か月以上 |
|----------|-------|---------|---------|---------|---------|---------|-------------|
| 付与日数 | 10日 | 11日 | 12日 | 14日 | 16日 | 18日 | 20日 |

【特別休暇について聞かれた場合】
慶弔休暇と新特別休暇（夏季休暇廃止後の制度）について回答すること。

【回答】"""

    last_error = None
    used_provider = None

    # 1. まずGroqを試す（メイン）
    groq_api_key = get_groq_api_key()
    if groq_api_key:
        groq_models = [
            'llama-3.3-70b-versatile',
            'llama-3.1-8b-instant',  # フォールバック
        ]
        for model_name in groq_models:
            try:
                result = call_groq_with_retry(prompt, groq_api_key, model_name)

                # キャッシュに保存
                st.session_state.response_cache[cache_key] = result

                return result

            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                # レート制限エラーの場合、次のモデルを試す
                if '429' in error_str or 'rate' in error_str or 'limit' in error_str:
                    continue
                # その他のエラーは次のプロバイダーへ
                break

    # 2. Groqが失敗したらGeminiを試す（フォールバック）
    gemini_api_key = get_gemini_api_key()
    gemini_models = [
        'gemini-2.0-flash',
        'gemini-1.5-flash',
        'gemini-1.5-pro',
    ]

    for model_name in gemini_models:
        try:
            response = call_gemini_with_retry(prompt, gemini_api_key, model_name)

            # レスポンスの完全性チェック
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if candidate.finish_reason.name == "SAFETY":
                    result = "安全性フィルターにより回答がブロックされました。別の質問をお試しください。"
                elif candidate.content and candidate.content.parts:
                    result = candidate.content.parts[0].text
                else:
                    result = response.text
            else:
                result = response.text

            # キャッシュに保存
            st.session_state.response_cache[cache_key] = result

            # フォールバック使用を表示
            result += f"\n\n_(フォールバック: Gemini {model_name}を使用)_"

            return result

        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            # 429エラーまたはリソース枯渇の場合、次のモデルを試す
            if '429' in error_str or 'resource' in error_str or 'exhausted' in error_str or 'quota' in error_str:
                continue
            # その他のエラーは即座に返す
            break

    # 全てのプロバイダーで失敗した場合
    return f"""⚠️ APIが一時的に利用できません。

**エラー詳細**: {str(last_error)}

**対処方法**:
1. 管理画面からGroq APIキーを設定してください（推奨）
2. 数分待ってから再度お試しください
3. よくある質問ボタンを使うと、キャッシュされた回答を利用できます

**Groq APIキーの取得方法**:
https://console.groq.com/keys からアカウントを作成して無料でAPIキーを取得できます。

申し訳ございませんが、しばらくお待ちください。"""


def main():
    """メイン処理"""

    # パスワード認証
    if not check_password():
        return

    init_session_state()

    # 管理画面表示
    if st.session_state.show_admin:
        render_admin_page()
        return

    # サイドバー
    with st.sidebar:
        st.title("⚙️ 設定")

        # デバッグモード
        debug_mode = st.checkbox("🔍 デバッグモード（検索結果を表示）", value=False)

        # ベクトルストアを初期化
        initialize_vector_store()

        # ドキュメント自動読み込み（初回起動時のみ）
        auto_load_documents()

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
            st.success("チャット履歴をクリアしました")
            st.rerun()

        st.divider()

        # 使い方
        st.subheader("📖 使い方")
        st.markdown("""
        1. 部署を選択
        2. よくある質問ボタンをクリック、または自由に質問を入力
        """)

        st.divider()

        # 管理画面へのリンク
        if st.button("🔧 管理画面", use_container_width=True):
            st.session_state.show_admin = True
            st.rerun()

    # メインエリア
    st.title("📚 社内規定検索チャットボット")

    if not st.session_state.initialized:
        st.info("左のサイドバーから「ドキュメントを読み込む」ボタンをクリックして、ドキュメントを登録してください")
        return

    # 部署選択UI（部署未選択時のみ表示）
    if not st.session_state.selected_department:
        render_department_selector()
        st.info("👆 部署を選択すると質問できます")
        return

    # 選択された部署を表示
    if st.session_state.selected_department:
        # 部署表示と変更ボタンを横並び
        col1, col2 = st.columns([3, 1])
        with col1:
            st.success(f"📍 {st.session_state.selected_department}")
        with col2:
            if st.button("変更", key="reset_dept"):
                st.session_state.selected_department = None
                st.session_state.messages = []  # チャット履歴もクリア
                st.rerun()

        # よくある質問ボタン（4つずつ2行に分けて表示）
        st.markdown("##### よくある質問")
        # 1行目（4つ）
        cols1 = st.columns(4)
        for i, q in enumerate(QUICK_QUESTIONS[:4]):
            with cols1[i]:
                if st.button(q["label"], key=f"q_{i}", use_container_width=True):
                    st.session_state.pending_question = q["question"]
                    st.rerun()
        # 2行目（残り）
        cols2 = st.columns(4)
        for i, q in enumerate(QUICK_QUESTIONS[4:]):
            with cols2[i]:
                if st.button(q["label"], key=f"q2_{i}", use_container_width=True):
                    st.session_state.pending_question = q["question"]
                    st.rerun()

        st.caption("💬 または下の入力欄から自由に質問できます")
        st.divider()

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

    # 質問候補ボタンからの質問を処理
    if st.session_state.pending_question:
        prompt = st.session_state.pending_question
        st.session_state.pending_question = None
    else:
        prompt = st.chat_input("質問を入力してください（例：有給休暇の申請方法は？）")

    # ユーザー入力を処理
    if prompt:
        # ユーザーメッセージを表示
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # アシスタントの回答を生成
        with st.chat_message("assistant"):
            # まず事前キャッシュをチェック（APIを使わない）
            precached = get_precached_response(prompt)
            if precached:
                st.markdown(precached)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": precached,
                    "sources": []
                })
                st.rerun()

            with st.spinner("検索中..."):
                # 選択した部署をクエリに追加
                dept = st.session_state.get('selected_department', '')
                search_query = f"{dept} {prompt}" if dept else prompt

                # 部署名のスペース対応（ドキュメント内で「薬　局」のようにスペースが入っている場合）
                dept_variants = {
                    "薬局": "薬　局",
                    "検査科": "検 査 科",
                    "事務部門": "事 務 部 門",
                    "診療部": "診 療 部",
                    "看護部門": "看 護 部 門",
                    "放射線科": "放 射 線 科",
                    "栄養科": "栄 養 科",
                }
                dept_search = dept
                if dept in dept_variants:
                    dept_search = dept_variants[dept]
                    search_query = f"{dept_search} {prompt}" if dept else prompt

                # クエリを拡張（同義語を含める）
                expanded_prompt = expand_query(search_query)

                # ハイブリッド検索（ベクトル + キーワード + リランキング）
                search_results = st.session_state.vector_store.search(
                    expanded_prompt,
                    n_results=15,  # より多くの関連情報を取得
                    use_reranking=True,
                    distance_threshold=3.0  # 閾値を緩めて関連情報を拾いやすく
                )

                # 勤務時間の質問時は、固定の表を直接出力
                if '勤務時間' in prompt or '始業' in prompt or '終業' in prompt or '何時' in prompt:
                    # 部署ごとの勤務時間データ
                    work_hours_data = {
                        "診療部": """## 診療部の勤務時間

| 勤務種別 | 始業～終業 | 拘束時間 | 休憩時間 | 勤務時間 |
|----------|------------|----------|----------|----------|
| 日勤 | 8:30～17:00 | 8:30 | 1:12 | 7:18 |
| 夜勤 | 16:30～9:00 | 16:30 | 1:54 | 14:36 |
| 土曜 | 8:30～12:00 | 3:30 | － | 3:30 |""",
                        "看護部門": """## 看護部門の勤務時間

| 勤務種別 | 始業～終業 | 拘束時間 | 休憩時間 | 勤務時間 |
|----------|------------|----------|----------|----------|
| 日勤 | 8:30～17:00 | 8:30 | 1:12 | 7:18 |
| 遅番 | 10:00～18:30 | 8:30 | 1:12 | 7:18 |
| 夜勤 | 16:30～9:00 | 16:30 | 1:54 | 14:36 |
| 土曜 | 8:30～12:00 | 3:30 | － | 3:30 |""",
                        "放射線科": """## 放射線科の勤務時間

| 勤務種別 | 始業～終業 | 拘束時間 | 休憩時間 | 勤務時間 |
|----------|------------|----------|----------|----------|
| 日勤 | 8:30～17:00 | 8:30 | 1:12 | 7:18 |
| 遅番 | 10:30～19:00 | 8:30 | 1:12 | 7:18 |
| 土曜 | 8:30～12:00 | 3:30 | － | 3:30 |""",
                        "リハビリテーション科": """## リハビリテーション科の勤務時間

| 勤務種別 | 始業～終業 | 拘束時間 | 休憩時間 | 勤務時間 |
|----------|------------|----------|----------|----------|
| 日勤 | 8:30～17:00 | 8:30 | 1:12 | 7:18 |
| 遅番 | 10:30～19:00 | 8:30 | 1:12 | 7:18 |
| 土曜 | 8:30～12:00 | 3:30 | － | 3:30 |""",
                        "栄養科": """## 栄養科の勤務時間

| 勤務種別 | 始業～終業 | 拘束時間 | 休憩時間 | 勤務時間 |
|----------|------------|----------|----------|----------|
| 早番 | 6:15～14:45 | 8:30 | 1:12 | 7:18 |
| 日１ | 7:30～16:00 | 8:30 | 1:12 | 7:18 |
| 日勤 | 8:30～17:00 | 8:30 | 1:12 | 7:18 |
| 遅番 | 10:30～19:00 | 8:30 | 1:12 | 7:18 |""",
                        "検査科": """## 検査科の勤務時間

| 勤務種別 | 始業～終業 | 拘束時間 | 休憩時間 | 勤務時間 |
|----------|------------|----------|----------|----------|
| 日勤 | 8:30～17:00 | 8:30 | 1:12 | 7:18 |
| 土曜 | 8:30～12:00 | 3:30 | － | 3:30 |""",
                        "薬局": """## 薬局の勤務時間

| 勤務種別 | 始業～終業 | 拘束時間 | 休憩時間 | 勤務時間 |
|----------|------------|----------|----------|----------|
| 日勤 | 8:30～17:00 | 8:30 | 1:12 | 7:18 |
| 土曜 | 8:30～12:00 | 3:30 | － | 3:30 |""",
                        "地域連携室": """## 地域連携室の勤務時間

| 勤務種別 | 始業～終業 | 拘束時間 | 休憩時間 | 勤務時間 |
|----------|------------|----------|----------|----------|
| 日勤 | 8:30～17:00 | 8:30 | 1:12 | 7:18 |
| 土曜 | 8:30～12:00 | 3:30 | － | 3:30 |""",
                        "事務部門": """## 事務部門の勤務時間

| 勤務種別 | 始業～終業 | 拘束時間 | 休憩時間 | 勤務時間 |
|----------|------------|----------|----------|----------|
| 日勤 | 8:30～17:00 | 8:30 | 1:12 | 7:18 |
| 早番 | 8:00～16:30 | 8:30 | 1:12 | 7:18 |
| 遅番 | 10:30～19:00 | 8:30 | 1:12 | 7:18 |
| 土曜 | 8:30～12:00 | 3:30 | － | 3:30 |""",
                        "訪問看護ステーション": """## 訪問看護ステーションの勤務時間

| 勤務種別 | 始業～終業 | 拘束時間 | 休憩時間 | 勤務時間 |
|----------|------------|----------|----------|----------|
| 日勤 | 8:30～17:00 | 8:30 | 1:12 | 7:18 |
| 土曜 | 8:30～12:00 | 3:30 | － | 3:30 |""",
                    }

                    if dept in work_hours_data:
                        work_hours_response = work_hours_data[dept]
                        st.markdown(work_hours_response)
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": work_hours_response,
                            "sources": []
                        })
                        st.rerun()

                # 介護休業の質問時は、固定の表を直接出力
                if '介護休業' in prompt or '介護休暇' in prompt or ('介護' in prompt and '休' in prompt):
                    nursing_care_response = """## 介護休業制度

### 基本情報

| 項目 | 内容 |
|:-----|:-----|
| 取得日数 | 対象家族1人につき **のべ93日間まで** |
| 取得回数 | **3回まで**分割取得可能 |
| 申出期限 | 休業開始予定日の **2週間前まで** |
| 申出方法 | 介護休業申出書を病院に提出 |

### 対象となる家族

| 対象家族 |
|:---------|
| 配偶者 |
| 父母 |
| 子 |
| 配偶者の父母 |
| 祖父母、兄弟姉妹又は孫 |
| 上記以外で病院が認めた者 |

### 対象者の条件

| 区分 | 条件 |
|:-----|:-----|
| 正職員 | 要介護状態の家族を介護する職員（日雇職員を除く） |
| 期間契約職員 | 入社1年以上、かつ休業開始から93日+6か月後まで契約継続見込み |

### 取得できない場合

| 除外される職員 |
|:---------------|
| 入社1年未満の職員 |
| 申出日から93日以内に雇用終了が明らかな職員 |
| 週の所定労働日数が2日以下の職員 |

※要介護状態とは、2週間以上の期間にわたり常時介護を必要とする状態をいいます"""
                    st.markdown(nursing_care_response)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": nursing_care_response,
                        "sources": []
                    })
                    st.rerun()

                # 育児休業の質問時は、固定の表を直接出力
                if '育児休業' in prompt or '育児休暇' in prompt or '育休' in prompt or ('育児' in prompt and '休' in prompt):
                    childcare_response = """## 育児休業制度

### 基本情報

| 項目 | 内容 |
|:-----|:-----|
| 対象 | 1歳に満たない子と同居し養育する職員（日雇職員を除く） |
| 申出期限 | 休業開始予定日の **1か月前まで**（1歳超の延長は2週間前まで） |
| 申出回数 | 一子につき **1回**（出生後8週間以内の最初の育児休業は回数に含めない） |
| 申出方法 | 育児休業申出書を病院に提出 |

### 取得可能期間

| 区分 | 期間 | 条件 |
|:-----|:-----|:-----|
| 原則 | 子が **1歳に達するまで** | - |
| 1歳2か月まで | 子が **1歳2か月に達するまで** | 配偶者が職員と同じ日から又は職員より先に育児休業をしている場合（産前産後休業期間と育児休業期間の合計が1年限度） |
| 1歳6か月まで | 子が **1歳6か月に達するまで** | 子の1歳の誕生日前日に育児休業中で、保育所等に入所できない場合等 |
| 2歳まで | 子が **2歳に達するまで** | 子の1歳6か月の誕生日応当日前日に育児休業中で、保育所等に入所できない場合等 |

### 期間契約職員の条件

| 条件 |
|:-----|
| 入社1年以上であること |
| 子が1歳6か月（2歳までの延長申出の場合は2歳）に達する日までに労働契約期間が満了し、更新されないことが明らかでないこと |

### 取得できない場合（労使協定により除外）

| 除外される職員 |
|:---------------|
| 入社1年未満の職員 |
| 申出の日から1年以内（1歳6か月・2歳までの申出は6か月以内）に雇用関係が終了することが明らかな職員 |
| 1週間の所定労働日数が2日以下の職員 |

### 期間の変更

| 変更内容 | 申出期限 | 回数 |
|:---------|:---------|:-----|
| 開始予定日の繰り上げ | 育児休業開始予定日の **1週間前まで** | 原則1回 |
| 終了予定日の繰り下げ | 育児休業終了予定日の **1か月前まで**（1歳6か月までの休業は2週間前まで） | 原則1回 |

※1歳6か月までの休業の場合、1歳までの休業とは別に1回、終了予定日の繰り下げ変更が可能

### 育児休業が終了する場合

| 事由 | 終了日 |
|:-----|:-------|
| 子の死亡等により養育しないこととなった場合 | 当該事由が発生した日 |
| 子が1歳に達した場合（1歳6か月までの延長の場合は1歳6か月に達した日） | 子が1歳（または1歳6か月）に達した日 |
| 産前産後休業、介護休業又は新たな育児休業期間が始まった場合 | 当該休業の開始日の前日 |
| 産前産後休業期間と育児休業期間との合計が1年に達した場合 | 1年に達した日 |"""
                    st.markdown(childcare_response)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": childcare_response,
                        "sources": []
                    })
                    st.rerun()

                # 有給休暇・特別休暇の質問時は、固定の表を直接出力
                if '有給' in prompt or '特別休暇' in prompt or ('休暇' in prompt and '付与' in prompt):
                    leave_response = """## 年次有給休暇

| 勤続年数 | 6か月 | 1年6か月 | 2年6か月 | 3年6か月 | 4年6か月 | 5年6か月 | 6年6か月以上 |
|----------|-------|---------|---------|---------|---------|---------|-------------|
| 付与日数 | 10日 | 11日 | 12日 | 14日 | 16日 | 18日 | 20日 |

## 特別休暇

### 慶弔休暇

| 事由 | 日数 |
|------|------|
| 本人が結婚したとき | 5日 |
| 配偶者・子・父母が死亡したとき | 3日 |
| 兄弟姉妹・祖父母が死亡したとき | 1日 |

### 新特別休暇（夏季休暇廃止後の制度）

| 入職時期 | 付与日数 |
|----------|----------|
| 4月～7月 | 3日 |
| 8月～11月 | 2日 |
| 12月～3月 | 1日 |

※半日単位から取得可能、有給扱い、年度内に取得（繰り越し不可）"""
                    st.markdown(leave_response)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": leave_response,
                        "sources": []
                    })
                    st.rerun()

                # 時間外手当の質問時は、固定の表を直接出力（全部署共通）
                if '時間外手当' in prompt or '時間外労働' in prompt or '割増賃金' in prompt or ('残業' in prompt and '手当' in prompt):
                    overtime_response = """## 時間外手当・割増賃金（全部署共通）

### 時間外労働の割増賃金

| 区分 | 条件 | 割増率 |
|:-----|:-----|:------:|
| 時間外労働 | 月45時間以下 | **25%** |
| 時間外労働 | 月45時間超〜60時間以下 | **35%** |
| 時間外労働 | 月60時間超の部分 | **50%** |
| 時間外労働 | 年360時間超の部分 | **40%** |

### 休日労働・深夜労働の割増賃金

| 区分 | 条件 | 割増率 |
|:-----|:-----|:------:|
| 休日労働 | 法定休日 | **35%** |
| 深夜労働 | 22:00〜5:00 | **25%** |

※時間外労働が深夜に及ぶ場合は、時間外割増＋深夜割増となります"""
                    st.markdown(overtime_response)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": overtime_response,
                        "sources": []
                    })
                    st.rerun()

                # 有給休暇・特別休暇の質問時は、表を含むチャンクを優先（上記以外の休暇関連）
                elif '休暇' in prompt or '付与' in prompt:
                    # 付与日数の表を含むチャンクを上位に
                    prioritized = []
                    others = []
                    for r in search_results:
                        content = r['content']
                        # 年次有給休暇の表
                        is_paid_leave = ('付与日数' in content and ('10日' in content or '11日' in content))
                        # 特別休暇（慶弔など）
                        is_special_leave = ('特別休暇' in content and ('結婚' in content or '死亡' in content))
                        # 新特別休暇（夏季休暇廃止後の制度）
                        is_new_special = ('夏季休暇' in content or ('４月～７月' in content or '4月～7月' in content))

                        if is_paid_leave or is_special_leave or is_new_special:
                            prioritized.append(r)
                        else:
                            others.append(r)
                    search_results = prioritized + others

                # デバッグモード：検索結果を表示
                if debug_mode and search_results:
                    with st.expander("🔍 検索結果の詳細", expanded=True):
                        st.write(f"**拡張クエリ:** {expanded_prompt}")
                        st.write(f"**検索結果数:** {len(search_results)}")
                        for i, result in enumerate(search_results, 1):
                            rerank_score = result.get('rerank_score', 0)
                            st.markdown(f"**{i}. {result['metadata']['filename']}** (距離: {result['distance']:.3f}, リランクスコア: {rerank_score:.3f})")
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
                        response = generate_answer(prompt, search_results)
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
