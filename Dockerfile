FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 TRUST_PROXY=1 PORT=8080
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8080
CMD ["sh", "-c", "gunicorn 'app.server:create_app()' --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 60"]
