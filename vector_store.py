"""
ベクトルストア管理モジュール
Sentence TransformersとChromaDBを使用してドキュメントをベクトル化・検索
"""
import os
from typing import List, Dict, Optional
from sentence_transformers import SentenceTransformer, CrossEncoder
import chromadb
from chromadb.config import Settings


class VectorStore:
    """ベクトルストアを管理するクラス"""

    def __init__(self, collection_name: str = "company_documents", persist_directory: str = "./data/chroma_db"):
        """
        Args:
            collection_name: ChromaDBのコレクション名
            persist_directory: ChromaDBの永続化ディレクトリ
        """
        # Sentence Transformerモデルの読み込み（高精度な多言語モデル）
        print("埋め込みモデルを読み込み中...")
        # より高精度な多言語モデルを使用
        self.model = SentenceTransformer('intfloat/multilingual-e5-base')
        print("✓ 埋め込みモデルの読み込み完了")

        # リランキング用のCross-Encoderモデル
        print("リランキングモデルを読み込み中...")
        self.reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
        print("✓ リランキングモデルの読み込み完了")

        # ChromaDB クライアントの初期化
        self.client = chromadb.PersistentClient(path=persist_directory)

        # コレクションの取得または作成
        try:
            self.collection = self.client.get_collection(name=collection_name)
            print(f"既存のコレクション '{collection_name}' を読み込みました")
        except:
            self.collection = self.client.create_collection(name=collection_name)
            print(f"新しいコレクション '{collection_name}' を作成しました")

    def get_embedding(self, text: str, is_query: bool = False) -> List[float]:
        """
        Sentence Transformersを使用してテキストをベクトル化

        Args:
            text: ベクトル化するテキスト
            is_query: クエリの場合はTrue（E5モデル用プレフィックスを追加）

        Returns:
            埋め込みベクトル
        """
        # E5モデルはクエリとドキュメントで異なるプレフィックスを使用
        if is_query:
            text = f"query: {text}"
        else:
            text = f"passage: {text}"
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def chunk_text(self, text: str, chunk_size: int = 800, overlap: int = 150) -> List[str]:
        """
        長いテキストをチャンクに分割
        勤務時間表などの表データは1つのチャンクとして保持

        Args:
            text: 分割するテキスト
            chunk_size: 各チャンクの文字数
            overlap: チャンク間のオーバーラップ文字数

        Returns:
            テキストチャンクのリスト
        """
        import re

        chunks = []

        # 勤務時間表を先に抽出（【〇〇の勤務時間】から次の【または文末まで）
        time_table_pattern = r'【[^】]*の勤務時間】[^【]*'
        time_tables = re.findall(time_table_pattern, text)

        # 勤務時間表を独立したチャンクとして追加
        for table in time_tables:
            if table.strip():
                chunks.append(table.strip())

        # 勤務時間表を除いたテキストを通常のチャンク分割
        text_without_tables = re.sub(time_table_pattern, '', text)

        start = 0
        while start < len(text_without_tables):
            end = start + chunk_size
            chunk = text_without_tables[start:end]

            # 空白で区切るために、最後の改行または句点を探す
            if end < len(text_without_tables):
                last_break = max(
                    chunk.rfind('\n'),
                    chunk.rfind('。'),
                    chunk.rfind('. ')
                )
                if last_break > chunk_size * 0.5:
                    chunk = chunk[:last_break + 1]
                    end = start + last_break + 1

            if chunk.strip():
                chunks.append(chunk.strip())

            start = end - overlap

        return chunks

    def add_documents(self, documents: List[Dict[str, str]]):
        """
        ドキュメントをベクトル化してChromaDBに保存

        Args:
            documents: ドキュメントのリスト [{'filename': str, 'content': str, 'file_type': str}]
        """
        all_chunks = []
        all_metadatas = []
        all_ids = []

        for doc_idx, doc in enumerate(documents):
            print(f"\nベクトル化中: {doc['filename']}")

            # テキストをチャンクに分割
            chunks = self.chunk_text(doc['content'])
            print(f"  {len(chunks)} チャンクに分割")

            for chunk_idx, chunk in enumerate(chunks):
                all_chunks.append(chunk)
                all_metadatas.append({
                    'filename': doc['filename'],
                    'file_type': doc['file_type'],
                    'chunk_index': chunk_idx,
                    'total_chunks': len(chunks)
                })
                all_ids.append(f"{doc['filename']}_{chunk_idx}")

        # 一括でembeddingを取得（高速！）
        print(f"\n全 {len(all_chunks)} チャンクのembeddingを取得中...")
        print("※ ローカルモデルを使用しているため、API制限なしで高速処理します")

        # E5モデル用にpassage:プレフィックスを追加
        prefixed_chunks = [f"passage: {chunk}" for chunk in all_chunks]
        embeddings = self.model.encode(prefixed_chunks,
                                       convert_to_numpy=True,
                                       show_progress_bar=True)
        embeddings_list = [emb.tolist() for emb in embeddings]

        # ChromaDBに追加
        print("\nChromaDBに保存中...")
        self.collection.add(
            embeddings=embeddings_list,
            documents=all_chunks,
            metadatas=all_metadatas,
            ids=all_ids
        )
        print("保存完了！")

    def search(self, query: str, n_results: int = 5, use_reranking: bool = True,
               distance_threshold: float = 1.5) -> List[Dict]:
        """
        ハイブリッド検索：ベクトル検索 + キーワード検索 + リランキング

        Args:
            query: 検索クエリ
            n_results: 返す結果の数
            use_reranking: リランキングを使用するかどうか
            distance_threshold: この距離を超える結果は除外（低いほど厳しい）

        Returns:
            検索結果のリスト
        """
        # 1. ベクトル検索（E5モデル用にquery:プレフィックスを追加）
        query_with_prefix = f"query: {query}"
        query_embedding = self.model.encode(query_with_prefix, convert_to_numpy=True).tolist()
        vector_results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results * 3  # リランキング用に多めに取得
        )

        # 2. キーワード検索（全チャンクから部分一致）
        keyword_matches = self._keyword_search(query, n_results * 2)

        # 3. 結果を統合
        all_results = {}

        # ベクトル検索結果を追加
        if vector_results['documents'] and len(vector_results['documents']) > 0:
            for i in range(len(vector_results['documents'][0])):
                doc_id = vector_results['ids'][0][i]
                distance = vector_results['distances'][0][i] if 'distances' in vector_results else 10
                all_results[doc_id] = {
                    'content': vector_results['documents'][0][i],
                    'metadata': vector_results['metadatas'][0][i],
                    'distance': distance,
                    'keyword_score': 0
                }

        # キーワード検索結果を追加/更新
        for match in keyword_matches:
            doc_id = match['id']
            if doc_id in all_results:
                all_results[doc_id]['keyword_score'] = match['score']
            else:
                all_results[doc_id] = {
                    'content': match['content'],
                    'metadata': match['metadata'],
                    'distance': 10,  # キーワードのみの場合は高い距離
                    'keyword_score': match['score']
                }

        # 4. 距離による閾値フィルタリング（キーワードスコアがある場合は緩める）
        filtered_results = {}
        for doc_id, result in all_results.items():
            # キーワードマッチがある場合は閾値を大幅に緩める
            if result['keyword_score'] > 0:
                # キーワードマッチがあれば基本的に含める
                filtered_results[doc_id] = result
            elif result['distance'] <= distance_threshold:
                # ベクトル検索のみでも閾値以内なら含める
                filtered_results[doc_id] = result

        # 5. リランキング（Cross-Encoderで精度向上）
        if use_reranking and filtered_results:
            pairs = [(query, result['content']) for result in filtered_results.values()]
            rerank_scores = self.reranker.predict(pairs)

            for idx, (doc_id, result) in enumerate(filtered_results.items()):
                result['rerank_score'] = float(rerank_scores[idx])
                # キーワードスコアが高い場合はリランクスコアにボーナスを追加
                if result['keyword_score'] >= 50:
                    result['rerank_score'] += 10  # 勤務時間表チャンクを優先
                if result['keyword_score'] >= 100:
                    result['rerank_score'] += 20  # 該当部署の勤務時間表を最優先

            # リランキングスコアでソート
            formatted_results = list(filtered_results.values())
            formatted_results.sort(key=lambda x: x['rerank_score'], reverse=True)
        else:
            # リランキングなしの場合は複合スコアでソート
            formatted_results = []
            for doc_id, result in filtered_results.items():
                combined_score = -result['distance'] + (result['keyword_score'] * 3)
                result['combined_score'] = combined_score
                result['rerank_score'] = 0
                formatted_results.append(result)
            formatted_results.sort(key=lambda x: x['combined_score'], reverse=True)

        return formatted_results[:n_results]

    def _keyword_search(self, query: str, max_results: int) -> List[Dict]:
        """キーワード部分一致検索"""
        import re

        # 部署名のパターンリスト（スペース有無両対応）
        dept_patterns = [
            '診療部', '看護部門', '放射線科', 'リハビリテーション科', 'リハビリ',
            '栄養科', '検査科', '薬局', '薬　局', '地域連携室', '事務部門', '事務',
            '訪問看護ステーション', '訪問看護', 'パートタイマー'
        ]

        # クエリから部署名を抽出
        keywords = []
        for dept in dept_patterns:
            if dept in query:
                keywords.append(dept)

        # 重要キーワードも追加
        important_keywords = ['勤務時間', '始業', '終業', 'シフト', '休暇', '休業', '給与', '手当',
                             '有給', '年次有給', '特別休暇', '付与', '日数', '届出', '手続き']
        for kw in important_keywords:
            if kw in query:
                keywords.append(kw)

        # 勤務時間に関するクエリかどうかを判定
        is_work_time_query = any(kw in query for kw in ['勤務時間', '始業', '終業', 'シフト', '勤務'])

        # 休暇に関するクエリかどうかを判定
        is_leave_query = any(kw in query for kw in ['休暇', '有給', '特別休暇', '付与', '日数'])

        # 全ドキュメントを取得してキーワードマッチ
        all_data = self.collection.get(include=['documents', 'metadatas'])
        matches = []

        for i, doc in enumerate(all_data['documents']):
            score = 0

            # 勤務時間表チャンクに大幅ボーナス
            if is_work_time_query and '勤務時間】' in doc:
                score += 50  # 勤務時間表チャンクを大幅に優先

            # 休暇関連チャンクにボーナス
            if is_leave_query:
                if '年次有給休暇' in doc:
                    score += 50
                if '特別休暇' in doc:
                    score += 50
                if '付与日数' in doc:
                    score += 100  # 付与日数の表を最優先
                # 日数の表（10日、11日など）を含むチャンクに大幅ボーナス
                if '10日' in doc and '11日' in doc and '12日' in doc:
                    score += 80  # 付与日数テーブルを優先

            for kw in keywords:
                if kw in doc:
                    # キーワードの出現回数に応じてスコア付け
                    score += doc.count(kw) * 2
                    # タイトル部分（【】内）にある場合はボーナス
                    if f'【{kw}' in doc or f'{kw}】' in doc:
                        score += 20  # ボーナスを増加
                    # 勤務時間表のヘッダーに部署名がある場合は大幅ボーナス
                    if f'【{kw}' in doc and '勤務時間】' in doc:
                        score += 100  # 該当部署の勤務時間表を最優先

            if score > 0:
                matches.append({
                    'id': all_data['ids'][i],
                    'content': doc,
                    'metadata': all_data['metadatas'][i],
                    'score': score
                })

        # スコア順にソート
        matches.sort(key=lambda x: x['score'], reverse=True)
        return matches[:max_results]

    def clear_collection(self):
        """コレクション内の全データを削除"""
        self.client.delete_collection(name=self.collection.name)
        self.collection = self.client.create_collection(name=self.collection.name)
        print("コレクションをクリアしました")

    def get_collection_count(self) -> int:
        """コレクション内のドキュメント数を取得"""
        return self.collection.count()
