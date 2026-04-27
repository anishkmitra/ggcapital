#!/usr/bin/env python3
"""Send daily PnL report via Gmail."""

import sys
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'), override=True)

from digest import generate_digest


def send_report():
    gmail_address = os.getenv('GMAIL_ADDRESS')
    gmail_password = os.getenv('GMAIL_APP_PASSWORD')

    if not gmail_address or not gmail_password:
        print("ERROR: GMAIL_ADDRESS or GMAIL_APP_PASSWORD not set in .env")
        return False

    subject, html_body = generate_digest()

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"Trading Bot <{gmail_address}>"
    msg['To'] = gmail_address

    # Plain text fallback
    plain_text = subject + "\n\nOpen in an HTML-capable email client to see the full report."
    msg.attach(MIMEText(plain_text, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail_address, gmail_password)
            server.sendmail(gmail_address, gmail_address, msg.as_string())
        print(f"Report sent to {gmail_address}: {subject}")
        return True
    except Exception as e:
        print(f"ERROR sending email: {e}")
        return False


if __name__ == '__main__':
    send_report()
