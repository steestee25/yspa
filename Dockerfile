FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY yspa yspa

ENV YSPA_DB_PATH=/data/yspa.db PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8000

# Di default la pagina web; il servizio di raccolta usa lo stesso file con "python -m yspa run".
CMD ["python", "-m", "uvicorn", "yspa.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
