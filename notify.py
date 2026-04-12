"""
notify.py — Garden Calendar daily notification
Reads garden_data.json from Google Drive and sends email if there are
overdue or upcoming treatments.
"""

import json
import os
import io
import smtplib
import base64
from datetime import date, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


# ── Config from environment variables (GitHub Secrets) ───────────────────────
GMAIL_USER        = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "")
NOTIFY_TO         = os.environ["NOTIFY_TO"]
FOLDER_ID         = os.environ["GDRIVE_FOLDER_ID"]
CREDENTIALS_JSON  = os.environ["GDRIVE_CREDENTIALS"]

# ── Google Drive setup ────────────────────────────────────────────────────────
creds_dict = json.loads(CREDENTIALS_JSON)
creds = service_account.Credentials.from_service_account_info(
    creds_dict,
    scopes=["https://www.googleapis.com/auth/drive.readonly"]
)
drive = build("drive", "v3", credentials=creds, cache_discovery=False)


def find_file(name):
    q = f"name='{name}' and '{FOLDER_ID}' in parents and trashed=false"
    r = drive.files().list(q=q, fields="files(id)").execute()
    files = r.get("files", [])
    return files[0]["id"] if files else None


def read_json(name):
    fid = find_file(name)
    if not fid:
        return None
    buf = io.BytesIO()
    req = drive.files().get_media(fileId=fid)
    dl  = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    return json.loads(buf.getvalue().decode("utf-8"))


def next_date(last_date_str, interval):
    if not last_date_str:
        return None
    return date.fromisoformat(last_date_str) + timedelta(days=interval)


# ── Load data ─────────────────────────────────────────────────────────────────
data = read_json("garden_data.json")
if not data:
    print("No garden_data.json found in Drive. Exiting.")
    exit(0)

today = date.today()

# ── Build notification content ────────────────────────────────────────────────
overdue, due_today, due_soon, sick_plants = [], [], [], []

for plant in data.get("plants", []):
    if plant.get("sick"):
        sick_plants.append(plant)
    for t in plant.get("treatments", []):
        nd = next_date(t.get("last_date"), t["interval_days"])
        if nd is None:
            continue
        delta = (nd - today).days
        entry = {
            "plant":     f"{plant['emoji']} {plant['name']}",
            "treatment": t["name"],
            "date":      str(nd),
            "delta":     delta,
        }
        if delta < 0:    overdue.append(entry)
        elif delta == 0: due_today.append(entry)
        elif delta <= 3: due_soon.append(entry)

# Skip if nothing to report
if not overdue and not due_today and not due_soon and not sick_plants:
    print("Nothing to report today. No email sent.")
    exit(0)

# ── Build email ───────────────────────────────────────────────────────────────
def section_html(title, color, entries, show_delta=True):
    if not entries:
        return ""
    rows = ""
    for e in entries:
        delta_str = ""
        if show_delta and e["delta"] < 0:
            delta_str = f" <span style='color:#c0392b'>({abs(e['delta'])}d vencido)</span>"
        elif show_delta and e["delta"] > 0:
            delta_str = f" <span style='color:#856404'>(en {e['delta']}d)</span>"
        rows += f"""
        <tr>
            <td style='padding:6px 12px;border-bottom:1px solid #f0f0f0'>{e['plant']}</td>
            <td style='padding:6px 12px;border-bottom:1px solid #f0f0f0'>{e['treatment']}</td>
            <td style='padding:6px 12px;border-bottom:1px solid #f0f0f0'>{e['date']}{delta_str}</td>
        </tr>"""
    return f"""
    <h3 style='color:{color};margin:1.2rem 0 0.4rem'>{title}</h3>
    <table style='width:100%;border-collapse:collapse;background:white;border-radius:8px;overflow:hidden'>
        <thead>
            <tr style='background:{color}20'>
                <th style='padding:8px 12px;text-align:left;color:{color}'>Planta</th>
                <th style='padding:8px 12px;text-align:left;color:{color}'>Tratamiento</th>
                <th style='padding:8px 12px;text-align:left;color:{color}'>Fecha</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>"""

sick_html = ""
if sick_plants:
    items = "".join(f"<li>{p['emoji']} <b>{p['name']}</b> — {p.get('sick_name') or 'plaga activa'} (desde {p.get('sick_date') or '—'})</li>"
                    for p in sick_plants)
    sick_html = f"""
    <h3 style='color:#c0392b;margin:1.2rem 0 0.4rem'>🐛 Plantas con plaga activa</h3>
    <ul style='background:white;padding:12px 12px 12px 28px;border-radius:8px;margin:0'>{items}</ul>"""

body_html = f"""
<div style='font-family:sans-serif;max-width:600px;margin:auto;background:#f5f7f2;padding:20px;border-radius:12px'>
    <div style='background:linear-gradient(135deg,#2d5a27,#4a7c59);padding:16px 20px;border-radius:10px;margin-bottom:16px'>
        <h2 style='color:white;margin:0'>🌿 Garden Calendar</h2>
        <p style='color:rgba(255,255,255,0.75);margin:4px 0 0;font-size:0.9rem'>{today.strftime("%A, %d de %B de %Y")}</p>
    </div>
    {sick_html}
    {section_html("⚠️ Tratamientos vencidos", "#c0392b", overdue)}
    {section_html("📅 Tratamientos para hoy", "#2d5a27", due_today, show_delta=False)}
    {section_html("🔔 Próximos 3 días", "#856404", due_soon)}
    <p style='color:#aaa;font-size:0.75rem;margin-top:16px;text-align:center'>
        Garden Calendar · Notificación automática diaria
    </p>
</div>
"""

n_issues = len(overdue) + len(due_today) + len(sick_plants)
subject  = f"🌿 Garden Calendar — {n_issues} {'urgente' if n_issues == 1 else 'urgentes'}" if n_issues else f"🌿 Garden Calendar — {len(due_soon)} próximos"

# ── Send email ────────────────────────────────────────────────────────────────
msg = MIMEMultipart("alternative")
msg["Subject"] = subject
msg["From"]    = GMAIL_USER
msg["To"]      = NOTIFY_TO
msg.attach(MIMEText(body_html, "html"))

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
    smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    smtp.sendmail(GMAIL_USER, NOTIFY_TO, msg.as_string())

print(f"Email sent: {subject}")