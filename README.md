# Touch Grass Planner v2

Local-first outdoor companion. Open pieces: Gemma via Ollama (plans), BirdNET (bird calls), Open-Meteo (optional live weather).

## Run locally (step by step)
1. Install Python 3.9+ and Ollama (https://ollama.com).
2. `ollama pull gemma3:4b` (on a weak laptop use `gemma3:1b` and run with `TG_MODEL=gemma3:1b`).
3. Optional bird ID: `pip install birdnet-analyzer` (large download, needs TensorFlow).
4. `python3 server.py`, then open http://localhost:8000
5. Pick your climate, press "Use my location" for weather, make a plan, press Start, go outside.

## Deploy on Render
Push this folder to GitHub. Render > New > Blueprint > pick the repo. Set `OLLAMA_URL` to a remote Ollama.
Bird ID needs build arg `WITH_BIRDS=1` and more RAM than the free tier has.

## Deploy on DigitalOcean
On a Droplet (or the Ollama 1-Click GPU image): `ollama pull gemma3:4b`, run `OLLAMA_HOST=0.0.0.0 ollama serve`, firewall port 11434 to the app only.
Then: `docker build -t tgp . && docker run -p 80:8000 -e OLLAMA_URL=http://<ollama-ip>:11434 tgp`
Public deploys share one journal stored in /tmp (lost on restart): treat them as a demo.

## Why open matters
Works with no signal, data stays on your machine, model swappable with one env var, zero API cost, regional crop table is plain editable data.
