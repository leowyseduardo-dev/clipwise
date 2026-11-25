"""Optional SMTP delivery for password resets.

The cloud server stays functional without SMTP, but /api/account/forgot
returns 503 until CLIPWISE_SMTP_* is configured. An admin can generate a
one-use reset link from the Admin tab instead. Set CLIPWISE_DEV_RESET=1
only on a local development machine to write reset links to the log.
"""

from __future__ import annotations

import html
import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger("clipwise.mail")


def configured() -> bool:
    return bool(os.getenv("CLIPWISE_SMTP_HOST", "").strip())


def send_reset(to: str, link: str) -> bool:
    if not configured():
        if os.getenv("CLIPWISE_DEV_RESET", "").strip() == "1":
            log.warning("Password reset link for %s: %s", to, link)
        else:
            log.warning(
                "Password reset requested for %s but CLIPWISE_SMTP_HOST is not configured.",
                to,
            )
        return False

    host = os.environ["CLIPWISE_SMTP_HOST"].strip()
    port = int(os.getenv("CLIPWISE_SMTP_PORT", "587"))
    user = os.getenv("CLIPWISE_SMTP_USER", "").strip()
    password = os.getenv("CLIPWISE_SMTP_PASSWORD", "")
    sender = os.getenv("CLIPWISE_SMTP_FROM", "").strip() or user or "no-reply@localhost"

    message = EmailMessage()
    message["Subject"] = "Restablece tu contraseña de Clipwise"
    message["From"] = sender
    message["To"] = to
    message.set_content(
        "Recibimos una solicitud para restablecer tu contraseña de Clipwise.\n\n"
        f"Abre este enlace para elegir una nueva contraseña (caduca en 1 hora):\n{link}\n\n"
        "Si no solicitaste este cambio, ignora este mensaje."
    )
    message.add_alternative(
        f"""<!doctype html>
<html lang="es"><body style="margin:0;background:#f6f8fc;font-family:Arial,sans-serif;color:#0f172a">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="padding:32px 16px">
      <table role="presentation" width="100%" style="max-width:520px;background:#fff;border:1px solid #e2e8f0;border-radius:16px">
        <tr><td style="padding:28px">
          <p style="margin:0 0 6px;font-size:18px;font-weight:700">Clipwise<span style="color:#2563eb">.</span></p>
          <h1 style="margin:16px 0 8px;font-size:22px;line-height:1.25">Restablece tu contraseña</h1>
          <p style="margin:0 0 18px;font-size:14px;line-height:1.6;color:#475569">
            Recibimos una solicitud para cambiar la contraseña de tu cuenta. El enlace caduca en 1 hora.
          </p>
          <p style="margin:0 0 22px">
            <a href="{html.escape(link)}" style="display:inline-block;background:#2563eb;color:#fff;text-decoration:none;font-size:14px;font-weight:600;padding:12px 20px;border-radius:10px">Elegir nueva contraseña</a>
          </p>
          <p style="margin:0;font-size:12px;line-height:1.6;color:#94a3b8">
            Si no solicitaste este cambio, ignora este mensaje. Tu contraseña actual sigue siendo válida.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>""",
        subtype="html",
    )

    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.ehlo()
            if os.getenv("CLIPWISE_SMTP_TLS", "1") != "0":
                smtp.starttls()
                smtp.ehlo()
            if user:
                smtp.login(user, password)
            smtp.send_message(message)
        return True
    except Exception:
        log.exception("Could not send password reset email to %s", to)
        return False
