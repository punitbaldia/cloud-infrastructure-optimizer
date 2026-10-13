FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN python -m pip --isolated install --no-cache-dir \
    --index-url https://pypi.org/simple --retries 10 --timeout 120 \
    -r requirements.txt \
    && python -m pip check
COPY . .
EXPOSE 8000
CMD ["sh","-c","python -m alembic upgrade head && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
