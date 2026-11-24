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
- Admin overview endpoint and admin panel in the account view, including admin plan overrides. A manual plan change marks the team subscription as `MANUAL` so reconciliation never downgrades it.
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
- Automatic PayPal Subscriptions. The plan tab renders the official PayPal JS SDK button (`vault=true&intent=subscription&currency=USD`); `createSubscription` sends the catalog `plan_id` plus the authenticated team as `custom_id`.
- Live catalog: product `PROD-0VJ49900FS465031M`; Creator `P-9JK82163JY201791BNMCPAMA` at $5.00/month; Studio `P-73R478908B315820HNMCPAMI` at $10.00/month.
- On `onApprove`, the browser posts the subscription ID to `POST /api/billing/paypal/activate`. The server verifies the subscription through PayPal, checks that `custom_id` matches the session team and that `plan_id` matches the catalog, then activates the plan immediately. No admin action and no webhook are needed for the first activation.
- `POST /api/billing/paypal/cancel` cancels at PayPal; the paid plan stays active until `renews_at`. `EXPIRED`, `SUSPENDED` and failed payments downgrade immediately. `BILLING.SUBSCRIPTION.ACTIVATED`, `UPDATED`, `CANCELLED`, `EXPIRED`, `SUSPENDED`, `BILLING.SUBSCRIPTION.PAYMENT.FAILED` and `PAYMENT.SALE.COMPLETED` are handled at `POST /api/billing/paypal/webhook`.
- `GET /api/public/config` exposes only public values: `configured`, live/sandbox mode, client ID, currency and the two plan IDs. The client secret stays server-side in `engine/.env` and is never committed.
- `GET /api/account` returns `paypal` config and the current `subscription`. `GET /api/admin/teams` lists teams with owner, plan and monthly usage; `POST /api/admin/plan` sets the plan and marks the team subscription `MANUAL`. `POST /api/admin/paypal/setup` returns the catalog and registers the webhook when `PAYPAL_PUBLIC_URL` is configured.
- `PAYPAL_ME_URL` remains a legacy runtime value but the landing page and plan tab no longer use it. Stripe Checkout code is retained server-side as a legacy alternative but no plan button uses it.

## 8. Environment variables to configure
- CLIPFORGE_CLOUD_DIR, CLIPFORGE_PUBLIC_ORIGIN
- PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET (server-side only; never commit the secret)
- PAYPAL_MODE=live (or `sandbox` for testing)
- PAYPAL_PRODUCT_ID, PAYPAL_CREATOR_PLAN_ID, PAYPAL_STUDIO_PLAN_ID
- PAYPAL_PUBLIC_URL (public HTTPS origin used to register the webhook)
- PAYPAL_WEBHOOK_ID (production webhook verification; register it with `POST /api/admin/paypal/setup`)
- PAYPAL_WEBHOOK_INSECURE=1 (local unsigned-webhook testing only; never set in production)
- PAYPAL_ME_URL (legacy, no longer used by the UI)
- Optional legacy Stripe: STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_CREATOR, STRIPE_PRICE_STUDIO
- ADMIN_EMAILS (comma-separated)
- FFMPEG_BIN and FFPROBE_BIN for the engine workers.
- YTDLP_COOKIES (path to a Netscape cookie file) or YTDLP_COOKIES_FROM_BROWSER (for example `chrome:default`) when YouTube requires a bot-check/login. Cloud workers do not read browser cookies automatically.
- Standard engine vars (WHISPER_MODEL, WHISPER_DEVICE, etc.).

## 9. Tests and packaging
- Engine test suite: 306 passed.
- Web build: tsc + vite successful; main bundle 237.68 kB (gzip 61.48 kB), Virocut engine lazy chunk 598.11 kB (gzip 155.76 kB), CSS 78.99 kB (gzip 14.06 kB).
- PayPal live credentials verified against `https://api-m.paypal.com` (sandbox returns `401 invalid_client`). Live product and both monthly plans created through the API.
- `/api/public/config` returns `configured: true`, the live client ID and plan IDs `P-9JK...` / `P-73R...`. `POST /api/admin/paypal/setup` returns the same catalog.
- Activation guard verified: a fake subscription ID is rejected by PayPal with HTTP 502 (`Request is not well-formed...`), so the plan cannot be activated without a real PayPal subscription.
- Webhook handling verified locally: `ACTIVATED` → Creator, `CANCELLED` → Creator until `2026-12-23`, `EXPIRED` → Starter. An admin plan reset to Studio marks the subscription `MANUAL`; repeated `/api/account` reads stay Studio.
- Account plan tab verified in headless Chrome: the PayPal JS SDK loads with the live client ID, three PayPal button iframes render for Creator, the copy says "Pago automático con PayPal", and no `paypal.me` or manual-activation text remains.
- Virocut editor verified end to end in headless Chrome: edited a 30 s source, rendered and saved a 12.011 s clip at 1080×1920, 30 fps, H.264 + AAC (48 kHz stereo), 6,009,144 bytes; the clip API reports `browser_engine: true` and the download link serves the same file.
- Link job creation verified through the cloud proxy: the URL is validated, a job is queued and the engine starts the remote download. Live YouTube/Kick/Twitch downloads depend on the host's DNS and platform access.
- Desktop installer rebuilt after the PayPal/admin UI and verified end to end:
  - Installer: `desktop/dist/installer/Clipwise-Setup-1.3.0.exe`
  - Size: 331,409,017 bytes
  - SHA256: `62B55AC2D803ED4846E7EFBF7A02BEAE24F3447FAD572899D5A8929E83DD773C`
  - App bundle: `desktop/dist/Clipwise-1.3.0/Clipwise/Clipwise.exe`
  - `tools/e2e/verify_bundle.py` confirms 13 packaged backend modules and all frontend assets match the source build.
  - Packaged `--self-test` returned 0 with health OK: FFmpeg 9.0.2, ffprobe, Whisper tiny, URL extractors, 9 subtitle styles and all layout modes present.
  - Silent install and silent uninstall previously returned 0; the rebuilt bundle was re-tested with `--self-test` and `verify_bundle.py`.
  - The local data directory stays `%LOCALAPPDATA%\ClipForge` so existing libraries survive the rebrand.

