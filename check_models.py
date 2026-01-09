"""
利用可能なGeminiモデルを確認するスクリプト
"""
import google.generativeai as genai
from dotenv import load_dotenv
import os

# 環境変数の読み込み
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("エラー: GEMINI_API_KEYが設定されていません")
    exit(1)

# API設定
genai.configure(api_key=api_key)

print("利用可能なモデル一覧:\n")
print("-" * 80)

try:
    models = genai.list_models()

    for model in models:
        # generateContentをサポートするモデルのみ表示
        if 'generateContent' in model.supported_generation_methods:
            print(f"モデル名: {model.name}")
            print(f"表示名: {model.display_name}")
            print(f"説明: {model.description}")
            print("-" * 80)
except Exception as e:
    print(f"エラー: {e}")
