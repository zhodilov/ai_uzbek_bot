# AI Telegram Bot (OpenRouter)

This repository contains a Telegram bot that uses OpenRouter for AI chat.
It also supports converting images to PDF, extracting text from PDFs, image stylization placeholder, and admin contact.

## Files
- `main.py` - main bot code
- `requirements.txt` - Python dependencies
- `Procfile` - for Render/Railway deployment
- `.env.example` - environment variable template

## Setup (local)
1. Copy `.env.example` to `.env` and fill values:
```
TELEGRAM_BOT_TOKEN=...
OPENROUTER_API_KEY=...
```
2. Create virtual env and install:
```
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
3. Run:
```
python main.py
```

## Deploying
- For Render or Railway, create a new service, connect your GitHub repo, and set environment variables in the dashboard.
- Use the provided `Procfile`.

## Notes
- The image stylization function is a placeholder. Integrate your preferred image model / service in `stylize_image_bytes`.
- Keep tokens secret. Do not commit `.env` to public repos.