## 10. Pending issues
- No public HTTPS domain is configured yet, so no Clipwise webhook has been registered and `PAYPAL_WEBHOOK_ID` is empty. First activation works through `onApprove`; renewals, cancellations, suspensions and failed payments need the webhook. Set `PAYPAL_PUBLIC_URL` and call `POST /api/admin/paypal/setup` once the domain is live.
- A real $5/$10 PayPal checkout has not been completed because it needs a buyer PayPal account. The live catalog and SDK are verified; the first real purchase must be watched end to end.
- Failed-job credit reconciliation beyond immediate request failure not fully automated.
- Full i18n (ES/EN) selector not implemented; landing and app copy are Spanish-first.
- Watermark enforcement and export resolution are not yet gated by plan in the render pipeline.
- Legal trademark/domain verification pending.
- `PAYPAL_ME_URL` remains in legacy config but is not used by the UI; remove it once old deployments are migrated.

## 11. Deployment 24/7 (gratis)
- GitHub repository: `https://github.com/leowyseduardo-dev/clipwise`.
- `Dockerfile` builds the Vite frontend and installs the hosted Python requirements with FFmpeg; one container serves the web UI, the cloud API and the per-workspace FFmpeg/Whisper engines.
- `docker-compose.yml` keeps accounts, workspaces and Whisper models in the `clipwise_data` volume; `Caddyfile` terminates HTTPS automatically.
- `.env.production.example` documents `APP_DOMAIN`, `CLIPFORGE_PUBLIC_ORIGIN`, `ADMIN_EMAILS`, the PayPal subscription values (`PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_MODE`, product/plan IDs, `PAYPAL_PUBLIC_URL`, `PAYPAL_WEBHOOK_ID`), Whisper settings and the optional admin seed.
- PayPal renewals and cancellations need a public HTTPS origin. After the domain is live, set `PAYPAL_PUBLIC_URL=https://<domain>`, restart and call `POST /api/admin/paypal/setup` to register `https://<domain>/api/billing/paypal/webhook`; store the returned `webhook_id` as `PAYPAL_WEBHOOK_ID`.
- `engine/cloud/seed.py` creates the admin account and sets its team to Studio on first boot only when `CLIPFORGE_SEED_ADMIN=1`; verified idempotent (306 engine tests still pass).
- `DEPLOY.md` contains the Oracle Always Free VPS steps, Caddy/HTTPS setup, Groq LLM option, cookies for YouTube, backups and updates.
- Vercel + Turso + R2 cannot render clips on the free plan (10 s function timeout, no persistent filesystem); the VPS keeps clip generation on the public website with maximum quality.
- Virocut-style browser renderer integrated into the clip modal: `mediabunny@1.66.3` + WebCodecs + `<canvas>` 2D (the same approach used by Virocut.com). The editor exposes 9:16/1:1/16:9 templates, split/spotlight/blur/black layouts, subtitle styles, hook text, watermark, focus framing and caption timing. `POST /api/clips/{id}/browser-render` saves the MP4 back into the clip and marks `overlay.render_options.browser_engine`.
- Headless Chrome verification: the editor loaded a 30 s source, applied a split layout and neon captions, rendered 1080×1920 at 30 fps (H.264 4 Mbps + AAC 48 kHz stereo), and saved a 12.011 s MP4 (6,009,144 bytes) into the clip. The clip API and download link returned the same 1080×1920 file.
- The standalone `/browser.html` beta page remains for uploads without a Clipwise project. Limit of both browser paths: they render media already available in the browser; YouTube/Kick/Twitch link ingestion still uses the server-side FFmpeg/Whisper pipeline. The desktop app keeps that path for links.
- Docker is not installed on the local build machine, so the image was not built here; the deployment files and the seed were verified, the image must be built on the VPS with `docker compose up -d --build`.
- `DEPLOY-GCP.md` documents the same stack on a Google Cloud e2-micro always-free VM (1 GB RAM + swap, US regions only, 1 GB/month egress) as an alternative to Oracle. Cloud Run, Modal, Render/Koyeb and Vercel+Turso+R2 are compared in its final table; only a real VM gives 24/7 full FFmpeg/Whisper rendering for free.
