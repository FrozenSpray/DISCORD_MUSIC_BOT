FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    libssl-dev \
    libffi-dev \
    build-essential \
    ca-certificates \
    && apt-get clean

WORKDIR /app
COPY . /app

RUN pip install -r requirements.txt

CMD ["python", "musicbot.py"]