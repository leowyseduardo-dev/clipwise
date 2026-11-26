# Clipwise SaaS Transformation Report

## 1. New commercial name
Selected brand: **Clipwise** (proposed alongside Cutflow and Viro). Trademark/domain availability was not verified; confirm before public launch.

## 2. Visual changes
- Tailwind theme switched from dark purple to light theme with blue (#2563eb) accent.
- Global CSS variables updated; body background light with subtle blue gradients.
- Brand strings updated across web, engine, website, docs.

## 3. Implemented features
- Link-based clipping restored as the default flow: paste a YouTube, Kick or Twitch video/VOD link and the engine downloads it, detects highlights, cuts, reframes and subtitles the clips automatically. Direct upload remains available as a secondary tab.
- Three subscription plans: Starter (free), Creator ($5/mo, recommended), Studio ($10/mo). All plans export 1080p without a forced watermark; paid plans differ by clip quota, simultaneous projects and team seats.
- Daily limit (2 clips/day) for Starter plus monthly limits.
- Admin overview endpoint and admin panel in the account view, including admin plan overrides. A manual plan change marks the team subscription as `MANUAL` so reconciliation never downgrades it.
- Public landing page before authentication, with hero, how-it-works, features, pricing, FAQ and footer.
- Spanish legal pages at `/terminos.html` and `/privacidad.html`; legacy `/terms-en.html` and `/privacy-en.html` redirect to them.
- Admin-generated password reset links (`POST /api/admin/reset-link`) for the no-SMTP deployment; the browser reset form accepts the link even when another session is active.
- SEO meta tags and responsive layout.

## 4. Authentication system
- Existing hosted auth (FastAPI + argon2 + SQLite sessions, HTTP-only cookies) retained and extended with admin flag.

## 5. Database changes
- Cloud SQLite schema unchanged; plans updated in accounts.PLANS.
- Daily usage derived from charges.created timestamps.

## 6. Plans system
- Starter: free, 20 clips/month, 2/day, 1 project, 1 seat, 1080p without a forced watermark.
- Creator: $5/month, 120 clips/month, 3 projects, 2 seats, 1080p without a forced watermark. Recommended tier.
- Studio: $10/month, 400 clips/month, 8 projects, 5 seats, 1080p without a forced watermark.
- Plan names are normalised through `VALID_PLANS` / `normalize_plan()`; legacy teams stored as "Free" are migrated to "Starter" on startup and at every account read.
- Registration inserts `Starter` explicitly and no longer raises `KeyError` for the old `Free` value.

## 7. Payments integration
- Automatic PayPal Subscriptions. The plan tab renders the official PayPal JS SDK button (`vault=true&intent=subscription&currency=USD`); `createSubscription` sends the catalog `plan_id`, the authenticated team as `custom_id`, and `application_context` (`NO_SHIPPING`, `SUBSCRIBE_NOW`). Landing paid-plan CTAs carry the plan intent; after signup or login the account drawer opens directly on the Plan tab.
- Live catalog: product `PROD-0VJ49900FS465031M`; Creator `P-9JK82163JY201791BNMCPAMA` at $5.00/month; Studio `P-73R478908B315820HNMCPAMI` at $10.00/month.
- On `onApprove`, the browser posts the subscription ID to `POST /api/billing/paypal/activate`. The server verifies the subscription through PayPal, checks that `custom_id` matches the session team and that `plan_id` matches the catalog, explicitly activates `APPROVED` subscriptions, and only grants access once the subscription is `ACTIVE`. No admin action and no webhook are needed for the first activation.
- `POST /api/billing/paypal/cancel` confirms cancellation at PayPal before changing local state; a PayPal failure no longer reports a false cancellation. The paid plan stays active until `renews_at`. `EXPIRED` and `SUSPENDED` downgrade; `PAYMENT_FAILED` keeps access while PayPal retries. Webhooks for `ACTIVATED`, `UPDATED`, `CANCELLED`, `EXPIRED`, `SUSPENDED`, `PAYMENT.FAILED` and `PAYMENT.SALE.COMPLETED` are handled at `POST /api/billing/paypal/webhook`; negative events require an existing local subscription so an arbitrary `custom_id` cannot remove a team's paid plan.
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
- Engine test suite: 312 passed. New PayPal tests cover direct activation, `APPROVED`→`ACTIVE`, strict cancellation failure, webhook-first activation, protection against unauthorized downgrades and naive renewal timestamps.
- Web build after the final audit: `npm run build` (tsc + vite) successful; main bundle 240.44 kB, Virocut engine lazy chunk 598.11 kB, CSS 79.60 kB. The Vite size warning is the expected 598 kB Virocut engine chunk.
- PayPal live credentials verified against `https://api-m.paypal.com` (sandbox returns `401 invalid_client`). Live product and both monthly plans created through the API.
- `/api/public/config` returns `configured: true`, the live client ID and plan IDs `P-9JK...` / `P-73R...`. `POST /api/admin/paypal/setup` returns the same catalog.
- Activation guard verified: a fake subscription ID is rejected by PayPal with HTTP 502 (`Request is not well-formed...`), so the plan cannot be activated without a real PayPal subscription.
- Webhook handling verified locally: `ACTIVATED` → Creator, `CANCELLED` → Creator until `2026-12-23`, `EXPIRED` → Starter. An admin plan reset to Studio marks the subscription `MANUAL`; repeated `/api/account` reads stay Studio.
- Public HTTPS live at `https://clipwise.tail7dfb82.ts.net` through Tailscale Funnel → `http://127.0.0.1:8000`. Verified from the public origin: landing `200`, `/api/public/config` `200`, admin login `200`, `/api/account` `200` (owner, Studio), `/api/admin/overview` `200`.
- Public browser pass after the Tailscale cutover: landing rendered, admin session survived a server restart, Plan tab showed Starter/Creator/Studio and the live PayPal JS SDK rendered the yellow Subscribe button plus the card button.
- PayPal webhook registered and stored as `2EJ44015Y0955270F` in `paypal_catalog.json`; the public webhook URL is `https://clipwise.tail7dfb82.ts.net/api/billing/paypal/webhook`.
- Malformed scanner paths that Windows rejects as filenames now return `404` instead of `500` (`SafeStaticFiles` in `engine/cloud/main.py`).
- Public host bootstrap: `%LOCALAPPDATA%\Clipwise\start-cloud.ps1` starts uvicorn with the public origin and restarts it every 5 s if it exits. A Startup-folder shortcut runs it at user logon. AC standby and hibernate timeouts are `0`.
- Launcher failover verified: killed the uvicorn process, the detached launcher started a new one within 10 s, and the public root returned `200` again.
- Account plan tab verified in headless Chrome: the PayPal JS SDK loads with the live client ID, three PayPal button iframes render for Creator, the copy says "Pago automático con PayPal", and no `paypal.me` or manual-activation text remains.
- Virocut editor verified end to end in headless Chrome: edited a 30 s source, rendered and saved a 12.011 s clip at 1080×1920, 30 fps, H.264 + AAC (48 kHz stereo), 6,009,144 bytes; the clip API reports `browser_engine: true` and the download link serves the same file.
- Final public-browser audit (2026-11-25):
  - Registration form rejects submission without accepting the terms, then creates a `Starter` account and logs in. Login, logout and the account drawer were exercised in the same browser.
  - Admin reset-link form generated a valid `?reset=` URL; the reset form appeared even with an admin session active, accepted a new password, and the new password logged in successfully.
  - Forgot-password without SMTP returns the honest `503` copy: recovery by email is not configured and points to support.
  - Plan tab: Starter, Creator and Studio cards match the plan matrix; the manual Studio plan now offers the live PayPal subscription button instead of a dead “suscríbete desde aquí” sentence. The Starter card no longer tells a manual-plan account to cancel a subscription it does not have. Creator/Studio PayPal iframe buttons render from the official SDK.
  - Landing: `/terminos.html` and `/privacidad.html` links resolve; `/terms-en.html` redirects to `/terminos.html`; copy says 1080p without a forced watermark and no longer claims 720p, watermarks or “máxima prioridad”.
  - Job/editor: uploaded a 240,724-byte MP4 through the browser, processed job `0042be74001d439987a2180a4f67bdc4`, opened clip `0042be74008df520c63857` in the Virocut editor, rendered 1080×1920 H.264+AAC in the browser, and saved it back to the clip with `browser_engine: true`. No console errors.
  - Purchase-path audit (2026-11-26): clicked "Elegir Creator" on the public landing, signed in from the auth screen, and confirmed the account drawer opened on the Plan tab with both live PayPal iframes rendered; normal account opening still defaults to Resumen.
  - Windows download added to the landing: header link, hero link, dedicated "Clipwise también vive en tu escritorio" section, FAQ entry and footer link all point to `/downloads/Clipwise-Setup-1.3.0.exe`. The 331,459,833-byte installer is copied from `desktop/dist/installer/` into `web/public/downloads/` before `npm run build`; the binary is gitignored and `web/public/downloads/README.md` documents the step. A dedicated GET route returns it with `Content-Disposition: attachment`; public GET returned `200`, range request `206`, SHA256 `541713363905D75FBB3156A676F5DB4093C39D5272E4CC6839AD60AEE5DF12D1`. The Windows section explains that the browser downloads the `.exe` and that SmartScreen requires **Más información → Ejecutar de todos modos**. The desktop bundle excludes `web/dist/downloads/` so the installer never nests a copy of itself.
  - Portable app audit (2026-11-26): removed the "Robar de TikTok" URL-grab section (nav, view, panel, API clients and engine endpoints). Added local account support in `engine/app/desktop_accounts.py` and desktop endpoints for login, register, logout, reset, member/team management, admin overview/teams/plan/suspend/reset-link and a PayPal-unavailable stub. The seeded owner `LeowysGarcia@gmail.com` / `Leowys123` is stored as an Argon2 hash in `%LOCALAPPDATA%\ClipForge\accounts.sqlite3`, auto-signs in on first launch, and is Studio/owner/admin. Logout shows the login screen; PayPal subscriptions stay web-only. Verified in a local browser: owner auto-login, Studio header chip, account drawer with Resumen/Equipo/Plan/Admin, plan cards and admin overview. `GET /api/tiktok/grabs` now returns `404`.
  - Test accounts and workspaces were removed; the database now contains only `Leowysgarcia@gmail.com` (Studio, owner) and `leowyseduardo@gmail.com` (Starter).
- Fixed during the audit: `Free`→`Starter` registration `KeyError`; reset-token logging (now gated by `CLIPWISE_DEV_RESET=1`); manual-paid-plan PayPal conversion; false “procesado local / en tu equipo / sin subir audio” copy; false 720p/watermark/max-priority plan copy; cancellation copy for manual plans; file sizes below 1 MB now display as KB.
- Link job creation verified through the cloud proxy: the URL is validated, a job is queued and the engine starts the remote download. Live YouTube/Kick/Twitch downloads depend on the host's DNS and platform access.
- Desktop installer rebuilt after the PayPal/admin UI and verified end to end:
  - Installer: `desktop/dist/installer/Clipwise-Setup-1.3.0.exe`
  - Size: 331,459,833 bytes
  - SHA256: `541713363905D75FBB3156A676F5DB4093C39D5272E4CC6839AD60AEE5DF12D1`
  - App bundle: `desktop/dist/Clipwise-1.3.0/Clipwise/Clipwise.exe`
  - `tools/e2e/verify_bundle.py` confirms 14 packaged backend modules and all frontend assets match the source build (the public installer folder is intentionally excluded).
  - Packaged `--self-test` returned 0 with health OK: FFmpeg 9.0.2, ffprobe, Whisper tiny, URL extractors, 9 subtitle styles and all layout modes present.
  - Silent install and silent uninstall previously returned 0; the rebuilt bundle was re-tested with `--self-test` and `verify_bundle.py`.
  - The local data directory stays `%LOCALAPPDATA%\ClipForge` so existing libraries survive the rebrand.

## 10. Pending issues
- Public HTTPS and the Clipwise webhook are live through Tailscale Funnel; the webhook ID is stored in `paypal_catalog.json`. The remaining hosting gap is that the PC must stay powered on and signed in: the Startup shortcut runs at logon, not before, and Tailscale Funnel has no SLA. For boot-level startup without a login, register an elevated Scheduled Task or move to the VPS in section 11.
- No real $5/$10 checkout is being used as a test; per decision, the purchase flow was prepared for future buyers and verified with live catalog/SDK checks plus mocked server-side PayPal tests. No buyer charge or manual activation step is required.
- Without SMTP, automatic password recovery is unavailable; the admin reset-link button is the current workaround. Set the SMTP variables to enable the normal email flow.
- The accounts database lives under `%LOCALAPPDATA%\Temp\opencode\cloudtest`; a Temp cleanup would erase accounts and workspaces. Move it to a permanent data directory before treating the service as production.
- Failed-job credit reconciliation beyond immediate request failure is not fully automated.
- Full i18n (ES/EN) selector is not implemented; landing and app copy are Spanish-first.
- Legal trademark/domain verification is pending.
- `PAYPAL_ME_URL` remains in legacy config but is not used by the UI; remove it once old deployments are migrated.
- The legacy `POST /api/account/billing/{plan}` endpoint still returns `409` when `PAYPAL_ME_URL` is set. The UI no longer calls it; remove the route or the variable in a future cleanup.
- The live PayPal catalog keeps the old plan description (“máxima prioridad”) in PayPal metadata because descriptions are written at plan creation. The application copy is already corrected; recreate the catalog only if the PayPal-side description must change.
- The PayPal SDK can leave the subscribe button in a loading state if `createSubscription` never resolves; a page reload recovers. Check the browser console and network tab if a buyer reports it.

## 11. Deployment 24/7 (gratis)
- GitHub repository: `https://github.com/leowyseduardo-dev/clipwise`.
- `Dockerfile` builds the Vite frontend and installs the hosted Python requirements with FFmpeg; one container serves the web UI, the cloud API and the per-workspace FFmpeg/Whisper engines. Copy `Clipwise-Setup-1.3.0.exe` into `web/public/downloads/` before the image build so the landing download link works on the public origin.
- `docker-compose.yml` keeps accounts, workspaces and Whisper models in the `clipwise_data` volume; `Caddyfile` terminates HTTPS automatically.
- `.env.production.example` documents `APP_DOMAIN`, `CLIPFORGE_PUBLIC_ORIGIN`, `ADMIN_EMAILS`, the PayPal subscription values (`PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_MODE`, product/plan IDs, `PAYPAL_PUBLIC_URL`, `PAYPAL_WEBHOOK_ID`), Whisper settings and the optional admin seed.
- PayPal renewals and cancellations need a public HTTPS origin. After the domain is live, set `PAYPAL_PUBLIC_URL=https://<domain>`, restart and call `POST /api/admin/paypal/setup` to register `https://<domain>/api/billing/paypal/webhook`; store the returned `webhook_id` as `PAYPAL_WEBHOOK_ID`.
- `engine/cloud/seed.py` creates the admin account and sets its team to Studio on first boot only when `CLIPFORGE_SEED_ADMIN=1`; verified idempotent (312 engine tests still pass).
- `DEPLOY.md` contains the Oracle Always Free VPS steps, Caddy/HTTPS setup, Groq LLM option, cookies for YouTube, backups and updates.
- Vercel + Turso + R2 cannot render clips on the free plan (10 s function timeout, no persistent filesystem); the VPS keeps clip generation on the public website with maximum quality.
- Virocut-style browser renderer integrated into the clip modal: `mediabunny@1.66.3` + WebCodecs + `<canvas>` 2D (the same approach used by Virocut.com). The editor exposes 9:16/1:1/16:9 templates, split/spotlight/blur/black layouts, subtitle styles, hook text, watermark, focus framing and caption timing. `POST /api/clips/{id}/browser-render` saves the MP4 back into the clip and marks `overlay.render_options.browser_engine`.
- Headless Chrome verification: the editor loaded a 30 s source, applied a split layout and neon captions, rendered 1080×1920 at 30 fps (H.264 4 Mbps + AAC 48 kHz stereo), and saved a 12.011 s MP4 (6,009,144 bytes) into the clip. The clip API and download link returned the same 1080×1920 file.
- The standalone `/browser.html` beta page remains for uploads without a Clipwise project. Limit of both browser paths: they render media already available in the browser; YouTube/Kick/Twitch link ingestion still uses the server-side FFmpeg/Whisper pipeline. The desktop app keeps that path for links.
- Docker is not installed on the local build machine, so the image was not built here; the deployment files and the seed were verified, the image must be built on the VPS with `docker compose up -d --build`.
- `DEPLOY-GCP.md` documents the same stack on a Google Cloud e2-micro always-free VM (1 GB RAM + swap, US regions only, 1 GB/month egress) as an alternative to Oracle. Cloud Run, Modal, Render/Koyeb and Vercel+Turso+R2 are compared in its final table; only a real VM gives 24/7 full FFmpeg/Whisper rendering for free.

## 12. Current no-card public route (Tailscale Funnel)
- Public URL: `https://clipwise.tail7dfb82.ts.net`.
- Tailnet device: `clipwise`, Tailscale IP `100.112.33.14`, funnel `https://clipwise.tail7dfb82.ts.net` → `http://127.0.0.1:8000`.
- Start manually:
  ```powershell
  $env:CLIPFORGE_CLOUD_DIR = "$env:LOCALAPPDATA\Temp\opencode\cloudtest"
  $env:ADMIN_EMAILS = "Leowysgarcia@gmail.com"
  $env:CLIPFORGE_PUBLIC_ORIGIN = "https://clipwise.tail7dfb82.ts.net"
  $env:PAYPAL_PUBLIC_URL = "https://clipwise.tail7dfb82.ts.net"
  python -m uvicorn engine.cloud.main:app --host 127.0.0.1 --port 8000
  ```
- Funnel is persistent: `tailscale funnel status` shows the mapping; re-enable with `tailscale funnel --bg 8000` if it is ever cleared.
- Startup: `%LOCALAPPDATA%\Clipwise\start-cloud.ps1` loops uvicorn, writing launcher events to `%LOCALAPPDATA%\Clipwise\cloud.log` and server output to `cloud.out.log` / `cloud.err.log`; a shortcut in the user's Startup folder runs it at logon.
- Power: AC standby and hibernate timeouts are `0`; monitor timeout is unchanged.
- Do not expose `engine/.env`; it contains `PAYPAL_CLIENT_SECRET` and is gitignored. The public config endpoint only returns the client ID and plan IDs.
- The admin account is `Leowysgarcia@gmail.com` with plan `Studio`; the cloud DB is `%LOCALAPPDATA%\Temp\opencode\cloudtest\accounts.sqlite3`.
