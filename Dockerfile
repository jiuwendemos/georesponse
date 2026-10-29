FROM node:22-alpine AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /srv/georesponse
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY georesponse ./georesponse
COPY pyproject.toml README.md ./
COPY --from=web /app/web/dist ./web/dist
COPY docs ./docs
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uvicorn", "georesponse.api:app", "--host", "0.0.0.0", "--port", "8000"]
