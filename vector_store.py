"""
ベクトルストア管理モジュール
Sentence TransformersとチromaDBを使用してドキュメントをベクトル化・検索
"""
import os
from typing import List, Dict
from sentence_transformers import SentenceTransformer
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
        # Sentence Transformerモデルの読み込み
        print("埋め込みモデルを読み込み中...")
        self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        print("✓ モデルの読み込み完了")

        # ChromaDB クライアントの初期化
        self.client = chromadb.PersistentClient(path=persist_directory)

        # コレクションの取得または作成
        try:
            self.collection = self.client.get_collection(name=collection_name)
            print(f"既存のコレクション '{collection_name}' を読み込みました")
        except:
            self.collection = self.client.create_collection(name=collection_name)
            print(f"新しいコレクション '{collection_name}' を作成しました")

    def get_embedding(self, text: str) -> List[float]:
        """
        Sentence Transformersを使用してテキストをベクトル化

        Args:
            text: ベクトル化するテキスト

        Returns:
            埋め込みベクトル
        """
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """
        長いテキストをチャンクに分割

        Args:
            text: 分割するテキスト
            chunk_size: 各チャンクの文字数
            overlap: チャンク間のオーバーラップ文字数

        Returns:
            テキストチャンクのリスト
        """
        chunks = []
        start = 0

        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]

            # 空白で区切るために、最後の改行または句点を探す
            if end < len(text):
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

        embeddings = self.model.encode(all_chunks,
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

    def search(self, query: str, n_results: int = 5) -> List[Dict]:
        """
        ハイブリッド検索：ベクトル検索 + キーワード検索

        Args:
            query: 検索クエリ
            n_results: 返す結果の数

        Returns:
            検索結果のリスト
        """
        # 1. ベクトル検索
        query_embedding = self.model.encode(query, convert_to_numpy=True).tolist()
        vector_results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results * 2
        )

        # 2. キーワード検索（全チャンクから部分一致）
        keyword_matches = self._keyword_search(query, n_results * 2)

        # 3. 結果を統合
        all_results = {}

        # ベクトル検索結果を追加
        if vector_results['documents'] and len(vector_results['documents']) > 0:
            for i in range(len(vector_results['documents'][0])):
                doc_id = vector_results['ids'][0][i]
                all_results[doc_id] = {
                    'content': vector_results['documents'][0][i],
                    'metadata': vector_results['metadatas'][0][i],
                    'distance': vector_results['distances'][0][i] if 'distances' in vector_results else 10,
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

        # 4. スコアを計算して並び替え
        formatted_results = []
        for doc_id, result in all_results.items():
            # 複合スコア: キーワードスコアを重視
            combined_score = -result['distance'] + (result['keyword_score'] * 3)
            result['combined_score'] = combined_score
            formatted_results.append(result)

        formatted_results.sort(key=lambda x: x['combined_score'], reverse=True)
        return formatted_results[:n_results]

    def _keyword_search(self, query: str, max_results: int) -> List[Dict]:
        """キーワード部分一致検索"""
        # クエリからキーワードを抽出
        keywords = []
        query_clean = query.replace('？', '').replace('?', '').replace('の', ' ').replace('は', ' ')
        for word in query_clean.split():
            if len(word) >= 2:
                keywords.append(word)
                # 「〜科」などの接尾辞を除去した形も追加
                if word.endswith(('科', '部', '室')):
                    keywords.append(word[:-1])

        if not keywords:
            return []

        # 全ドキュメントを取得してキーワードマッチ
        all_data = self.collection.get(include=['documents', 'metadatas'])
        matches = []

        for i, doc in enumerate(all_data['documents']):
            score = 0
            for kw in keywords:
                if kw in doc:
                    # キーワードの出現回数に応じてスコア付け
                    score += doc.count(kw) * 2
                    # タイトル部分（【】内）にある場合はボーナス
                    if f'【{kw}' in doc or f'{kw}】' in doc:
                        score += 5

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
