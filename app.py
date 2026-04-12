import streamlit as st
import json
import base64
import calendar
import io
import requests
from datetime import date, timedelta
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Garden Calendar", page_icon="🌿", layout="wide")

# ── Auth ──────────────────────────────────────────────────────────────────────
ALLOWED_EMAILS = ["pairo.miquel@gmail.com"]  # add more if needed

if not st.user.is_logged_in:
    st.markdown("""
    <div style='max-width:400px;margin:4rem auto;text-align:center'>
        <div style='background:linear-gradient(135deg,#2d5a27,#4a7c59);padding:2rem;border-radius:14px;color:white;margin-bottom:1.5rem'>
            <h2 style='margin:0;font-family:serif'>🌿 Garden Calendar</h2>
            <p style='color:rgba(255,255,255,0.75);margin:0.5rem 0 0'>Accés restringit</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    col = st.columns([1,2,1])[1]
    with col:
        if st.button("🔑 Entrar amb Google", use_container_width=True, type="primary"):
            st.login("google")
    st.stop()

if st.user.email not in ALLOWED_EMAILS:
    st.error(f"❌ Accés no autoritzat: {st.user.email}")
    if st.button("Tancar sessió"):
        st.logout()
    st.stop()

# ── Google Drive config ───────────────────────────────────────────────────────
# Streamlit secrets:
#   [gdrive]
#   folder_id = "1ABCxyz..."
#   [gdrive.credentials]   ← paste full service account JSON fields here
#   type = "service_account"
#   project_id = "..."
#   private_key_id = "..."
#   private_key = "-----BEGIN RSA PRIVATE KEY-----\n..."
#   client_email = "...@....iam.gserviceaccount.com"
#   ... (rest of service account JSON)

DRIVE_OK = False
drive_service = None
FOLDER_ID = None

try:
    creds_dict  = dict(st.secrets["gdrive"]["credentials"])
    FOLDER_ID   = st.secrets["gdrive"]["folder_id"]
    creds = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
    DRIVE_OK = True
except Exception as e:
    pass

DATA_FILENAME = "garden_data.json"

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Source+Sans+3:wght@300;400;600&display=swap');

html, body, [class*="css"] { font-family: 'Source Sans 3', sans-serif; }
h1, h2, h3 { font-family: 'Playfair Display', serif !important; }

/* Mobile viewport fix */
.block-container { padding: 0.75rem 0.75rem 2rem !important; max-width: 100% !important; }
@media (min-width: 768px) { .block-container { padding: 1.5rem 2rem 2rem !important; max-width: 1200px !important; margin: auto; } }

.garden-header {
    background: linear-gradient(135deg, #2d5a27 0%, #4a7c59 60%, #6b9e6e 100%);
    padding: 1rem 1.25rem; border-radius: 12px; margin-bottom: 1rem; color: white;
}
.garden-header h1 { color: white !important; font-size: 1.6rem; margin: 0; }
.garden-header p  { color: rgba(255,255,255,0.75); margin: 0.15rem 0 0; font-size: 0.85rem; }

/* Calendar grid */
.cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 3px; }
.cal-header-cell {
    text-align: center; font-size: 0.6rem; font-weight: 700;
    text-transform: uppercase; color: #6b9e6e; padding: 3px 0 5px;
}
.cal-cell {
    background: #f8faf8; border: 1px solid #e4edd4;
    border-radius: 6px; min-height: 60px; padding: 4px 3px;
}
.cal-cell.empty   { background: transparent; border-color: transparent; }
.cal-cell.today   { background: #eaf4e8; border: 2px solid #4a7c59; }
.cal-cell.has-ev  { background: #fffbf5; }
.cal-day-num { font-size: 0.75rem; font-weight: 700; color: #2d5a27; margin-bottom: 2px; }
.cal-cell.today .cal-day-num { color: #4a7c59; }

.pill {
    display: block; font-size: 0.55rem; font-weight: 600;
    padding: 1px 4px; border-radius: 3px; margin-bottom: 2px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    line-height: 1.5;
}
.pill-treatment { background: #d4edda; color: #155724; }
.pill-poda      { background: #cfe2ff; color: #084298; }
.pill-overdue   { background: #f8d7da; color: #721c24; }
.pill-oneoff    { background: #fff3cd; color: #664d03; }

/* Agenda list (mobile calendar) */
.agenda-day {
    border-left: 3px solid #4a7c59; padding: 6px 10px;
    margin-bottom: 8px; background: #f8faf8; border-radius: 0 8px 8px 0;
}
.agenda-day.today-agenda { border-left-color: #d4956a; background: #fffbf5; }
.agenda-date { font-size: 0.75rem; font-weight: 700; color: #2d5a27; }
.agenda-item { font-size: 0.82rem; color: #444; padding: 2px 0; }

/* Treatment cards (mobile) */
.t-card {
    background: white; border: 1px solid #e4edd4; border-radius: 10px;
    padding: 0.75rem 1rem; margin-bottom: 0.6rem;
}
.t-card-name { font-weight: 600; font-size: 0.95rem; color: #2d5a27; }
.t-card-meta { font-size: 0.78rem; color: #777; margin-top: 2px; }

.badge { display:inline-block; font-size:0.65rem; font-weight:600; padding:2px 8px; border-radius:20px; margin-left:4px; }
.badge-ok   { background:#d4edda; color:#155724; }
.badge-soon { background:#fff3cd; color:#856404; }
.badge-due  { background:#f8d7da; color:#721c24; }
.badge-none { background:#e9ecef; color:#495057; }

.section-title {
    font-family: 'Playfair Display', serif; font-size: 1rem;
    color: #2d5a27; border-bottom: 2px solid #d4edda;
    padding-bottom: 3px; margin: 0.8rem 0 0.5rem;
}

/* Sick plant highlight */
.sick-banner {
    background: #fff0f0; border: 1px solid #f5c6cb;
    border-radius: 8px; padding: 6px 12px; margin-bottom: 8px;
    color: #842029; font-size: 0.82rem; font-weight: 600;
}

/* Big touch buttons */
.stButton > button {
    border-radius: 8px !important;
    min-height: 2.2rem !important;
}
</style>
""", unsafe_allow_html=True)

