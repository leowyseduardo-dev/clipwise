# Clipwise SaaS Transformation Report

## 1. New commercial name
Selected brand: **Clipwise** (proposed alongside Cutflow and Viro). Trademark/domain availability was not verified; confirm before public launch.

## 2. Visual changes
- Tailwind theme switched from dark purple to light theme with blue (#2563eb) accent.
- Global CSS variables updated; body background light with subtle blue gradients.
- Brand strings updated across web, engine, website, docs.

## 3. Implemented features
- Link-based clipping restored as the default flow: paste a YouTube, Kick or Twitch video/VOD link and the engine downloads it, detects highlights, cuts, reframes and subtitles the clips automatically. Direct upload remains available as a secondary tab.
- Three subscription plans: Starter (free), Creator ($5/mo, recommended), Studio ($10/mo).
- Daily limit (2 clips/day) for Starter plus monthly limits.
- Admin overview endpoint and admin panel in the account view, including manual plan activation for PayPal payments.
- Commercial landing page with hero, how-it-works, features, pricing, FAQ, footer.
- SEO meta tags, responsive layout.

## 4. Authentication system
- Existing hosted auth (FastAPI + argon2 + SQLite sessions, HTTP-only cookies) retained and extended with admin flag.

## 5. Database changes
- Cloud SQLite schema unchanged; plans updated in accounts.PLANS.
- Daily usage derived from charges.created timestamps.

## 6. Plans system
- Starter: free, 20 clips/month, 2/day, 1 project, 1 seat, 720p + watermark.
- Creator: $5/month, 120 clips/month, 3 projects, 2 seats, 1080p, no watermark. Recommended tier.
- Studio: $10/month, 400 clips/month, 8 projects, 5 seats, max render priority.
- Legacy teams stored as "Free" are migrated to "Starter" on startup.

## 7. Payments integration
- Manual PayPal.me flow: set `PAYPAL_ME_URL` and the landing/plan tab render "Pagar $X con PayPal" buttons. After the payment arrives, an admin activates the plan from **Admin → Activar plan manual**.
- `GET /api/public/config` exposes only the PayPal.me base URL. `GET /api/admin/teams` lists teams with owner, plan and monthly usage; `POST /api/admin/plan` sets the plan.
- Stripe Checkout + webhooks retained as an automatic alternative. When `PAYPAL_ME_URL` is set and the Stripe keys are absent, the billing endpoint returns 409 with manual-payment instructions. Price env vars: `STRIPE_PRICE_CREATOR`, `STRIPE_PRICE_STUDIO`.

## 8. Environment variables to configure
- CLIPFORGE_CLOUD_DIR, CLIPFORGE_PUBLIC_ORIGIN
- PAYPAL_ME_URL (manual PayPal; for example `https://paypal.me/tuusuario`)
- Optional automatic billing: STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
- Optional Stripe prices: STRIPE_PRICE_CREATOR, STRIPE_PRICE_STUDIO
- ADMIN_EMAILS (comma-separated)
- FFMPEG_BIN and FFPROBE_BIN for the engine workers.
- YTDLP_COOKIES (path to a Netscape cookie file) or YTDLP_COOKIES_FROM_BROWSER (for example `chrome:default`) when YouTube requires a bot-check/login. Cloud workers do not read browser cookies automatically.
- Standard engine vars (WHISPER_MODEL, WHISPER_DEVICE, etc.).

## 9. Tests and packaging
- Engine test suite: 306 passed.
- Web build: tsc + vite successful; hosted assets `index-BcIxAsSI.js` and `index-DV3eVOPk.css`.
- Manual PayPal flow verified end to end in the browser with the real link `https://paypal.me/TenderMarginAI`: public config exposes it, Starter account sees `Pagar $5/$10 con PayPal` pointing to `/5` and `/10`, and the admin panel changed the team Starter → Studio via **Admin → Activar plan manual**.
- Landing verified in both states: with `PAYPAL_ME_URL` it shows the PayPal CTAs; without it, the pricing buttons fall back to `Elegir Creator` / `Elegir Studio` and the footnote explains manual activation. The running server now uses the real link from `engine/.env`.
- Link job creation verified through the cloud proxy: the URL is validated, a job is queued and the engine starts the remote download. Live YouTube/Kick/Twitch downloads depend on the host's DNS and platform access.
- Desktop installer rebuilt after the PayPal/admin UI and verified end to end:
  - Installer: `desktop/dist/installer/Clipwise-Setup-1.3.0.exe`
  - Size: 331,246,233 bytes
  - SHA256: `E3E0498BC09C97353542AAC25D904ACD99FE4935E5C34A2953F17F7B4CFBC4C4`
  - App bundle: `desktop/dist/Clipwise-1.3.0/Clipwise/Clipwise.exe`
  - `tools/e2e/verify_bundle.py` confirms 13 packaged backend modules and all frontend assets match the source build.
  - Packaged `--self-test` returned 0 with health OK: FFmpeg 9.0.2, ffprobe, Whisper tiny, URL extractors, 9 subtitle styles and all layout modes present.
  - Silent install and silent uninstall previously returned 0; the rebuilt bundle was re-tested with `--self-test` and `verify_bundle.py`.
  - The local data directory stays `%LOCALAPPDATA%\ClipForge` so existing libraries survive the rebrand.

## 10. Pending issues
- `PAYPAL_ME_URL` configured and verified with `https://paypal.me/TenderMarginAI`. Payments are checked manually in PayPal and the plan is activated from **Admin → Activar plan manual**.
- Failed-job credit reconciliation beyond immediate request failure not fully automated.
- Full i18n (ES/EN) selector not implemented; landing and app copy are Spanish-first.
- Watermark enforcement and export resolution are not yet gated by plan in the render pipeline.
- Legal trademark/domain verification pending.
- Public HTTPS domain is only required for automatic Stripe webhooks; manual PayPal needs no webhook or public domain.

## 11. Deployment 24/7 (gratis)
- GitHub repository: `https://github.com/leowyseduardo-dev/clipwise`.
- `Dockerfile` builds the Vite frontend and installs the hosted Python requirements with FFmpeg; one container serves the web UI, the cloud API and the per-workspace FFmpeg/Whisper engines.
- `docker-compose.yml` keeps accounts, workspaces and Whisper models in the `clipwise_data` volume; `Caddyfile` terminates HTTPS automatically.
- `.env.production.example` documents `APP_DOMAIN`, `CLIPFORGE_PUBLIC_ORIGIN`, `ADMIN_EMAILS`, `PAYPAL_ME_URL`, Whisper settings and the optional admin seed.
- `engine/cloud/seed.py` creates the admin account and sets its team to Studio on first boot only when `CLIPFORGE_SEED_ADMIN=1`; verified idempotent (306 engine tests still pass).
- `DEPLOY.md` contains the Oracle Always Free VPS steps, Caddy/HTTPS setup, Groq LLM option, cookies for YouTube, backups and updates.
- Vercel + Turso + R2 cannot render clips on the free plan (10 s function timeout, no persistent filesystem); the VPS keeps clip generation on the public website with maximum quality.
- Prototype of a fully browser-side renderer added at `/browser.html`: `mediabunny@1.66.3` + WebCodecs + `<canvas>` 2D (the same approach used by Virocut.com). It takes an uploaded MP4, a trim range and `start|end|text` cues, bakes 9:16 reframing and captions, and returns an MP4 with no server render. Vite now builds two HTML entries; the landing footer links to the beta page.
- Headless Chrome verification: a 5-second 1280x720 test source produced a 4-second 1080x1920 MP4 with captions, no errors. The video export is 1080x1920 and the download link works.
- Limitation of the prototype: it accepts file uploads, not YouTube/Kick/Twitch links. Link ingestion needs an HLS/URL proxy plus server-side transcription (Groq/Gemini) and Turso job storage; the desktop app keeps the FFmpeg/Whisper path for links.
- Docker is not installed on the local build machine, so the image was not built here; the deployment files and the seed were verified, the image must be built on the VPS with `docker compose up -d --build`.
- `DEPLOY-GCP.md` documents the same stack on a Google Cloud e2-micro always-free VM (1 GB RAM + swap, US regions only, 1 GB/month egress) as an alternative to Oracle. Cloud Run, Modal, Render/Koyeb and Vercel+Turso+R2 are compared in its final table; only a real VM gives 24/7 full FFmpeg/Whisper rendering for free.
