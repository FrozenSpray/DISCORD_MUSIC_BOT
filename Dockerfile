FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV DISCORD_DEBUG=True

RUN apt-get update && apt-get install -y ffmpeg

WORKDIR /app
COPY . /app

RUN pip install -r requirements.txt

CMD ["python", "-u", "musicbot.py"]