# ── Detect mobile via screen width trick ─────────────────────────────────────
if "is_mobile" not in st.session_state:
    st.session_state.is_mobile = False

st.components.v1.html("""
<script>
const mobile = window.innerWidth < 768;
window.parent.postMessage({type: 'streamlit:setComponentValue', value: mobile}, '*');
</script>
""", height=0)

# Simpler fallback: use sidebar state as proxy, default True (mobile-first)
IS_MOBILE = st.session_state.get("is_mobile", True)

# ── Default data ──────────────────────────────────────────────────────────────
DEFAULT_DATA = {
    "products": [
        {"name": "Acetamiprid 20%", "type": "insecticida", "dose": "0.5g/L", "notes": "Sistémico. Plazo seguridad 14d.", "expiry": ""},
        {"name": "Aceite de Neem", "type": "fungicida/insecticida", "dose": "5ml/L", "notes": "Mezclar con jabón potásico.", "expiry": ""},
        {"name": "Jabón Potásico", "type": "adyuvante/insecticida", "dose": "15ml/L", "notes": "Emulsionante para neem.", "expiry": ""},
    ],
    "plants": [
        {
            "name": "Limonero", "emoji": "🍋", "location": "", "notes": "", "photo": "", "sick": False,
            "treatments": [
                {"name": "Acetamiprid",          "type": "periodic", "interval_days": 12,
                 "last_date": str(date.today() - timedelta(days=1))},
                {"name": "Neem + Jabon potasico", "type": "periodic", "interval_days": 15,
                 "last_date": None},
            ], "events": []
        },
        {
            "name": "Higuera", "emoji": "🌿", "location": "", "notes": "", "photo": "", "sick": False,
            "treatments": [
                {"name": "Neem + Jabon potasico", "type": "periodic", "interval_days": 15,
                 "last_date": str(date.today())},
            ], "events": []
        },
        {
            "name": "Cerezo", "emoji": "🍒", "location": "", "notes": "", "photo": "", "sick": False,
            "treatments": [
                {"name": "Neem + Jabon potasico", "type": "periodic", "interval_days": 15,
                 "last_date": None},
            ], "events": []
        },
    ]
}

# ── Google Drive helpers ──────────────────────────────────────────────────────
def drive_find_file(name, parent_id=None):
    """Returns file_id or None."""
    if not DRIVE_OK:
        return None
    parent = parent_id or FOLDER_ID
    q = f"name='{name}' and '{parent}' in parents and trashed=false"
    r = drive_service.files().list(q=q, fields="files(id,name)").execute()
    files = r.get("files", [])
    return files[0]["id"] if files else None

def drive_read_json(name):
    """Read a JSON file from Drive folder. Returns (dict, file_id) or (None, None)."""
    if not DRIVE_OK:
        return None, None
    fid = drive_find_file(name)
    if not fid:
        return None, None
    try:
        buf = io.BytesIO()
        req = drive_service.files().get_media(fileId=fid)
        dl  = MediaIoBaseDownload(buf, req)
        done = False
        while not done:
            _, done = dl.next_chunk()
        return json.loads(buf.getvalue().decode("utf-8")), fid
    except Exception:
        return None, None

def drive_write_json(name, data_dict, file_id=None):
    """Create or update a JSON file in Drive folder."""
    if not DRIVE_OK:
        return False
    content = json.dumps(data_dict, indent=2, ensure_ascii=False).encode("utf-8")
    try:
        if file_id:
            # Update existing file
            url = f"https://www.googleapis.com/upload/drive/v3/files/{file_id}?uploadType=media"
            creds = drive_service._http.credentials
            creds.refresh(GoogleRequest())
            headers = {
                "Authorization": f"Bearer {creds.token}",
                "Content-Type": "application/json",
            }
            r = requests.patch(url, headers=headers, data=content, timeout=15)
            return r.status_code == 200
        else:
            # Create new file
            meta = {"name": name, "parents": [FOLDER_ID]}
            url  = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
            creds = drive_service._http.credentials
            creds.refresh(GoogleRequest())
            headers = {"Authorization": f"Bearer {creds.token}"}
            files = {
                "metadata": ("metadata", json.dumps(meta), "application/json"),
                "file":     ("file", content, "application/json"),
            }
            r = requests.post(url, headers=headers, files=files, timeout=15)
            return r.status_code in (200, 201)
    except Exception as e:
        st.error(f"Error guardando datos: {e}")
        return False

def drive_delete_file(filename):
    """Delete a file from Drive folder."""
    if not DRIVE_OK:
        return False
    fid = drive_find_file(filename)
    if fid:
        try:
            drive_service.files().delete(fileId=fid).execute()
        except Exception:
            pass
    return True

# ── Data load / save ──────────────────────────────────────────────────────────
def load_data_cached():
    d, fid = drive_read_json(DATA_FILENAME)
    if d:
        try:
            d.setdefault("products", [])
            d.setdefault("zones", ["Jardí posterior", "Entrada jardí", "Passadís nord", "Passadís sud"])
            d.setdefault("plant_types", ["arbre", "arbust", "planta"])
            for p in d.get("plants", []):
                if p is None:
                    continue
                p.setdefault("events", [])
                p.setdefault("location", "")
                p.setdefault("notes", "")
                p.setdefault("photo", "")
                p.setdefault("photo_b64", "")
                p.setdefault("sick", False)
                p.setdefault("sick_name", "")
                p.setdefault("sick_date", "")
                p.setdefault("sick_end", "")
                p.setdefault("history", [])
                p.setdefault("zone", "")
                p.setdefault("plant_type", "")
                for t in p.get("treatments", []):
                    t.setdefault("type", "periodic")
            return d, fid
        except Exception as e:
            st.error(f"Error carregant dades: {e}")
    return DEFAULT_DATA, None

def save_data(data):
    _, fid = drive_read_json(DATA_FILENAME)
    ok = drive_write_json(DATA_FILENAME, data, file_id=fid)
    return ok

# ── Domain helpers ────────────────────────────────────────────────────────────
def next_date(last_date_str, interval):
    if not last_date_str:
        return None
    return date.fromisoformat(last_date_str) + timedelta(days=interval)

