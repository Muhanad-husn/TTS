FROM ghcr.io/astral-sh/uv:debian

WORKDIR /app

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/kyutai-labs/pocket-tts.git .

COPY wyoming_tts_server.py .

RUN uv add "wyoming>=1.8,<2" zeroconf

ENV WYOMING_PORT=10201
ENV WYOMING_HOST=0.0.0.0
ENV DEFAULT_VOICE=alba
ENV MODEL_VARIANT=b6369a24
ENV PYTHONUNBUFFERED=1
ENV PAUSE_ENABLED=true
ENV PAUSE_SENTENCE=2.0
ENV PAUSE_PARAGRAPH=2.0
ENV PAUSE_SECTION=2.0
ENV PAUSE_CHAPTER=2.5

EXPOSE 10201

CMD ["uv", "run", "python", "wyoming_tts_server.py"]
