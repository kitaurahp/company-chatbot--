#!/bin/bash
# 社内規定チャットボット起動スクリプト（Mac用）

# スクリプトのあるディレクトリに移動
cd "$(dirname "$0")"

echo "=========================================="
echo "  社内規定チャットボットを起動しています..."
echo "=========================================="

# 仮想環境があれば有効化
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Streamlitを起動（自動でブラウザを開く）
python3 -m streamlit run app.py --server.headless false

# エラー時は画面を閉じない
if [ $? -ne 0 ]; then
    echo ""
    echo "エラーが発生しました。Enterキーを押して終了してください。"
    read
fi
