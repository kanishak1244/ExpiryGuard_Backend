"""
email_service.py - DawaiFlow / ExpiryGuard Instant Email Notification Engine
Sends immediate email notifications for new pilot lead requests via SMTP (Gmail App Password) with dual-port failover.
"""

import os
import socket
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("expiryguard.email")


def get_smtp_config() -> Dict[str, Any]:
    """
    Reads SMTP configuration from environment variables with aliases and sensible defaults.
    Supports:
    - User: SMTP_USER, SMTP_USERNAME, MAIL_USERNAME
    - Pass: SMTP_PASS, SMTP_PASSWORD, MAIL_PASSWORD, GMAIL_APP_PASSWORD
    - Recipient: MY_EMAIL, ADMIN_EMAIL, ADMIN_NOTIFICATION_EMAIL, NOTIFICATION_RECIPIENT, defaulting to vashistkanishak9@gmail.com
    - Host: SMTP_HOST (default smtp.gmail.com)
    - Port: SMTP_PORT (default 587)
    """
    load_dotenv(override=True)
    host = (os.getenv("SMTP_HOST") or os.getenv("MAIL_HOST") or "smtp.gmail.com").strip().strip("'\"")
    port_str = str(os.getenv("SMTP_PORT") or os.getenv("MAIL_PORT") or "587").strip().strip("'\"")
    try:
        port = int(port_str)
    except ValueError:
        port = 587

    user = (
        os.getenv("SMTP_USER")
        or os.getenv("SMTP_USERNAME")
        or os.getenv("MAIL_USERNAME")
        or os.getenv("MY_EMAIL")
        or os.getenv("ADMIN_EMAIL")
        or "vashistkanishak9@gmail.com"
    ).strip().strip("'\"")

    password = (
        os.getenv("SMTP_PASS")
        or os.getenv("SMTP_PASSWORD")
        or os.getenv("MAIL_PASSWORD")
        or os.getenv("GMAIL_APP_PASSWORD")
        or ""
    ).strip().strip("'\"").replace(" ", "")

    recipient = (
        os.getenv("MY_EMAIL")
        or os.getenv("ADMIN_EMAIL")
        or os.getenv("ADMIN_NOTIFICATION_EMAIL")
        or os.getenv("NOTIFICATION_RECIPIENT")
        or "vashistkanishak9@gmail.com"
    ).strip().strip("'\"")

    from_name = (os.getenv("SMTP_FROM_NAME") or "DawaiFlow Pilot Alerts").strip().strip("'\"")

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "recipient": recipient,
        "from_name": from_name,
        "is_configured": bool(user and password and recipient),
    }


