# NeighbourTalk

A real-time English ↔ Romanian voice translation app designed to run on a Raspberry Pi.
Hold a conversation across a language barrier: tap to speak, tap again to hear the translation spoken aloud.

## How it works

1. **Record** — tap the button and speak; tap again when done.
2. **Transcribe** — audio is sent to OpenAI Whisper (speech-to-text).
3. **Translate** — text is translated by DeepL.
4. **Speak** — the translation is read aloud via OpenAI TTS.

The direction toggle at the top switches between EN → RO and RO → EN.
API keys are held server-side and never exposed to the browser.

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3, FastAPI, Uvicorn |
| Speech-to-text | OpenAI Whisper (`whisper-1`) |
| Translation | DeepL API |
| Text-to-speech | OpenAI TTS (`tts-1`) |
| Frontend | Vanilla HTML/CSS/JS (single file, no build step) |
| Hosting | Raspberry Pi, served over LAN and/or Tailscale HTTPS |

## Requirements

- Raspberry Pi (tested on Pi 5) running Raspberry Pi OS
- Python 3.11+
- An [OpenAI API key](https://platform.openai.com/api-keys)
- A [DeepL API key](https://www.deepl.com/en/pro-api) (free tier is sufficient)

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/neighbourtalk.git
cd neighbourtalk

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
chmod 600 .env
# Edit .env and add your API keys
```

## Configuration

Copy `.env.example` to `.env` and fill in your keys:

```
OPENAI_API_KEY=sk-...
DEEPL_API_KEY=...
```

Never commit `.env` — it is listed in `.gitignore`.

## Running

### Manually (development)

```bash
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 5000
```

Open `http://<pi-ip>:5000` on any device on the same network.

### As a systemd service (production)

```bash
sudo cp neighbourtalk.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now neighbourtalk
```

Useful commands:

```bash
sudo systemctl status neighbourtalk   # check status
sudo systemctl restart neighbourtalk  # restart after changes
journalctl -u neighbourtalk -f        # live logs
```

The service starts automatically on boot and restarts on failure.

## Network access

### LAN (same WiFi)

The app listens on `0.0.0.0:5000`. Any device on the same network can reach it at:

```
http://<pi-local-ip>:5000
```

Find the Pi's local IP with `hostname -I`.

### HTTPS via Tailscale (recommended for iOS)

iOS Safari requires HTTPS for microphone access when not on `localhost`.
Tailscale Serve provides a trusted HTTPS endpoint without opening any ports.

**One-time setup:**

```bash
bash setup_tailscale.sh
```

This script will:
1. Install Tailscale if not already present
2. Authenticate your device with your Tailscale account
3. Configure Tailscale Serve to proxy HTTPS → `localhost:5000`
4. Print your personal Tailscale HTTPS URL and next steps

**Prerequisites in the Tailscale admin console** (`login.tailscale.com/admin/dns`):
- Enable **MagicDNS**
- Enable **HTTPS Certificates**

The HTTPS URL is only accessible to devices logged into your Tailscale network.

### Public access for a neighbour's device (Tailscale Funnel)

The neighbour opens a Tailscale Funnel URL in their browser — a public HTTPS link that
Tailscale tunnels directly to the Pi, with no app or account required on their end.

Key points:
- The URL is a subdomain of `ts.net` — publicly reachable but not guessable
- Traffic is TLS-encrypted end-to-end
- No ports are opened on your router; the Pi initiates the outbound tunnel
- The neighbour needs nothing installed — it is just a URL

Enable Funnel with:

```bash
sudo tailscale funnel --bg http://localhost:5000
```

The Funnel URL is the same Tailscale hostname used for Serve (`https://<your-pi>.ts.net`),
but now reachable from any browser without Tailscale installed.

To review current Serve/Funnel configuration at any time:

```bash
sudo tailscale serve status
```

## Project structure

```
neighbourtalk/
├── main.py                  # FastAPI app — transcription, translation, TTS
├── requirements.txt
├── .env.example             # Template for API keys (safe to commit)
├── .env                     # Your actual keys (never committed)
├── .gitignore
├── neighbourtalk.service    # systemd unit file
├── setup_tailscale.sh       # One-time Tailscale HTTPS setup script
└── static/
    └── index.html           # Full single-page frontend
```

## API

`POST /api/translate`

| Field | Type | Description |
|---|---|---|
| `audio` | file | Audio recording (webm / mp4 / ogg / wav / mp3) |
| `direction` | string | `"en-ro"` or `"ro-en"` |

Response:

```json
{
  "original":   "Hello, how are you?",
  "translated": "Bună ziua, cum ești?",
  "audio_b64":  "<base64-encoded MP3>"
}
```

`GET /health` — returns `{"status": "ok"}` (used for connectivity check).
