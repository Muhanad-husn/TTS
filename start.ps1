# Start the TTS server (if not already running) and launch read_aloud
docker compose up -d
python read_aloud.py @args
