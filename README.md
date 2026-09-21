# AI YouTube Studio V4

A single Windows-friendly desktop workspace for authorized multi-account YouTube content production.

## V4 improvements
- Real Google OAuth account connection and channel discovery.
- Multi-account / multi-channel database.
- Project workspace with persistent project records.
- Configurable AI provider adapter (endpoint/API key/model).
- FFmpeg video assembly with optional SRT subtitles.
- SRT generation.
- Thumbnail brief generator with anti-misleading guidance.
- Real YouTube upload through the YouTube Data API.
- Scheduling support using YouTube `publishAt`.
- Channel analytics snapshot (views, subscribers, video count).
- Upload history and errors.
- Human approval gate before publishing.
- Safety preflight for fake engagement, evasion language, and duplicated titles.
- Voice/TTS adapter with explicit authorization gate.
- No Google password storage; OAuth tokens are stored locally in the SQLite app database.

## Important setup
1. Install Python 3.11+.
2. Install dependencies: `pip install -r requirements.txt`.
3. Create a Google Cloud OAuth **Desktop app** credential and save it as `data/client_secret.json` (or change the path in Settings).
4. Enable the YouTube Data API v3 for the Google Cloud project.
5. Run `python main.py` or `run_windows.bat`.
6. In Accounts, click **Add Google account (OAuth)**.
7. In Settings, configure an official AI/TTS provider if desired.
8. Install FFmpeg and put it on PATH for video assembly.

## YouTube publishing notes
The app uses the official YouTube Data API. Scheduled uploads are sent as private videos with `publishAt`. Google documents that `publishAt` can only be set for a private video that has never been published. Unverified API projects created after July 28, 2020 can be restricted to private uploads until the project completes Google's audit process.

## Safety scope
This project deliberately does NOT implement fake engagement, automated comment/like/subscribe spam, CAPTCHA/rate-limit bypass, restriction evasion, credential collection, or deceptive publishing. Human review remains required before upload.

## Current provider boundary
The YouTube integration is real. The AI and voice layers are provider adapters; the project does not pretend to include a third-party AI/TTS service without that service's credentials and API contract.