def status_label(nd):
    if nd is None:
        return "none", "Sin programar"
    delta = (nd - date.today()).days
    if delta < 0:  return "due",  f"Vencido ({abs(delta)}d)"
    if delta == 0: return "due",  "Hoy"
    if delta <= 3: return "soon", f"En {delta}d"
    return "ok", f"En {delta}d"

def build_event_map(data, year, month):
    _, days_in_month = calendar.monthrange(year, month)
    first, last = date(year, month, 1), date(year, month, days_in_month)
    ev_map = {}
    for plant in data["plants"]:
        label = f"{plant['emoji']} {plant['name']}"
        for t in plant["treatments"]:
            nd = next_date(t.get("last_date"), t["interval_days"])
            if nd is None:
                continue
            iv = t["interval_days"]
            d = nd
            while d <= last:
                if d >= first:
                    ev_map.setdefault(d, []).append({"label": f"{label}: {t['name']}", "kind": "treatment", "overdue": d < date.today()})
                d += timedelta(days=iv)
            d = nd - timedelta(days=iv)
            while d >= first:
                ev_map.setdefault(d, []).append({"label": f"{label}: {t['name']}", "kind": "treatment", "overdue": d < date.today()})
                d -= timedelta(days=iv)
        for ev in plant.get("events", []):
            ev_date = date.fromisoformat(ev["date"])
            if first <= ev_date <= last:
                ev_map.setdefault(ev_date, []).append({"label": f"{label}: {ev['name']}", "kind": ev.get("kind", "oneoff"), "overdue": False})
    return ev_map

EMOJI_OPTIONS = {
    "🌱 Planta genérica": "🌱", "🍋 Limonero": "🍋", "🍊 Naranjo": "🍊",
    "🍒 Cerezo": "🍒", "🍎 Manzano": "🍎", "🍐 Peral": "🍐",
    "🍑 Melocotonero": "🍑", "🫒 Olivo": "🫒", "🌿 Higuera/arbusto": "🌿",
    "🌳 Árbol genérico": "🌳", "🌸 Frutal en flor": "🌸", "🥭 Mango": "🥭",
    "🍇 Vid/uva": "🍇", "🌵 Cactus": "🌵", "🪴 Maceta": "🪴",
    "🌺 Flor": "🌺", "🌻 Girasol": "🌻", "🍓 Fresón": "🍓", "🫐 Arándano": "🫐",
}
EMOJI_BY_VALUE = {v: k for k, v in EMOJI_OPTIONS.items()}

# ── Load ──────────────────────────────────────────────────────────────────────
if not DRIVE_OK:
    st.warning("⚠️ Google Drive no configurado. Añade los secrets en Streamlit Cloud. Usando datos de ejemplo.")

data, data_sha = load_data_cached()
if data is None:
    # Retry once — can happen right after OAuth redirect clears cache
    import time
    time.sleep(1)
    st.cache_data.clear()
    data, data_sha = load_data_cached()
if data is None:
    data = DEFAULT_DATA
today = date.today()

if "cal_year"  not in st.session_state: st.session_state.cal_year  = today.year
if "cal_month" not in st.session_state: st.session_state.cal_month = today.month

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="garden-header">
    <h1>🌿 Garden Calendar</h1>
    <p>{today.strftime("%A, %d de %B de %Y")}</p>
