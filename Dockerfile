FROM python:3.12-slim
WORKDIR /app
COPY . .
ENV HOST=0.0.0.0 \
    PORT=7860 \
    PYTHONUNBUFFERED=1
EXPOSE 7860
CMD ["python", "app.py"]
