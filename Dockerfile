# 実機（社内承認済みPython環境）が用意できない場合の動作確認用。
# 本番配布はrequirements.txt + start.batによるvenv運用であり、
# このDockerfileはコンテナ上でも同じ依存関係・起動手順が動くことを
# 検証するためのものであってexe化の代替ではない。
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY static/ ./static/
COPY run.py .

EXPOSE 18080

CMD ["python", "run.py"]