def format_pilot_lead_html(lead_data: Dict[str, Any]) -> str:
    """Generates a clean, professional HTML email template for new pilot request notifications."""
    import re
    pharmacy_name = lead_data.get("pharmacy_name", "N/A")
    full_name = lead_data.get("full_name", "N/A")
    phone = lead_data.get("phone", "N/A")
    city = lead_data.get("city", "N/A")
    current_billing = lead_data.get("current_billing_method", "N/A")
    bills_per_day = lead_data.get("bills_per_day", "N/A")
    biggest_problem = lead_data.get("biggest_problem") or "None specified"
    created_at = lead_data.get("created_at") or datetime.utcnow().strftime("%d %b %Y, %I:%M %p UTC")
    lead_id = lead_data.get("id", "N/A")

    # Extract email or outlets if embedded in combined details string
    email_address = lead_data.get("email")
    if not email_address and isinstance(biggest_problem, str):
        email_match = re.search(r'\[Email:\s*([^\]]+)\]', biggest_problem, re.IGNORECASE)
        if email_match:
            email_address = email_match.group(1).strip()

    email_row = ""
    if email_address:
        email_row = f"""<tr>
                  <td style="padding: 12px 16px; font-weight: 600; color: #334155; font-size: 13px; border-bottom: 1px solid #F1F5F9;">Email Address</td>
                  <td style="padding: 12px 16px; color: #1E293B; font-size: 14px; font-weight: 600; border-bottom: 1px solid #F1F5F9;">
                    <a href="mailto:{email_address}" style="color: #2563EB; text-decoration: underline;">{email_address}</a>
                  </td>
                </tr>"""

    # Clean phone for WhatsApp action link (strip non-digits, prepend 91 if 10-digit Indian number)
    clean_phone = "".join(filter(str.isdigit, str(phone)))
    if len(clean_phone) == 10:
        wa_phone = "91" + clean_phone
    else:
        wa_phone = clean_phone
    whatsapp_url = f"https://wa.me/{wa_phone}?text=Hi%20{full_name.split()[0]}%2C%20thank%20you%20for%20requesting%20early%20pilot%20access%20to%20DawaiFlow%20for%20{pharmacy_name}!"

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>New Pilot Request: {pharmacy_name}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #F8FAFC; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1E293B;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #F8FAFC; padding: 30px 15px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 600px; background-color: #FFFFFF; border-radius: 12px; border: 1px solid #E2E8F0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
          
          <!-- Header Banner -->
          <tr>
            <td style="background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%); padding: 24px 30px; text-align: left;">
              <div style="font-size: 20px; font-weight: 800; color: #FFFFFF; letter-spacing: -0.5px;">
                🛡️ Dawai<span style="color: #10B981;">Flow</span>
              </div>
              <p style="margin: 6px 0 0 0; color: #94A3B8; font-size: 13px; font-weight: 500;">Instant Pilot Access Lead Notification</p>
            </td>
          </tr>

          <!-- Main Content -->
          <tr>
            <td style="padding: 30px;">
              <div style="background-color: #ECFDF5; border-left: 4px solid #10B981; padding: 12px 16px; border-radius: 4px; margin-bottom: 24px;">
                <span style="color: #065F46; font-weight: 700; font-size: 14px;">🎉 New Pharmacy Pilot Signup Received</span>
                <p style="margin: 4px 0 0 0; color: #047857; font-size: 13px;">A pharmacy owner just requested early pilot access on the landing page.</p>
              </div>

              <!-- Lead Details Table -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border: 1px solid #E2E8F0; border-radius: 8px; overflow: hidden; margin-bottom: 24px;">
                <tr style="background-color: #F8FAFC;">
                  <td style="padding: 10px 16px; font-weight: 600; color: #64748B; font-size: 11.5px; text-transform: uppercase; width: 36%; border-bottom: 1px solid #E2E8F0;">Field</td>
                  <td style="padding: 10px 16px; font-weight: 600; color: #64748B; font-size: 11.5px; text-transform: uppercase; border-bottom: 1px solid #E2E8F0;">Submitted Details</td>
                </tr>
                <tr>
                  <td style="padding: 12px 16px; font-weight: 600; color: #334155; font-size: 13px; border-bottom: 1px solid #F1F5F9;">Pharmacy Name</td>
                  <td style="padding: 12px 16px; font-weight: 800; color: #0F172A; font-size: 15px; border-bottom: 1px solid #F1F5F9;">{pharmacy_name}</td>
                </tr>
                <tr>
                  <td style="padding: 12px 16px; font-weight: 600; color: #334155; font-size: 13px; border-bottom: 1px solid #F1F5F9;">Contact Person</td>
                  <td style="padding: 12px 16px; color: #1E293B; font-size: 14px; font-weight: 600; border-bottom: 1px solid #F1F5F9;">{full_name}</td>
                </tr>
                {email_row}
                <tr>
                  <td style="padding: 12px 16px; font-weight: 600; color: #334155; font-size: 13px; border-bottom: 1px solid #F1F5F9;">Phone Number</td>
                  <td style="padding: 12px 16px; color: #1E293B; font-size: 14px; border-bottom: 1px solid #F1F5F9;">
                    <a href="tel:{phone}" style="color: #2563EB; font-weight: 700; text-decoration: none;">{phone}</a>
                  </td>
                </tr>
                <tr>
                  <td style="padding: 12px 16px; font-weight: 600; color: #334155; font-size: 13px; border-bottom: 1px solid #F1F5F9;">City / Location</td>
                  <td style="padding: 12px 16px; color: #1E293B; font-size: 14px; border-bottom: 1px solid #F1F5F9;">{city}</td>
                </tr>
                <tr>
                  <td style="padding: 12px 16px; font-weight: 600; color: #334155; font-size: 13px; border-bottom: 1px solid #F1F5F9;">Current Billing Setup</td>
                  <td style="padding: 12px 16px; color: #1E293B; font-size: 14px; border-bottom: 1px solid #F1F5F9;">
                    <span style="background-color: #F1F5F9; color: #334155; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">{current_billing}</span>
                  </td>
                </tr>
                <tr>
                  <td style="padding: 12px 16px; font-weight: 600; color: #334155; font-size: 13px; border-bottom: 1px solid #F1F5F9;">Daily Bill Volume</td>
                  <td style="padding: 12px 16px; color: #1E293B; font-size: 14px; border-bottom: 1px solid #F1F5F9;">{bills_per_day}</td>
                </tr>
                <tr>
                  <td style="padding: 12px 16px; font-weight: 600; color: #334155; font-size: 13px; border-bottom: 1px solid #F1F5F9;">Biggest Pain Point / Details</td>
                  <td style="padding: 12px 16px; color: #475569; font-size: 13px; font-style: italic; line-height: 1.5; border-bottom: 1px solid #F1F5F9;">"{biggest_problem}"</td>
                </tr>
                <tr>
                  <td style="padding: 12px 16px; font-weight: 600; color: #334155; font-size: 13px;">Timestamp</td>
                  <td style="padding: 12px 16px; color: #64748B; font-size: 12px;">{created_at} &bull; Lead #{lead_id}</td>
                </tr>
              </table>

              <!-- Action Buttons -->
              <div style="text-align: center; margin: 20px 0 10px 0;">
                <a href="tel:{phone}" style="display: inline-block; background-color: #0F172A; color: #FFFFFF; font-size: 13px; font-weight: 700; text-decoration: none; padding: 10px 18px; border-radius: 6px; margin: 4px;">
                  📞 Call Pharmacist
                </a>
                <a href="{whatsapp_url}" target="_blank" style="display: inline-block; background-color: #10B981; color: #FFFFFF; font-size: 13px; font-weight: 700; text-decoration: none; padding: 10px 18px; border-radius: 6px; margin: 4px;">
                  💬 Open WhatsApp Chat
                </a>
              </div>

            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color: #F8FAFC; border-top: 1px solid #E2E8F0; padding: 14px 30px; text-align: center;">
              <p style="margin: 0; color: #94A3B8; font-size: 11.5px;">
                Sent automatically by DawaiFlow AI Platform Backend • Real-time Pilot Lead Alert
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def format_pilot_lead_plain_text(lead_data: Dict[str, Any]) -> str:
    """Generates plain text fallback email."""
    import re
    pharmacy_name = lead_data.get("pharmacy_name", "N/A")
    full_name = lead_data.get("full_name", "N/A")
    phone = lead_data.get("phone", "N/A")
    city = lead_data.get("city", "N/A")
    current_billing = lead_data.get("current_billing_method", "N/A")
    bills_per_day = lead_data.get("bills_per_day", "N/A")
    biggest_problem = lead_data.get("biggest_problem") or "None specified"
    created_at = lead_data.get("created_at") or datetime.utcnow().strftime("%d %b %Y, %I:%M %p UTC")
    lead_id = lead_data.get("id", "N/A")

    email_address = lead_data.get("email")
    if not email_address and isinstance(biggest_problem, str):
        email_match = re.search(r'\[Email:\s*([^\]]+)\]', biggest_problem, re.IGNORECASE)
        if email_match:
            email_address = email_match.group(1).strip()

    email_line = f"• Email Address:         {email_address}\n" if email_address else ""

    return f"""==================================================
DAWAIFLOW — NEW PILOT ACCESS REQUEST
==================================================

A new pharmacy lead has just signed up for the pilot:

• Pharmacy Name:         {pharmacy_name}
• Contact Person:        {full_name}
{email_line}• Phone Number:          {phone}
• City / Location:       {city}
• Current Billing Setup: {current_billing}
• Daily Bill Volume:     {bills_per_day}
• Biggest Pain Point:    {biggest_problem}
• Submitted At:          {created_at}
• Lead ID:               #{lead_id}

--------------------------------------------------
Call Pharmacist: tel:{phone}
--------------------------------------------------
Automated alert sent by DawaiFlow Platform.
"""


