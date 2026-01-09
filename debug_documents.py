"""
ドキュメント読み込みのデバッグスクリプト
"""
from document_processor import DocumentProcessor

processor = DocumentProcessor(documents_dir="documents")
documents = processor.process_all_documents()

print("=" * 80)
print(f"読み込まれたドキュメント数: {len(documents)}")
print("=" * 80)

for i, doc in enumerate(documents, 1):
    print(f"\n【ドキュメント {i}】")
    print(f"ファイル名: {doc['filename']}")
    print(f"ファイル種類: {doc['file_type']}")
    print(f"テキスト長: {len(doc['content'])} 文字")
    print(f"最初の500文字:")
    print("-" * 80)
    print(doc['content'][:500])
    print("-" * 80)

    # 空のコンテンツをチェック
    if not doc['content'].strip():
        print("⚠️ 警告: このファイルは空です！")

print("\n" + "=" * 80)
print("デバッグ完了")
