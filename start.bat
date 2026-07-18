@echo off
chcp 65001 >nul

if not exist .venv (
    echo [INFO] .venvを作成します...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] venvの作成に失敗しました。
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat

echo [INFO] 依存パッケージを確認しています...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] 依存パッケージのインストールに失敗しました。
    echo 社内プロキシ配下の場合はHTTP_PROXY/HTTPS_PROXY環境変数の設定を確認してください。
    pause
    exit /b 1
)

python run.py
if errorlevel 1 (
    pause
    exit /b 1
)
