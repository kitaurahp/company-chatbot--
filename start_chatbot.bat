@echo off
chcp 65001 > nul
REM 社内規定チャットボット起動スクリプト（Windows用）

cd /d "%~dp0"

echo ==========================================
echo   社内規定チャットボットを起動しています...
echo ==========================================

REM 仮想環境があれば有効化
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM Streamlitを起動（自動でブラウザを開く）
python -m streamlit run app.py --server.headless false

REM エラー時は画面を閉じない
if errorlevel 1 (
    echo.
    echo エラーが発生しました。何かキーを押して終了してください。
    pause > nul
)
