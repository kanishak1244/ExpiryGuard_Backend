"""
email_service.py - ExpiryGuard Instant Email Notification Engine
Sends immediate email notifications for new pilot lead requests via SMTP (e.g. Gmail App Password).
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()


def get_smtp_config() -> Dict[str, Any]:
    """Reads SMTP configuration from environment variables with sensible defaults."""
    load_dotenv(override=True)
    host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    port_str = os.getenv("SMTP_PORT", "587").strip()
    try:
        port = int(port_str)
    except ValueError:
        port = 587
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASS", "").strip().replace(" ", "")
    # Founder recipient email defaults to MY_EMAIL, or SMTP_USER if not set
    recipient = os.getenv("MY_EMAIL", os.getenv("NOTIFICATION_RECIPIENT", user)).strip()
    from_name = os.getenv("SMTP_FROM_NAME", "ExpiryGuard Pilot Alerts").strip()

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
    pharmacy_name = lead_data.get("pharmacy_name", "N/A")
    full_name = lead_data.get("full_name", "N/A")
    phone = lead_data.get("phone", "N/A")
    city = lead_data.get("city", "N/A")
    current_billing = lead_data.get("current_billing_method", "N/A")
    bills_per_day = lead_data.get("bills_per_day", "N/A")
    biggest_problem = lead_data.get("biggest_problem") or "None specified"
    created_at = lead_data.get("created_at") or datetime.utcnow().strftime("%d %b %Y, %I:%M %p UTC")
    lead_id = lead_data.get("id", "N/A")

    # Clean phone for WhatsApp action link (strip non-digits, prepend 91 if 10-digit Indian number)
    clean_phone = "".join(filter(str.isdigit, str(phone)))
    if len(clean_phone) == 10:
        wa_phone = "91" + clean_phone
    else:
        wa_phone = clean_phone
    whatsapp_url = f"https://wa.me/{wa_phone}?text=Hi%20{full_name.split()[0]}%2C%20thank%20you%20for%20requesting%20early%20pilot%20access%20to%20ExpiryGuard%20for%20{pharmacy_name}!"

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
                🛡️ Expiry<span style="color: #10B981;">Guard</span>
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
                  <td style="padding: 12px 16px; font-weight: 600; color: #334155; font-size: 13px; border-bottom: 1px solid #F1F5F9;">Biggest Pain Point</td>
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
                Sent automatically by ExpiryGuard AI Platform Backend • Real-time Pilot Lead Alert
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
    pharmacy_name = lead_data.get("pharmacy_name", "N/A")
    full_name = lead_data.get("full_name", "N/A")
    phone = lead_data.get("phone", "N/A")
    city = lead_data.get("city", "N/A")
    current_billing = lead_data.get("current_billing_method", "N/A")
    bills_per_day = lead_data.get("bills_per_day", "N/A")
    biggest_problem = lead_data.get("biggest_problem") or "None specified"
    created_at = lead_data.get("created_at") or datetime.utcnow().strftime("%d %b %Y, %I:%M %p UTC")
    lead_id = lead_data.get("id", "N/A")

    return f"""==================================================
EXPIRYGUARD — NEW PILOT ACCESS REQUEST
==================================================

A new pharmacy lead has just signed up for the pilot:

• Pharmacy Name:         {pharmacy_name}
• Contact Person:        {full_name}
• Phone Number:          {phone}
• City / Location:       {city}
• Current Billing Setup: {current_billing}
• Daily Bill Volume:     {bills_per_day}
• Biggest Pain Point:    {biggest_problem}
• Submitted At:          {created_at}
• Lead ID:               #{lead_id}