def get_ipv4_address(host: str) -> Optional[str]:
    """Resolves a hostname strictly to an IPv4 address to avoid broken IPv6 routes."""
    try:
        results = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
        if results:
            return results[0][4][0]
    except Exception:
        pass
    return None


def send_email_via_resend(
    to_email: str,
    subject: str,
    html_content: str,
    plain_text: str,
    from_name: str = "DawaiFlow Pilot Alerts",
    reply_to: Optional[str] = None,
) -> Tuple[bool, str, str]:
    """
    Sends email via Resend HTTPS REST API (port 443).
    Bypasses cloud platform SMTP port restrictions.
    """
    api_key = (os.getenv("RESEND_API_KEY") or "").strip()
    if not api_key:
        return False, "resend", "RESEND_API_KEY not configured"

    import urllib.request
    import json

    from_email = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev").strip()
    payload: Dict[str, Any] = {
        "from": f"{from_name} <{from_email}>",
        "to": [to_email],
        "subject": subject,
        "html": html_content,
        "text": plain_text,
    }
    if reply_to:
        payload["reply_to"] = reply_to

    try:
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "DawaiFlow-Backend/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            resp_body = response.read().decode("utf-8")
            resp_json = json.loads(resp_body)
            msg_id = resp_json.get("id", "ok")
            logger.info(f"[EMAIL NOTIFICATION] Successfully sent alert via Resend HTTPS API (id={msg_id}) to {to_email}")
            return True, "resend:https", ""
    except Exception as e:
        err_msg = f"Resend API error: {type(e).__name__}: {str(e)}"
        logger.warning(f"[EMAIL NOTIFICATION WARNING] {err_msg}")
        return False, "resend:https", err_msg


def send_email_via_brevo(
    to_email: str,
    subject: str,
    html_content: str,
    plain_text: str,
    from_name: str = "DawaiFlow Pilot Alerts",
    reply_to: Optional[str] = None,
) -> Tuple[bool, str, str]:
    """
    Sends email via Brevo (Sendinblue) HTTPS REST API (port 443).
    Bypasses cloud platform SMTP port restrictions.
    """
    api_key = (os.getenv("BREVO_API_KEY") or os.getenv("SENDINBLUE_API_KEY") or "").strip()
    if not api_key:
        return False, "brevo", "BREVO_API_KEY not configured"

    import urllib.request
    import json

    sender_email = (
        os.getenv("BREVO_SENDER_EMAIL")
        or os.getenv("SMTP_USER")
        or "hello@dawaiflow.com"
    ).strip()
    payload: Dict[str, Any] = {
        "sender": {"name": from_name, "email": sender_email},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content,
        "textContent": plain_text,
    }
    if reply_to:
        payload["replyTo"] = {"email": reply_to}

    try:
        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            resp_body = response.read().decode("utf-8")
            logger.info(f"[EMAIL NOTIFICATION] Successfully sent alert via Brevo HTTPS API to {to_email}")
            return True, "brevo:https", ""
    except Exception as e:
        err_msg = f"Brevo API error: {type(e).__name__}: {str(e)}"
        logger.warning(f"[EMAIL NOTIFICATION WARNING] {err_msg}")
        return False, "brevo:https", err_msg