</div>
""", unsafe_allow_html=True)

# Logout button top right
with st.container():
    _, col_logout = st.columns([6,1])
    with col_logout:
        if st.button("↩ Sortir"):
            st.logout()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_today, tab_cal, tab_plants, tab_add = st.tabs(["🏠 Hoy", "📅 Calendario", "🌱 Plantas", "➕ Añadir"])

# ════════════════════════════════════════════════════════════════════════════
# TAB 0 — HOY
# ════════════════════════════════════════════════════════════════════════════
with tab_today:
    st.markdown(f"### {today.strftime('%A %d de %B').capitalize()}")

    # ── Plantas enfermas ─────────────────────────────────────────────────
    sick_plants = [p for p in data["plants"] if p.get("sick")]
    if sick_plants:
        st.markdown('<div class="sick-banner" style="margin-bottom:1rem">'
                    + "  ".join(f"🐛 {p['emoji']} {p['name']} — {p.get('sick_name') or 'plaga activa'}"
                                for p in sick_plants)
                    + '</div>', unsafe_allow_html=True)

    # ── Tratamientos de hoy y vencidos ───────────────────────────────────
    overdue, due_today, due_soon = [], [], []
    for plant in data["plants"]:
        for t in plant["treatments"]:
            nd = next_date(t.get("last_date"), t["interval_days"])
            if nd is None:
                continue
            delta = (nd - today).days
            entry = {"plant": plant, "treatment": t, "nd": nd, "delta": delta}
            if delta < 0:   overdue.append(entry)
            elif delta == 0: due_today.append(entry)
            elif delta <= 3: due_soon.append(entry)

    if not overdue and not due_today and not due_soon:
        st.success("✅ Todo al día — no hay tratamientos pendientes ni próximos.")
    else:
        def render_today_treatment(entry, pi_lookup):
            p, t, nd, delta = entry["plant"], entry["treatment"], entry["nd"], entry["delta"]
            pi = pi_lookup[p["name"]]
            ti = p["treatments"].index(t)
            if delta < 0:
                badge = f'<span class="badge badge-due">Vencido {abs(delta)}d</span>'
            elif delta == 0:
                badge = '<span class="badge badge-due">Hoy</span>'
            else:
                badge = f'<span class="badge badge-soon">En {delta}d</span>'
            st.markdown(f"""
            <div class="t-card">
                <div class="t-card-name">{p['emoji']} {p['name']} — {t['name']} {badge}</div>
                <div class="t-card-meta">Próxima: {nd}</div>
            </div>""", unsafe_allow_html=True)
            with st.popover("✓ Registrar aplicación", use_container_width=True):
                apply_date  = st.date_input("Fecha", value=today, key=f"td_date_{pi}_{ti}")
                apply_notes = st.text_input("Notas", key=f"td_notes_{pi}_{ti}", placeholder="opcional")
                if st.button("💾 Guardar", key=f"td_save_{pi}_{ti}"):
                    data["plants"][pi]["treatments"][ti]["last_date"] = str(apply_date)
                    data["plants"][pi].setdefault("history", []).append({
                        "kind": "treatment", "name": t["name"],
                        "date": str(apply_date), "date_end": "", "notes": apply_notes.strip(),
                    })
                    with st.spinner("Guardando..."):
                        save_data(data)
                    st.rerun()

        pi_lookup = {p["name"]: i for i, p in enumerate(data["plants"])}

        if overdue:
            st.markdown('<div class="section-title">⚠️ Vencidos</div>', unsafe_allow_html=True)
            for entry in overdue:
                render_today_treatment(entry, pi_lookup)
        if due_today:
            st.markdown('<div class="section-title">📅 Hoy</div>', unsafe_allow_html=True)
            for entry in due_today:
                render_today_treatment(entry, pi_lookup)
        if due_soon:
            st.markdown('<div class="section-title">🔔 Próximos 3 días</div>', unsafe_allow_html=True)
            for entry in due_soon:
                render_today_treatment(entry, pi_lookup)

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — CALENDAR
# ════════════════════════════════════════════════════════════════════════════
with tab_cal:
    month_names = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
                   "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
    cy, cm = st.session_state.cal_year, st.session_state.cal_month

    # Navigation
    c_prev, c_title, c_next = st.columns([1, 4, 1])
    with c_prev:
        if st.button("◀", use_container_width=True):
            if cm == 1: st.session_state.cal_month = 12; st.session_state.cal_year -= 1
            else: st.session_state.cal_month -= 1
            st.rerun()
    with c_next:
        if st.button("▶", use_container_width=True):
            if cm == 12: st.session_state.cal_month = 1; st.session_state.cal_year += 1
            else: st.session_state.cal_month += 1
            st.rerun()
    with c_title:
        st.markdown(f"<h3 style='text-align:center;color:#2d5a27;margin:4px 0'>"
                    f"{month_names[cm-1]} {cy}</h3>", unsafe_allow_html=True)

    ev_map = build_event_map(data, cy, cm)

    # ── Mobile: agenda list ──────────────────────────────────────────────
    # ── Desktop: grid calendar ──────────────────────────────────────────
    # We render both and use CSS to show/hide based on screen width
    # Agenda (mobile)
    agenda_html = ""
    _, days_in_month = calendar.monthrange(cy, cm)
    for day in range(1, days_in_month + 1):
        d = date(cy, cm, day)
        events = ev_map.get(d, [])
        if not events and d != today:
            continue
        is_today = d == today
        day_class = "agenda-day today-agenda" if is_today else "agenda-day"
        items_html = ""
        for ev in events:
            icon = "✂️" if ev["kind"] == "poda" else ("🔴" if ev["overdue"] else ("🟢" if ev["kind"] == "treatment" else "📌"))
            items_html += f'<div class="agenda-item">{icon} {ev["label"]}</div>'
        day_label = f"{'⭐ ' if is_today else ''}{d.strftime('%a %d').capitalize()}"
        agenda_html += f'<div class="{day_class}"><div class="agenda-date">{day_label}</div>{items_html}</div>'

    if not agenda_html:
        agenda_html = "<p style='color:#aaa;font-size:0.85rem'>Sin eventos este mes.</p>"

    # Grid calendar (desktop)
    day_headers = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]
    header_html = "".join(f'<div class="cal-header-cell">{d}</div>' for d in day_headers)
    cells_html = ""
    for week in calendar.monthcalendar(cy, cm):
        for day in week:
            if day == 0:
                cells_html += '<div class="cal-cell empty"></div>'; continue
            d = date(cy, cm, day)
            events = ev_map.get(d, [])
            cls = "cal-cell" + (" today" if d == today else "") + (" has-ev" if events else "")
            pills = ""
            for ev in events[:3]:
                pc = "pill-poda" if ev["kind"]=="poda" else ("pill-overdue" if ev["overdue"] else ("pill-oneoff" if ev["kind"]=="oneoff" else "pill-treatment"))
                safe = ev["label"].replace('"','&quot;')
                pills += f'<span class="pill {pc}" title="{safe}">{ev["label"]}</span>'
            if len(events) > 3:
                pills += f'<span class="pill" style="background:#eee;color:#666">+{len(events)-3}</span>'
            cells_html += f'<div class="{cls}"><div class="cal-day-num">{day}</div>{pills}</div>'

    st.markdown(f"""
    <style>
    .cal-wrap  {{ display:none }}
    .agenda-wrap {{ display:block }}
    @media (min-width: 640px) {{
        .cal-wrap {{ display:block }}
        .agenda-wrap {{ display:none }}
    }}
    </style>
    <div class="agenda-wrap">{agenda_html}</div>
    <div class="cal-wrap"><div class="cal-grid">{header_html}{cells_html}</div></div>
    <div style='margin-top:0.8rem;display:flex;gap:10px;flex-wrap:wrap;font-size:0.72rem'>
        <span style='background:#d4edda;padding:2px 7px;border-radius:3px;color:#155724'>■ Tratamiento</span>
        <span style='background:#cfe2ff;padding:2px 7px;border-radius:3px;color:#084298'>■ Poda</span>
        <span style='background:#fff3cd;padding:2px 7px;border-radius:3px;color:#664d03'>■ Puntual</span>
        <span style='background:#f8d7da;padding:2px 7px;border-radius:3px;color:#721c24'>■ Vencido</span>
    </div>
    """, unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — PLANTS
# ════════════════════════════════════════════════════════════════════════════
with tab_plants:
    zones      = data.get("zones", [])
    ptypes     = data.get("plant_types", [])

    # ── Filters ──────────────────────────────────────────────────────────
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        flt_zone  = st.selectbox("Zona", ["Totes"] + zones, key="flt_zone")
    with fc2:
        flt_type  = st.selectbox("Tipus", ["Tots"] + ptypes, key="flt_type")
    with fc3:
        flt_sick  = st.checkbox("Només amb plaga", key="flt_sick")

    filtered_plants = [
        (pi, p) for pi, p in enumerate(data["plants"])
        if (flt_zone == "Totes" or p.get("zone") == flt_zone)
        and (flt_type == "Tots" or p.get("plant_type") == flt_type)
        and (not flt_sick or p.get("sick"))
    ]

    if not filtered_plants:
        st.caption("Cap planta amb aquests filtres.")

    for pi, plant in filtered_plants:
        is_sick = plant.get("sick", False)
        zone_tag = f" · {plant.get('zone')}" if plant.get("zone") else ""
        type_tag = f" · {plant.get('plant_type')}" if plant.get("plant_type") else ""
        label    = f"{'🐛 ' if is_sick else ''}{plant['emoji']} {plant['name']}{zone_tag}{type_tag}"
        with st.expander(label, expanded=False):

            # ── Plaga / enfermedad ───────────────────────────────────────
            sick_checked = st.checkbox("🐛 Plaga / enfermedad activa", value=is_sick, key=f"sick_{pi}")
            if sick_checked != is_sick:
                data["plants"][pi]["sick"] = sick_checked
                if not sick_checked:
                    data["plants"][pi]["sick_name"] = ""
                    data["plants"][pi]["sick_date"] = ""
                    data["plants"][pi]["sick_end"]  = ""
                with st.spinner("Guardando..."):
                    save_data(data)
                st.rerun()

            if is_sick:
                sc1, sc2, sc3 = st.columns(3)
                with sc1:
                    sick_name = st.text_input("Tipo de plaga / enfermedad",
                                              value=plant.get("sick_name", ""),
                                              placeholder="ej: Mosca blanca, Oidio...",
                                              key=f"sname_{pi}")
                with sc2:
                    sick_date_val = date.fromisoformat(plant["sick_date"]) if plant.get("sick_date") else today
                    sick_date = st.date_input("Fecha detección", value=sick_date_val, key=f"sdate_{pi}")
                with sc3:
                    sick_end = st.date_input("Fecha fin (opcional)", value=None, key=f"send_{pi}")

                col_save, col_close = st.columns(2)
                with col_save:
                    if st.button("💾 Guardar plaga", key=f"ssave_{pi}"):
                        data["plants"][pi]["sick_name"] = sick_name.strip()
                        data["plants"][pi]["sick_date"] = str(sick_date)
                        with st.spinner("Guardando..."):
                            save_data(data)
                        st.rerun()
                with col_close:
                    if st.button("✅ Cerrar plaga", key=f"sclose_{pi}", help="Archiva en historial y desactiva"):
                        if sick_name.strip() or plant.get("sick_name"):
                            entry = {
                                "kind":      "plaga",
                                "name":      (sick_name.strip() or plant.get("sick_name", "Plaga")),
                                "date":      str(sick_date) if sick_name else plant.get("sick_date", str(today)),
                                "date_end":  str(sick_end) if sick_end else str(today),
                                "notes":     "",
                            }
                            data["plants"][pi].setdefault("history", []).append(entry)
                        data["plants"][pi]["sick"]      = False
                        data["plants"][pi]["sick_name"] = ""
                        data["plants"][pi]["sick_date"] = ""
                        data["plants"][pi]["sick_end"]  = ""
                        with st.spinner("Archivando..."):
                            save_data(data)
                        st.rerun()

                sname_txt = plant.get("sick_name") or "sin especificar"
                sdate_txt = plant.get("sick_date") or "—"
                st.markdown(f'<div class="sick-banner">⚠️ {sname_txt} · detectado: {sdate_txt}</div>',
                            unsafe_allow_html=True)

            # Photo + meta
            photo_b64 = plant.get("photo_b64", "")
            photo_url = f"data:image/jpeg;base64,{photo_b64}" if photo_b64 else None
            col_photo, col_meta = st.columns([1, 3])
            with col_photo:
                if photo_url:
                    st.image(photo_url, use_container_width=True)
                else:
                    st.markdown("<div style='background:#f0f4f0;border:1px dashed #b0c8b0;border-radius:8px;"
                                "height:80px;display:flex;align-items:center;justify-content:center;"
                                "color:#ccc;font-size:1.8rem'>🌿</div>", unsafe_allow_html=True)
            with col_meta:
                if plant.get("zone") or plant.get("plant_type"):
                    tags = " · ".join(filter(None, [plant.get("zone"), plant.get("plant_type")]))
                    st.markdown(f"🏷️ {tags}")
                if plant.get("location"):
                    st.markdown(f"📍 **{plant['location']}**")
                if plant.get("notes"):
                    st.markdown(f"_{plant['notes']}_")
                if not any([plant.get("zone"), plant.get("plant_type"), plant.get("location"), plant.get("notes")]):
                    st.caption("Sense ubicació ni notes.")

            # Edit popover
            with st.popover("✏️ Editar planta"):
                e_name  = st.text_input("Nom", value=plant["name"], key=f"en_{pi}")
                cur_lbl = EMOJI_BY_VALUE.get(plant["emoji"], list(EMOJI_OPTIONS.keys())[0])
                e_emoji = EMOJI_OPTIONS[st.selectbox("Icona", list(EMOJI_OPTIONS.keys()),
                          index=list(EMOJI_OPTIONS.keys()).index(cur_lbl), key=f"ee_{pi}")]

                ez1, ez2 = st.columns(2)
                with ez1:
                    zone_opts  = [""] + zones
                    zone_idx   = zone_opts.index(plant.get("zone","")) if plant.get("zone","") in zone_opts else 0
                    e_zone     = st.selectbox("Zona", zone_opts, index=zone_idx, key=f"ez_{pi}")
                with ez2:
                    type_opts  = [""] + ptypes
                    type_idx   = type_opts.index(plant.get("plant_type","")) if plant.get("plant_type","") in type_opts else 0
                    e_ptype    = st.selectbox("Tipus", type_opts, index=type_idx, key=f"ept_{pi}")

                e_loc   = st.text_input("Ubicació", value=plant.get("location",""), key=f"el_{pi}")
                e_notes = st.text_area("Notes", value=plant.get("notes",""), key=f"eno_{pi}", height=70)

                st.markdown("**Foto**")
                uploaded = st.file_uploader("Subir foto", type=["jpg","jpeg","png","webp"], key=f"up_{pi}")
                if uploaded:
                    raw     = uploaded.read()
                    b64_str = base64.b64encode(raw).decode("utf-8")
                    data["plants"][pi]["photo"]     = uploaded.name
                    data["plants"][pi]["photo_b64"] = b64_str
                    with st.spinner("Guardando foto..."):
                        save_data(data)
                    st.success("✅ Foto guardada")

                if plant.get("photo_b64"):
                    st.caption(f"Foto: {plant.get('photo','')}")
                    if st.button("🗑 Eliminar foto", key=f"dph_{pi}"):
                        data["plants"][pi]["photo"]     = ""
                        data["plants"][pi]["photo_b64"] = ""
                        with st.spinner("Eliminando..."):
                            save_data(data)
                        st.rerun()

                cs, cd = st.columns(2)
                with cs:
                    if st.button("💾 Guardar", key=f"sp_{pi}"):
                        data["plants"][pi].update({
                            "name": e_name.strip(), "emoji": e_emoji,
                            "location": e_loc.strip(), "notes": e_notes.strip(),
                            "zone": e_zone, "plant_type": e_ptype,
                        })
                        with st.spinner("Guardant..."):
                            save_data(data)
                        st.success("✅ Guardat")
                with cd:
                    if st.button("🗑 Eliminar", key=f"dp_{pi}", type="primary"):
                        data["plants"].pop(pi)
                        with st.spinner("Eliminando..."):
                            save_data(data)
                        st.rerun()

            # Treatments
            if plant["treatments"]:
                st.markdown('<div class="section-title">Tratamientos periódicos</div>', unsafe_allow_html=True)
                for ti, t in enumerate(plant["treatments"]):
                    nd = next_date(t.get("last_date"), t["interval_days"])
                    st_code, st_lbl = status_label(nd)
                    badge_cls = {"ok":"badge-ok","soon":"badge-soon","due":"badge-due","none":"badge-none"}[st_code]

                    st.markdown(f"""
                    <div class="t-card">
                        <div class="t-card-name">{t['name']} <span class="badge {badge_cls}">{st_lbl}</span></div>
                        <div class="t-card-meta">Última: {t.get('last_date') or '—'} &nbsp;·&nbsp; Próxima: {nd or '—'} &nbsp;·&nbsp; c/{t['interval_days']}d</div>
                    </div>
                    """, unsafe_allow_html=True)

                    cb1, cb2, cb3 = st.columns(3)
                    with cb1:
                        with st.popover("✓ Hecho", use_container_width=True):
                            apply_date = st.date_input("Fecha de aplicación", value=today, key=f"apdate_{pi}_{ti}")
                            apply_notes = st.text_input("Notas (opcional)", key=f"apnotes_{pi}_{ti}", placeholder="ej: dosis reducida")
                            if st.button("💾 Registrar", key=f"done_{pi}_{ti}", use_container_width=True):
                                data["plants"][pi]["treatments"][ti]["last_date"] = str(apply_date)
                                data["plants"][pi].setdefault("history", []).append({
                                    "kind":     "treatment",
                                    "name":     t["name"],
                                    "date":     str(apply_date),
                                    "date_end": "",
                                    "notes":    apply_notes.strip(),
                                })
                                with st.spinner("Guardando..."):
                                    save_data(data)
                                st.rerun()
                    with cb2:
                        with st.popover("✏️ Editar", use_container_width=True):
                            et_name = st.text_input("Nombre", value=t["name"], key=f"etn_{pi}_{ti}")
                            et_int  = st.number_input("Intervalo (días)", 1, 365, t["interval_days"], key=f"eti_{pi}_{ti}")
                            last_v  = date.fromisoformat(t["last_date"]) if t.get("last_date") else None
                            et_last = st.date_input("Última aplicación", value=last_v, key=f"etl_{pi}_{ti}")
                            if st.button("💾 Guardar", key=f"ets_{pi}_{ti}"):
                                data["plants"][pi]["treatments"][ti].update({
                                    "name": et_name.strip(), "interval_days": int(et_int),
                                    "last_date": str(et_last) if et_last else None
                                })
                                with st.spinner("Guardando..."):
                                    save_data(data)
                                st.rerun()
                    with cb3:
                        if st.button("🗑 Eliminar", key=f"dt_{pi}_{ti}", use_container_width=True):
                            data["plants"][pi]["treatments"].pop(ti)
                            with st.spinner("Eliminando..."):
                                save_data(data)
                            st.rerun()
            else:
                st.caption("Sin tratamientos. Añade uno desde ➕ Añadir.")

            # One-off events
            events   = plant.get("events", [])
            upcoming = sorted([e for e in events if date.fromisoformat(e["date"]) >= today], key=lambda x: x["date"])
            past     = sorted([e for e in events if date.fromisoformat(e["date"]) < today],  key=lambda x: x["date"], reverse=True)

            if upcoming:
                st.markdown('<div class="section-title">Eventos planificados</div>', unsafe_allow_html=True)
                for ev in upcoming:
                    ri = events.index(ev)
                    icon = "✂️" if ev.get("kind") == "poda" else "📌"
                    c1, c2, c3 = st.columns([4, 1, 1])
                    with c1: st.markdown(f"{icon} **{ev['name']}** · {ev['date']}")
                    with c2:
                        with st.popover("✏️"):
                            ee_n = st.text_input("Desc.", value=ev["name"], key=f"een_{pi}_{ri}")
                            ee_k = st.selectbox("Tipo", ["poda","oneoff"],
                                                index=["poda","oneoff"].index(ev.get("kind","oneoff")),
                                                key=f"eek_{pi}_{ri}")
                            ee_d = st.date_input("Fecha", value=date.fromisoformat(ev["date"]), key=f"eed_{pi}_{ri}")
                            if st.button("💾 Guardar", key=f"ees_{pi}_{ri}"):
                                data["plants"][pi]["events"][ri].update({"name": ee_n.strip(), "kind": ee_k, "date": str(ee_d)})
                                with st.spinner("Guardando..."):
                                    save_data(data)
                                st.rerun()
                    with c3:
                        if st.button("🗑", key=f"de_{pi}_{ri}"):
                            data["plants"][pi]["events"].pop(ri)
                            with st.spinner("Eliminando..."):
                                save_data(data)
                            st.rerun()

            # ── Historial ────────────────────────────────────────────────
            # Manual entry
            with st.popover("➕ Añadir entrada al historial"):
                he_kind  = st.selectbox("Tipo", ["poda","treatment","plaga","oneoff"],
                                        format_func=lambda x: {"poda":"✂️ Poda","treatment":"💊 Tratamiento","plaga":"🐛 Plaga","oneoff":"📌 Otro"}[x],
                                        key=f"he_kind_{pi}")
                he_name  = st.text_input("Descripción", key=f"he_name_{pi}", placeholder="ej: Poda de verano")
                he_date  = st.date_input("Fecha", value=today, key=f"he_date_{pi}")
                he_end   = st.date_input("Fecha fin (opcional)", value=None, key=f"he_end_{pi}")
                he_notes = st.text_input("Notas", key=f"he_notes_{pi}", placeholder="opcional")
                if st.button("💾 Guardar entrada", key=f"he_save_{pi}"):
                    if he_name.strip():
                        data["plants"][pi].setdefault("history", []).append({
                            "kind": he_kind, "name": he_name.strip(),
                            "date": str(he_date),
                            "date_end": str(he_end) if he_end else "",
                            "notes": he_notes.strip(),
                        })
                        with st.spinner("Guardando..."):
                            save_data(data)
                        st.rerun()
                    else:
                        st.warning("Escribe una descripción.")

            # Build unified history from: past events + plant.history entries
            # Mark which entries are native (editable) vs from events (read-only)
            history_entries = []
            for hi, e in enumerate(plant.get("history", [])):
                history_entries.append({**e, "_src": "history", "_idx": hi})
            for ev in plant.get("events", []):
                if date.fromisoformat(ev["date"]) < today:
                    history_entries.append({
                        "kind": ev.get("kind", "oneoff"), "name": ev["name"],
                        "date": ev["date"], "date_end": "", "notes": "",
                        "_src": "event",
                    })

            if history_entries:
                st.markdown('<div class="section-title">Historial</div>', unsafe_allow_html=True)

                # Type filter
                all_kinds   = sorted({e.get("kind","oneoff") for e in history_entries})
                kind_labels = {"poda":"✂️ Poda","plaga":"🐛 Plaga","oneoff":"📌 Evento","treatment":"💊 Tratamiento"}
                filter_opts = ["Todos"] + [kind_labels.get(k, k) for k in all_kinds]
                sel_filter  = st.selectbox("Filtrar por tipo", filter_opts, key=f"hfilter_{pi}")

                # Year grouping
                filtered = sorted(history_entries, key=lambda x: x["date"], reverse=True)
                if sel_filter != "Todos":
                    filtered = [e for e in filtered if kind_labels.get(e.get("kind","oneoff")) == sel_filter]

                years = sorted({e["date"][:4] for e in filtered}, reverse=True)
                for year in years:
                    year_entries = [e for e in filtered if e["date"].startswith(year)]
                    st.markdown(f"**{year}** · {len(year_entries)} entradas")
                    for e in year_entries:
                        icon     = kind_labels.get(e.get("kind","oneoff"), "📌")
                        date_str = e["date"] + (f" → {e['date_end']}" if e.get("date_end") else "")
                        notes_str = f" · _{e['notes']}_" if e.get("notes") else ""

                        if e["_src"] == "history":
                            hi = e["_idx"]
                            hc1, hc2, hc3 = st.columns([6, 1, 1])
                            with hc1:
                                st.caption(f"{icon} {date_str} — {e['name']}{notes_str}")
                            with hc2:
                                with st.popover("✏️"):
                                    he_kind  = st.selectbox("Tipo", ["poda","treatment","plaga","oneoff"],
                                                            format_func=lambda x: kind_labels.get(x, x),
                                                            index=["poda","treatment","plaga","oneoff"].index(e.get("kind","oneoff")),
                                                            key=f"eh_kind_{pi}_{hi}")
                                    he_name  = st.text_input("Descripción", value=e["name"], key=f"eh_name_{pi}_{hi}")
                                    he_date  = st.date_input("Fecha", value=date.fromisoformat(e["date"]), key=f"eh_date_{pi}_{hi}")
                                    he_end   = st.date_input("Fecha fin", value=date.fromisoformat(e["date_end"]) if e.get("date_end") else None, key=f"eh_end_{pi}_{hi}")
                                    he_notes = st.text_input("Notas", value=e.get("notes",""), key=f"eh_notes_{pi}_{hi}")
                                    if st.button("💾 Guardar", key=f"eh_save_{pi}_{hi}"):
                                        data["plants"][pi]["history"][hi].update({
                                            "kind": he_kind, "name": he_name.strip(),
                                            "date": str(he_date),
                                            "date_end": str(he_end) if he_end else "",
                                            "notes": he_notes.strip(),
                                        })
                                        with st.spinner("Guardando..."):
                                            save_data(data)
                                        st.rerun()
                            with hc3:
                                if st.button("🗑", key=f"eh_del_{pi}_{hi}"):
                                    data["plants"][pi]["history"].pop(hi)
                                    with st.spinner("Eliminando..."):
                                        save_data(data)
                                    st.rerun()
                        else:
                            st.caption(f"{icon} {date_str} — {e['name']}{notes_str}")

# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — ADD
# ════════════════════════════════════════════════════════════════════════════
with tab_add:
    plant_names = [p["name"] for p in data["plants"]]

    st.markdown("#### ✂️ Poda o evento puntual")
    sel_p   = st.selectbox("Planta", plant_names, key="ev_plant")
    ev_name = st.text_input("Descripción", key="ev_name", placeholder="ej: Poda de formación")
    ev_kind = st.selectbox("Tipo", ["poda", "tratamiento puntual", "otro"], key="ev_kind")
    ev_date = st.date_input("Fecha", value=today, key="ev_date")
    if st.button("Añadir evento", use_container_width=True):
        if ev_name:
            idx = plant_names.index(sel_p)
            km  = {"poda":"poda","tratamiento puntual":"oneoff","otro":"oneoff"}
            data["plants"][idx]["events"].append({"name": ev_name, "date": str(ev_date), "kind": km[ev_kind]})
            with st.spinner("Guardando..."):
                save_data(data)
            st.success(f"Evento añadido a {sel_p}")
            st.rerun()

    st.markdown("---")
    st.markdown("#### 🔄 Tratamiento periódico")
    sel_p2     = st.selectbox("Planta", plant_names, key="t_plant")
    # Product selector from catalog
    prod_names = [p["name"] for p in data.get("products", [])]
    if prod_names:
        use_catalog = st.checkbox("Seleccionar del catálogo", key="t_use_catalog")
        if use_catalog:
            sel_prod = st.selectbox("Producto", prod_names, key="t_prod_sel")
            t_name   = sel_prod
            prod_obj = next((p for p in data["products"] if p["name"] == sel_prod), {})
            if prod_obj.get("dose"):
                st.caption(f"Dosis: {prod_obj['dose']}  ·  {prod_obj.get('notes','')}")
        else:
            t_name = st.text_input("Nombre del tratamiento", key="t_name")
    else:
        t_name = st.text_input("Nombre del tratamiento", key="t_name")
    t_interval = st.number_input("Intervalo (días)", 1, 365, 15, key="t_interval")
    t_last     = st.date_input("Última aplicación (opcional)", value=None, key="t_last")
    if st.button("Añadir tratamiento", use_container_width=True):
        if t_name:
            idx = plant_names.index(sel_p2)
            data["plants"][idx]["treatments"].append({
                "name": t_name, "type": "periodic",
                "interval_days": int(t_interval),
                "last_date": str(t_last) if t_last else None,
            })
            with st.spinner("Guardando..."):
                save_data(data)
            st.success(f"Tratamiento añadido a {sel_p2}")
            st.rerun()

    st.markdown("---")
    st.markdown("#### 🌳 Nova planta")
    new_p_name     = st.text_input("Nom", key="new_p_name", placeholder="ej: Olivera")
    nz1, nz2      = st.columns(2)
    with nz1:
        new_p_zone  = st.selectbox("Zona", [""] + data.get("zones", []), key="new_p_zone")
    with nz2:
        new_p_ptype = st.selectbox("Tipus", [""] + data.get("plant_types", []), key="new_p_ptype")
    new_p_location = st.text_input("Ubicació (opcional)", key="new_p_loc", placeholder="ej: Racó nord")
    emoji_label    = st.selectbox("Icona", list(EMOJI_OPTIONS.keys()), key="new_p_emoji")
    new_p_emoji    = EMOJI_OPTIONS[emoji_label]
    new_p_notes    = st.text_area("Notes (opcional)", key="new_p_notes", placeholder="varietat, any...", height=70)
    if st.button("Afegir planta", type="primary", use_container_width=True):
        if new_p_name.strip():
            data["plants"].append({
                "name": new_p_name.strip(), "emoji": new_p_emoji,
                "location": new_p_location.strip(), "notes": new_p_notes.strip(),
                "zone": new_p_zone, "plant_type": new_p_ptype,
                "photo": "", "photo_b64": "", "treatments": [], "events": [],
                "sick": False, "sick_name": "", "sick_date": "", "sick_end": "", "history": []
            })
            with st.spinner("Guardant..."):
                save_data(data)
            st.success(f"{new_p_emoji} '{new_p_name}' afegit")
            st.rerun()
        else:
            st.warning("Escriu un nom.")

    # ════════════════════════════════════════════════════════════════════
    # CATÁLOGO DE PRODUCTOS
    # ════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("#### 🧪 Catálogo de productos")

    products = data.get("products", [])
    if products:
        for pri, prod in enumerate(products):
            with st.expander(f"🧪 {prod['name']} · {prod.get('type','')}"):
                pc1, pc2 = st.columns(2)
                with pc1:
                    st.markdown(f"**Dosis:** {prod.get('dose') or '—'}")
                    st.markdown(f"**Caducidad:** {prod.get('expiry') or '—'}")
                with pc2:
                    st.markdown(f"**Notas:** {prod.get('notes') or '—'}")
                with st.popover("✏️ Editar"):
                    ep_name   = st.text_input("Nombre", value=prod["name"], key=f"ep_name_{pri}")
                    ep_type   = st.text_input("Tipo", value=prod.get("type",""), key=f"ep_type_{pri}",
                                              placeholder="ej: insecticida, fungicida...")
                    ep_dose   = st.text_input("Dosis recomendada", value=prod.get("dose",""), key=f"ep_dose_{pri}",
                                              placeholder="ej: 5ml/L")
                    ep_expiry = st.text_input("Caducidad del bote", value=prod.get("expiry",""), key=f"ep_exp_{pri}",
                                              placeholder="ej: 2027-06")
                    ep_notes  = st.text_area("Notas", value=prod.get("notes",""), key=f"ep_notes_{pri}", height=70)
                    es1, es2  = st.columns(2)
                    with es1:
                        if st.button("💾 Guardar", key=f"ep_save_{pri}"):
                            data["products"][pri].update({
                                "name": ep_name.strip(), "type": ep_type.strip(),
                                "dose": ep_dose.strip(), "expiry": ep_expiry.strip(),
                                "notes": ep_notes.strip()
                            })
                            with st.spinner("Guardando..."):
                                save_data(data)
                            st.rerun()
                    with es2:
                        if st.button("🗑 Eliminar", key=f"ep_del_{pri}", type="primary"):
                            data["products"].pop(pri)
                            with st.spinner("Eliminando..."):
                                save_data(data)
                            st.rerun()
    else:
        st.caption("Sin productos. Añade uno a continuación.")

    st.markdown("##### Añadir producto")
    np1, np2 = st.columns(2)
    with np1:
        new_prod_name  = st.text_input("Nombre del producto", key="np_name", placeholder="ej: Aceite de Neem")
        new_prod_dose  = st.text_input("Dosis", key="np_dose", placeholder="ej: 5ml/L")
    with np2:
        new_prod_type  = st.text_input("Tipo", key="np_type", placeholder="ej: insecticida")
        new_prod_exp   = st.text_input("Caducidad", key="np_exp", placeholder="ej: 2027-06")
    new_prod_notes = st.text_area("Notas", key="np_notes", placeholder="plazo seguridad, observaciones...", height=68)
    if st.button("Añadir producto", use_container_width=True):
        if new_prod_name.strip():
            data.setdefault("products", []).append({
                "name": new_prod_name.strip(), "type": new_prod_type.strip(),
                "dose": new_prod_dose.strip(), "expiry": new_prod_exp.strip(),
                "notes": new_prod_notes.strip()
            })
            with st.spinner("Guardando..."):
                save_data(data)
            st.success(f"Producto '{new_prod_name}' añadido")
            st.rerun()
        else:
            st.warning("Escribe un nombre.")