--------------------------------------------------
Call Pharmacist: tel:{phone}
--------------------------------------------------
Automated alert sent by ExpiryGuard Platform.
"""


def send_pilot_lead_notification(lead_data: Dict[str, Any]) -> bool:
    """
    Sends an immediate email notification via SMTP (Gmail) to the founder.
    Designed to run inside a background task so it never blocks or fails lead submission.
    """
    cfg = get_smtp_config()
    pharmacy_name = lead_data.get("pharmacy_name", "New Pharmacy")
    subject = f"New Pilot Request: {pharmacy_name}"

    if not cfg["is_configured"]:
        print(f"[EMAIL NOTIFICATION] SMTP credentials not configured (SMTP_USER or SMTP_PASS missing). Notification for '{pharmacy_name}' skipped.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{cfg['from_name']} <{cfg['user']}>"
        msg["To"] = cfg["recipient"]
        msg["Reply-To"] = cfg["user"]

        part_plain = MIMEText(format_pilot_lead_plain_text(lead_data), "plain", "utf-8")
        part_html = MIMEText(format_pilot_lead_html(lead_data), "html", "utf-8")

        msg.attach(part_plain)
        msg.attach(part_html)

        print(f"[EMAIL NOTIFICATION] Connecting to SMTP server {cfg['host']}:{cfg['port']}...")
        if cfg["port"] == 465:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=15) as server:
                server.login(cfg["user"], cfg["password"])
                server.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(cfg["user"], cfg["password"])
                server.send_message(msg)

        print(f"[EMAIL NOTIFICATION] Successfully sent new pilot request alert to {cfg['recipient']} for '{pharmacy_name}'.")
        return True

    except Exception as e:
        print(f"[EMAIL NOTIFICATION ERROR] Failed to send pilot request email: {str(e)}")
        return False


def send_test_email(test_recipient: Optional[str] = None) -> Dict[str, Any]:
    """
    Sends a test email to verify SMTP credentials and network connectivity.
    Returns diagnostic results.
    """
    cfg = get_smtp_config()
    recipient = (test_recipient or cfg["recipient"]).strip()

    if not cfg["user"] or not cfg["password"]:
        return {
            "success": False,
            "error": "SMTP_USER or SMTP_PASS is missing in your .env file.",
            "help": "Please set SMTP_USER and SMTP_PASS (16-character Gmail App Password) in .env"
        }

    if not recipient:
        return {
            "success": False,
            "error": "Recipient email (MY_EMAIL or SMTP_USER) is not configured.",
            "help": "Set MY_EMAIL in your .env file with your personal receiving email address."
        }

    test_lead = {
        "id": 999,
        "full_name": "Dr. Rajesh Kumar (Sample Lead)",
        "pharmacy_name": "City Medicos & Healthcare",
        "city": "New Delhi",
        "phone": "+91 9876543210",
        "current_billing_method": "Marg ERP",
        "bills_per_day": "100–200",
        "biggest_problem": "Manual bill typing is too slow during peak rush hours and inventory counts frequently get mismatched.",
        "created_at": datetime.utcnow().strftime("%d %b %Y, %I:%M %p UTC"),
    }

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🧪 [TEST] ExpiryGuard Notification Setup Verified: {test_lead['pharmacy_name']}"
        msg["From"] = f"{cfg['from_name']} <{cfg['user']}>"
        msg["To"] = recipient

        part_plain = MIMEText(format_pilot_lead_plain_text(test_lead), "plain", "utf-8")
        part_html = MIMEText(format_pilot_lead_html(test_lead), "html", "utf-8")

        msg.attach(part_plain)
        msg.attach(part_html)

        if cfg["port"] == 465:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=15) as server:
                server.login(cfg["user"], cfg["password"])
                server.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(cfg["user"], cfg["password"])
                server.send_message(msg)

        return {
            "success": True,
            "message": f"Test email sent successfully to {recipient} via {cfg['host']}:{cfg['port']}.",
            "recipient": recipient,
            "sender": cfg["user"],
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "help": "Ensure your 16-character Gmail App Password is correct without spaces, 2-Step Verification is enabled on your Google account, and your server can reach smtp.gmail.com:587."
        }