def send_email_via_sendgrid(
    to_email: str,
    subject: str,
    html_content: str,
    plain_text: str,
    from_name: str = "DawaiFlow Pilot Alerts",
    reply_to: Optional[str] = None,
) -> Tuple[bool, str, str]:
    """
    Sends email via SendGrid HTTPS REST API (port 443).
    Bypasses cloud platform SMTP port restrictions.
    """
    api_key = (os.getenv("SENDGRID_API_KEY") or "").strip()
    if not api_key:
        return False, "sendgrid", "SENDGRID_API_KEY not configured"

    import urllib.request
    import json

    sender_email = (
        os.getenv("SENDGRID_SENDER_EMAIL")
        or os.getenv("SMTP_USER")
        or "vashistkanishak9@gmail.com"
    ).strip()
    payload: Dict[str, Any] = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": sender_email, "name": from_name},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": plain_text},
            {"type": "text/html", "value": html_content},
        ],
    }
    if reply_to:
        payload["reply_to"] = {"email": reply_to}

    try:
        req = urllib.request.Request(
            "https://api.sendgrid.com/v3/mail/send",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "DawaiFlow-Backend/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            logger.info(f"[EMAIL NOTIFICATION] Successfully sent alert via SendGrid HTTPS API to {to_email}")
            return True, "sendgrid:https", ""
    except Exception as e:
        err_msg = f"SendGrid API error: {type(e).__name__}: {str(e)}"
        logger.warning(f"[EMAIL NOTIFICATION WARNING] {err_msg}")
        return False, "sendgrid:https", err_msg


def send_email_with_fallback(
    msg: MIMEMultipart,
    cfg: Dict[str, Any],
    timeout: int = 12,
    subject: Optional[str] = None,
    html_content: Optional[str] = None,
    plain_text: Optional[str] = None,
) -> Tuple[bool, str, str]:
    """
    Sends email with multi-layer resilience:
    1. Direct SMTP with both DNS hostname and forced IPv4 resolution (Port 587 STARTTLS & Port 465 Direct SSL).
    2. Automatic HTTPS API fallback (Resend, Brevo, SendGrid) if cloud firewall blocks SMTP sockets.
    Returns (success: bool, provider_label: str, error_details: str).
    """
    host = cfg["host"]
    user = cfg["user"]
    password = cfg["password"]
    recipient = cfg.get("recipient") or msg.get("To", "unknown")
    email_subject = subject or msg.get("Subject", "DawaiFlow Notification")

    # If HTTPS API is explicitly configured, try it first to avoid blocked socket delays
    if os.getenv("RESEND_API_KEY") and html_content and plain_text:
        ok, prov, err = send_email_via_resend(
            to_email=recipient,
            subject=email_subject,
            html_content=html_content,
            plain_text=plain_text,
            from_name=cfg.get("from_name", "DawaiFlow Pilot Alerts"),
            reply_to=cfg.get("user") or None,
        )
        if ok:
            return True, prov, ""

    if (os.getenv("BREVO_API_KEY") or os.getenv("SENDINBLUE_API_KEY")) and html_content and plain_text:
        ok, prov, err = send_email_via_brevo(
            to_email=recipient,
            subject=email_subject,
            html_content=html_content,
            plain_text=plain_text,
            from_name=cfg.get("from_name", "DawaiFlow Pilot Alerts"),
            reply_to=cfg.get("user") or None,
        )
        if ok:
            return True, prov, ""

    if os.getenv("SENDGRID_API_KEY") and html_content and plain_text:
        ok, prov, err = send_email_via_sendgrid(
            to_email=recipient,
            subject=email_subject,
            html_content=html_content,
            plain_text=plain_text,
            from_name=cfg.get("from_name", "DawaiFlow Pilot Alerts"),
            reply_to=cfg.get("user") or None,
        )
        if ok:
            return True, prov, ""

    # SMTP Attempts: Ports 587 and 465
    primary_port = cfg.get("port", 587)
    secondary_port = 465 if primary_port == 587 else 587
    ports_to_try = [primary_port, secondary_port]

    # Resolve IPv4 to bypass broken IPv6 routes on Linux containers
    ipv4_address = get_ipv4_address(host)
    hosts_to_try = [host]
    if ipv4_address and ipv4_address != host:
        hosts_to_try.append(ipv4_address)

    errors: List[str] = []

    for port in ports_to_try:
        for target_host in hosts_to_try:
            is_ip = target_host == ipv4_address
            host_label = f"{target_host} ({'IPv4' if is_ip else 'DNS'})"
            try:
                logger.info(f"[EMAIL NOTIFICATION] Connecting to SMTP server {host_label}:{port}...")
                if port == 465:
                    with smtplib.SMTP_SSL(target_host, port, timeout=timeout) as server:
                        server.login(user, password)
                        server.send_message(msg)
                else:
                    with smtplib.SMTP(target_host, port, timeout=timeout) as server:
                        server.ehlo()
                        server.starttls()
                        server.ehlo()
                        server.login(user, password)
                        server.send_message(msg)

                provider_label = f"smtp:{port}:{('ipv4' if is_ip else 'dns')}"
                logger.info(f"[EMAIL NOTIFICATION] Successfully sent alert to {recipient} via {provider_label}.")
                return True, provider_label, ""
            except Exception as err:
                err_detail = f"Port {port} on {host_label} failed ({type(err).__name__}: {str(err)})"
                logger.warning(f"[EMAIL NOTIFICATION WARNING] {err_detail}")
                errors.append(err_detail)
                # If network is completely unreachable on host, do not waste time retrying raw sockets
                if "Network is unreachable" in str(err) or "Errno 101" in str(err):
                    logger.warning("[EMAIL NOTIFICATION] Raw socket networking is blocked/unreachable by cloud host. Skipping further raw socket retries.")
                    break
        if any("Errno 101" in e or "Network is unreachable" in e for e in errors):
            break
    if html_content and plain_text:
        if os.getenv("RESEND_API_KEY"):
            ok, prov, err = send_email_via_resend(
                to_email=recipient,
                subject=email_subject,
                html_content=html_content,
                plain_text=plain_text,
                from_name=cfg.get("from_name", "DawaiFlow Pilot Alerts"),
                reply_to=cfg.get("user") or None,
            )
            if ok:
                return True, prov, ""
            errors.append(err)

        if os.getenv("BREVO_API_KEY") or os.getenv("SENDINBLUE_API_KEY"):
            ok, prov, err = send_email_via_brevo(
                to_email=recipient,
                subject=email_subject,
                html_content=html_content,
                plain_text=plain_text,
                from_name=cfg.get("from_name", "DawaiFlow Pilot Alerts"),
                reply_to=cfg.get("user") or None,
            )
            if ok:
                return True, prov, ""
            errors.append(err)

        if os.getenv("SENDGRID_API_KEY"):
            ok, prov, err = send_email_via_sendgrid(
                to_email=recipient,
                subject=email_subject,
                html_content=html_content,
                plain_text=plain_text,
                from_name=cfg.get("from_name", "DawaiFlow Pilot Alerts"),
                reply_to=cfg.get("user") or None,
            )
            if ok:
                return True, prov, ""
            errors.append(err)

    combined_err = " | ".join(errors)
    logger.error(f"[EMAIL NOTIFICATION ERROR] All delivery methods failed for recipient {recipient}: {combined_err}")
    return False, "none", combined_err


def _update_lead_status(
    lead_id: int,
    status: str,
    error: Optional[str] = None,
    provider: Optional[str] = None
) -> None:
    """Updates database record for a pilot lead with its email notification outcome."""
    if not lead_id:
        return
    try:
        import database
        import models
        with database.SessionLocal() as db:
            lead = db.query(models.PilotLead).filter(models.PilotLead.id == lead_id).first()
            if lead:
                lead.notification_status = status
                lead.notified_at = datetime.utcnow()
                lead.notification_error = error
                lead.notification_provider = provider
                db.commit()
    except Exception as db_err:
        logger.warning(f"[EMAIL DB LOG ERROR] Could not update lead #{lead_id} status in DB: {db_err}")


def send_pilot_lead_notification(lead_data: Dict[str, Any], lead_id: Optional[int] = None) -> bool:
    """
    Sends an immediate email notification via SMTP (Gmail) to the founder.
    Designed to run inside a background task or standalone caller.
    Automatically logs status and error details to the pilot_leads table.
    """
    cfg = get_smtp_config()
    target_lead_id = lead_id or lead_data.get("id")
    pharmacy_name = lead_data.get("pharmacy_name", "New Pharmacy")
    subject = f"New Pilot Request: {pharmacy_name}"

    if not cfg["is_configured"]:
        missing = []
        if not cfg["user"]:
            missing.append("SMTP_USER/SMTP_USERNAME")
        if not cfg["password"]:
            missing.append("SMTP_PASS/SMTP_PASSWORD")
        if not cfg["recipient"]:
            missing.append("MY_EMAIL/ADMIN_EMAIL")
        err_msg = f"SMTP unconfigured: missing {', '.join(missing)}"
        logger.warning(f"[EMAIL NOTIFICATION] {err_msg}. Notification for '{pharmacy_name}' skipped.")
        if target_lead_id:
            _update_lead_status(target_lead_id, "SKIPPED_NOT_CONFIGURED", error=err_msg)
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{cfg['from_name']} <{cfg['user']}>"
        msg["To"] = cfg["recipient"]
        msg["Reply-To"] = cfg["user"]

        part_plain_text = format_pilot_lead_plain_text(lead_data)
        part_html_content = format_pilot_lead_html(lead_data)

        part_plain = MIMEText(part_plain_text, "plain", "utf-8")
        part_html = MIMEText(part_html_content, "html", "utf-8")

        msg.attach(part_plain)
        msg.attach(part_html)

        success, provider, err_details = send_email_with_fallback(
            msg, cfg,
            subject=subject,
            html_content=part_html_content,
            plain_text=part_plain_text
        )
        if success:
            if target_lead_id:
                _update_lead_status(target_lead_id, "SENT", provider=provider)
            return True
        else:
            if target_lead_id:
                _update_lead_status(target_lead_id, "FAILED", error=err_details)
            return False

    except Exception as e:
        logger.error(f"[EMAIL NOTIFICATION ERROR] Unexpected error for lead #{target_lead_id}: {e}", exc_info=True)
        if target_lead_id:
            _update_lead_status(target_lead_id, "FAILED", error=str(e))
        return False


def send_test_email(test_recipient: Optional[str] = None) -> Dict[str, Any]:
    """
    Sends a test email to verify SMTP credentials and network connectivity.
    Returns diagnostic results including port used and failover status.
    """
    cfg = get_smtp_config()
    recipient = (test_recipient or cfg["recipient"]).strip()

    if not cfg["user"] or not cfg["password"]:
        return {
            "success": False,
            "error": "SMTP_USER or SMTP_PASS is missing in environment variables.",
            "help": "Please set SMTP_USER (e.g. your Gmail) and SMTP_PASS (16-character Gmail App Password)."
        }

    if not recipient:
        return {
            "success": False,
            "error": "Recipient email (MY_EMAIL or SMTP_USER) is not configured.",
            "help": "Set MY_EMAIL in environment variables with your personal receiving email address."
        }

    test_lead = {
        "id": 999,
        "full_name": "Dr. Rajesh Kumar (Diagnostic Test Lead)",
        "pharmacy_name": "DawaiFlow System Diagnostics",
        "city": "New Delhi",
        "phone": "+91 9817066533",
        "current_billing_method": "Marg ERP",
        "bills_per_day": "100–200",
        "biggest_problem": "System diagnostic verification test of email alert delivery engine.",
        "created_at": datetime.utcnow().strftime("%d %b %Y, %I:%M %p UTC"),
    }

    try:
        msg = MIMEMultipart("alternative")
        subject = f"🧪 [TEST] DawaiFlow Email Delivery Verified: {test_lead['pharmacy_name']}"
        msg["Subject"] = subject
        msg["From"] = f"{cfg['from_name']} <{cfg['user']}>"
        msg["To"] = recipient

        plain_text = format_pilot_lead_plain_text(test_lead)
        html_content = format_pilot_lead_html(test_lead)

        part_plain = MIMEText(plain_text, "plain", "utf-8")
        part_html = MIMEText(html_content, "html", "utf-8")

        msg.attach(part_plain)
        msg.attach(part_html)

        success, provider, err_details = send_email_with_fallback(
            msg, cfg,
            subject=subject,
            html_content=html_content,
            plain_text=plain_text
        )
        if success:
            return {
                "success": True,
                "message": f"Test email sent successfully to {recipient} via {provider}.",
                "recipient": recipient,
                "sender": cfg["user"],
                "provider": provider,
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            return {
                "success": False,
                "error": err_details,
                "help": "Ensure your 16-character Gmail App Password is correct without spaces, 2-Step Verification is enabled, and your server can reach smtp.gmail.com or configure RESEND_API_KEY."
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "help": "An unexpected exception occurred during test email delivery."
        }


def check_smtp_health(probe_network: bool = False) -> Dict[str, Any]:
    """Diagnostic tool to inspect environment variables and optionally test network connectivity."""
    cfg = get_smtp_config()
    user = cfg["user"]
    masked_user = (user[:2] + "***" + user[user.find("@"):]) if ("@" in user and len(user) > 3) else ("SET" if user else "NOT_SET")

    def test_conn(h: str, p: int) -> Dict[str, Any]:
        try:
            with socket.create_connection((h, p), timeout=2):
                return {"reachable": True, "error": None}
        except Exception as e:
            return {"reachable": False, "error": f"{type(e).__name__}: {str(e)}"}

    ipv4 = get_ipv4_address(cfg["host"])

    if probe_network:
        conn_587 = test_conn(cfg["host"], 587)
        conn_587_ipv4 = test_conn(ipv4, 587) if ipv4 else None
        conn_465 = test_conn(cfg["host"], 465)
        conn_465_ipv4 = test_conn(ipv4, 465) if ipv4 else None
        conn_https_resend = test_conn("api.resend.com", 443)
    else:
        conn_587 = {"reachable": None, "note": "Probe skipped (pass ?probe=true to test)"}
        conn_587_ipv4 = None
        conn_465 = {"reachable": None, "note": "Probe skipped (pass ?probe=true to test)"}
        conn_465_ipv4 = None
        conn_https_resend = {"reachable": True, "note": "Standard HTTPS port 443 open"}

    return {
        "is_configured": cfg["is_configured"],
        "host": cfg["host"],
        "ipv4_resolved": ipv4,
        "primary_port": cfg["port"],
        "has_user": bool(cfg["user"]),
        "user_masked": masked_user,
        "has_password": bool(cfg["password"]),
        "password_length": len(cfg["password"]),
        "recipient": cfg["recipient"],
        "from_name": cfg["from_name"],
        "port_587_dns": conn_587,
        "port_587_ipv4": conn_587_ipv4,
        "port_465_dns": conn_465,
        "port_465_ipv4": conn_465_ipv4,
        "https_api_reachable": conn_https_resend,
        "environment_vars_detected": {
            "SMTP_USER": bool(os.getenv("SMTP_USER")),
            "SMTP_USERNAME": bool(os.getenv("SMTP_USERNAME")),
            "MAIL_USERNAME": bool(os.getenv("MAIL_USERNAME")),
            "SMTP_PASS": bool(os.getenv("SMTP_PASS")),
            "SMTP_PASSWORD": bool(os.getenv("SMTP_PASSWORD")),
            "MAIL_PASSWORD": bool(os.getenv("MAIL_PASSWORD")),
            "GMAIL_APP_PASSWORD": bool(os.getenv("GMAIL_APP_PASSWORD")),
            "MY_EMAIL": bool(os.getenv("MY_EMAIL")),
            "ADMIN_EMAIL": bool(os.getenv("ADMIN_EMAIL")),
            "ADMIN_NOTIFICATION_EMAIL": bool(os.getenv("ADMIN_NOTIFICATION_EMAIL")),
            "RESEND_API_KEY": bool(os.getenv("RESEND_API_KEY")),
            "BREVO_API_KEY": bool(os.getenv("BREVO_API_KEY")),
            "SENDGRID_API_KEY": bool(os.getenv("SENDGRID_API_KEY")),
        }
    }


def retry_pending_pilot_leads(limit: int = 20) -> Dict[str, Any]:
    """Retries notifications for leads that are pending, failed, or were skipped due to unconfigured SMTP."""
    cfg = get_smtp_config()
    if not cfg["is_configured"]:
        return {"success": False, "message": "SMTP not configured, retry skipped", "retried": 0}

    import database
    import models

    retried_count = 0
    succeeded_count = 0
    failed_count = 0

    try:
        with database.SessionLocal() as db:
            pending_leads = (
                db.query(models.PilotLead)
                .filter(models.PilotLead.notification_status.in_(["PENDING", "FAILED", "SKIPPED_NOT_CONFIGURED", None]))
                .order_by(models.PilotLead.id.desc())
                .limit(limit)
                .all()
            )

            for lead in pending_leads:
                retried_count += 1
                lead_dict = {
                    "id": lead.id,
                    "full_name": lead.full_name,
                    "pharmacy_name": lead.pharmacy_name,
                    "city": lead.city,
                    "phone": lead.phone,
                    "current_billing_method": lead.current_billing_method,
                    "bills_per_day": lead.bills_per_day,
                    "biggest_problem": lead.biggest_problem,
                    "created_at": lead.created_at.strftime("%d %b %Y, %I:%M %p UTC") if lead.created_at else datetime.utcnow().strftime("%d %b %Y, %I:%M %p UTC"),
                }
                ok = send_pilot_lead_notification(lead_dict, lead_id=lead.id)
                if ok:
                    succeeded_count += 1
                else:
                    failed_count += 1

        return {
            "success": True,
            "retried": retried_count,
            "succeeded": succeeded_count,
            "failed": failed_count,
        }
    except Exception as e:
        logger.error(f"[EMAIL RETRY ERROR] Failed during lead notification retry: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "retried": retried_count,
            "succeeded": succeeded_count,
            "failed": failed_count,
        }


def send_ca_report_email(
    ca_email: str,
    sender_email: str,
    pharmacy_name: str,
    owner_name: str,
    gstin: Optional[str],
    date_range_label: str,
    reports_shared_labels: list,
    summary_dict: dict,
    csv_attachments: Optional[dict] = None,
    custom_message: Optional[str] = None
) -> dict:
    """
    Sends pharmacy financial & GST reports directly to the Chartered Accountant.
    Sets Reply-To to the authenticated shopkeeper's email identity.
    Attaches CSV report files (Sales Register, Purchase Register, GST Summary, HSN Summary).
    """
    from email.mime.base import MIMEBase
    from email import encoders

    cfg = get_smtp_config()
    if not cfg["is_configured"]:
        return {
            "success": False,
            "error": "SMTP server is not configured. Please set SMTP_USER and SMTP_PASS environment variables."
        }

    formatted_time = datetime.utcnow().strftime("%d %b %Y, %I:%M %p UTC")
    reports_html = "".join([f"<li style='margin-bottom: 4px;'>📊 <strong>{r}</strong></li>" for r in reports_shared_labels])

    custom_msg_section = ""
    if custom_message and custom_message.strip():
        custom_msg_section = f"""
        <div style="background-color: #F1F5F9; border-left: 4px solid #3B82F6; padding: 12px 16px; border-radius: 4px; margin-bottom: 20px;">
          <strong style="color: #1E293B; font-size: 13px;">Note from Pharmacy Owner:</strong>
          <p style="margin: 4px 0 0 0; color: #334155; font-size: 13.5px; font-style: italic;">"{custom_message.strip()}"</p>
        </div>
        """

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>DawaiFlow - Pharmacy GST & Financial Reports</title>
</head>
<body style="margin: 0; padding: 0; background-color: #F8FAFC; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1E293B;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #F8FAFC; padding: 30px 15px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 600px; background-color: #FFFFFF; border-radius: 12px; border: 1px solid #E2E8F0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
          
          <!-- Header Banner -->
          <tr>
            <td style="background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%); padding: 24px 30px; text-align: left;">
              <div style="font-size: 20px; font-weight: 800; color: #FFFFFF; letter-spacing: -0.5px;">
                🛡️ Dawai<span style="color: #10B981;">Flow</span> ERP
              </div>
              <p style="margin: 6px 0 0 0; color: #94A3B8; font-size: 13px; font-weight: 500;">CA Connect — Official Financial & GST Data Package</p>
            </td>
          </tr>

          <!-- Main Content -->
          <tr>
            <td style="padding: 30px;">
              <div style="background-color: #ECFDF5; border-left: 4px solid #10B981; padding: 12px 16px; border-radius: 4px; margin-bottom: 24px;">
                <span style="color: #065F46; font-weight: 700; font-size: 14.5px;">📈 Pharmacy Reports Shared with CA</span>
                <p style="margin: 4px 0 0 0; color: #047857; font-size: 13px;">Sent by <strong>{owner_name}</strong> ({sender_email}) for <strong>{pharmacy_name}</strong>.</p>
              </div>

              <!-- Authenticated Sender Identity Block -->
              <div style="background-color: #F0F9FF; border-left: 4px solid #0284C7; padding: 14px 18px; border-radius: 6px; margin-bottom: 24px;">
                <span style="color: #0369A1; font-weight: 700; font-size: 13.5px;">👤 Authenticated Sender Identity</span>
                <table role="presentation" width="100%" style="margin-top: 6px; font-size: 13px; color: #1E293B;">
                  <tr>
                    <td style="padding: 2px 0; width: 130px; font-weight: 600; color: #64748B;">Sender Email:</td>
                    <td style="padding: 2px 0; font-weight: 700; color: #0284C7;">{sender_email}</td>
                  </tr>
                  <tr>
                    <td style="padding: 2px 0; font-weight: 600; color: #64748B;">Pharmacy Name:</td>
                    <td style="padding: 2px 0; font-weight: 700;">{pharmacy_name}</td>
                  </tr>
                  <tr>
                    <td style="padding: 2px 0; font-weight: 600; color: #64748B;">Target CA:</td>
                    <td style="padding: 2px 0; font-weight: 700; color: #059669;">{ca_email}</td>
                  </tr>
                </table>
              </div>

              {custom_msg_section}

              <!-- Summary Metadata -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border: 1px solid #E2E8F0; border-radius: 8px; overflow: hidden; margin-bottom: 24px;">
                <tr style="background-color: #F8FAFC;">
                  <td style="padding: 10px 16px; font-weight: 600; color: #64748B; font-size: 12px; border-bottom: 1px solid #E2E8F0;">Pharmacy Name</td>
                  <td style="padding: 10px 16px; font-weight: 700; color: #0F172A; font-size: 13px; border-bottom: 1px solid #E2E8F0;">{pharmacy_name}</td>
                </tr>
                <tr>
                  <td style="padding: 10px 16px; font-weight: 600; color: #64748B; font-size: 12px; border-bottom: 1px solid #E2E8F0;">GSTIN</td>
                  <td style="padding: 10px 16px; font-weight: 700; color: #0F172A; font-size: 13px; border-bottom: 1px solid #E2E8F0;">{gstin or 'N/A'}</td>
                </tr>
                <tr style="background-color: #F8FAFC;">
                  <td style="padding: 10px 16px; font-weight: 600; color: #64748B; font-size: 12px; border-bottom: 1px solid #E2E8F0;">Reporting Period</td>
                  <td style="padding: 10px 16px; font-weight: 700; color: #2563EB; font-size: 13px; border-bottom: 1px solid #E2E8F0;">{date_range_label}</td>
                </tr>
                <tr>
                  <td style="padding: 10px 16px; font-weight: 600; color: #64748B; font-size: 12px;">Generated Date</td>
                  <td style="padding: 10px 16px; color: #475569; font-size: 12.5px;">{formatted_time}</td>
                </tr>
              </table>

              <!-- Key Metrics Card -->
              <div style="border: 1px solid #CBD5E1; border-radius: 8px; padding: 16px; margin-bottom: 24px; background-color: #FFFFFF;">
                <div style="font-weight: 700; font-size: 14px; color: #0F172A; margin-bottom: 12px;">Financial Overview ({date_range_label})</div>
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                  <tr>
                    <td style="padding: 6px 0; color: #64748B; font-size: 13px;">Total Sales Volume:</td>
                    <td style="padding: 6px 0; font-weight: 700; color: #166534; font-size: 13.5px; text-align: right;">₹{summary_dict.get('total_sales', 0.0):,.2f} ({summary_dict.get('total_bills', 0)} bills)</td>
                  </tr>
                  <tr>
                    <td style="padding: 6px 0; color: #64748B; font-size: 13px;">Total Purchases:</td>
                    <td style="padding: 6px 0; font-weight: 700; color: #1E40AF; font-size: 13.5px; text-align: right;">₹{summary_dict.get('total_purchases', 0.0):,.2f}</td>
                  </tr>
                  <tr>
                    <td style="padding: 6px 0; color: #64748B; font-size: 13px;">Output GST Collected:</td>
                    <td style="padding: 6px 0; font-weight: 700; color: #D97706; font-size: 13.5px; text-align: right;">₹{summary_dict.get('total_output_gst', 0.0):,.2f}</td>
                  </tr>
                  <tr>
                    <td style="padding: 6px 0; color: #64748B; font-size: 13px;">Input GST Paid:</td>
                    <td style="padding: 6px 0; font-weight: 700; color: #059669; font-size: 13.5px; text-align: right;">₹{summary_dict.get('total_input_gst', 0.0):,.2f}</td>
                  </tr>
                  <tr style="border-top: 1px dashed #CBD5E1;">
                    <td style="padding: 8px 0 0 0; font-weight: 700; color: #0F172A; font-size: 13.5px;">Net Tax Liability:</td>
                    <td style="padding: 8px 0 0 0; font-weight: 800; color: #B91C1C; font-size: 14px; text-align: right;">₹{summary_dict.get('net_gst_payable', 0.0):,.2f}</td>
                  </tr>
                </table>
              </div>

              <!-- Reports Included -->
              <div style="font-weight: 700; font-size: 14px; color: #0F172A; margin-bottom: 8px;">Attached Reports ({len(reports_shared_labels)}):</div>
              <ul style="margin: 0 0 24px 0; padding-left: 20px; color: #334155; font-size: 13.5px;">
                {reports_html}
              </ul>

              <p style="color: #64748B; font-size: 12.5px; line-height: 1.5;">
                This package contains formatted spreadsheet report files attached directly to this email. You can import these CSV files directly into Tally, Zoho Books, Busy, or GST return filing software.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color: #F1F5F9; padding: 20px 30px; text-align: center; border-top: 1px solid #E2E8F0;">
              <p style="margin: 0; color: #94A3B8; font-size: 12px;">
                Generated securely by <strong>DawaiFlow AI Pharmacy ERP System</strong>.<br>
                This automated email was triggered directly by {owner_name} ({sender_email}).
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    try:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = f"📑 DawaiFlow — Pharmacy Financial & GST Reports ({pharmacy_name} - {date_range_label})"
        
        # SENDER IDENTITY: Display Shopkeeper Name & Pharmacy Name, set Reply-To to Shopkeeper's Email
        sender_display_name = f"{owner_name} ({pharmacy_name}) via DawaiFlow"
        msg["From"] = f"{sender_display_name} <{cfg['user']}>"
        msg["Reply-To"] = f"{owner_name} <{sender_email}>"
        msg["To"] = ca_email

        msg_body = MIMEMultipart("alternative")
        msg_body.attach(MIMEText(f"Pharmacy GST & Financial Reports shared by {pharmacy_name} ({date_range_label}).", "plain", "utf-8"))
        msg_body.attach(MIMEText(html_content, "html", "utf-8"))
        msg.attach(msg_body)

        # Attach CSV files if provided
        if csv_attachments:
            for filename, content_str in csv_attachments.items():
                attachment = MIMEBase("text", "csv")
                attachment.set_payload(content_str.encode("utf-8"))
                encoders.encode_base64(attachment)
                attachment.add_header("Content-Disposition", f'attachment; filename="{filename}"')
                msg.attach(attachment)

        success, provider, err_details = send_email_with_fallback(msg, cfg)
        if success:
            return {
                "success": True,
                "message": f"Reports successfully emailed to {ca_email} via {provider}.",
                "ca_email": ca_email,
                "provider": provider,
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            return {
                "success": False,
                "error": f"Delivery failed: {err_details}"
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

