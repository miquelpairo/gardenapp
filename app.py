import streamlit as st
import json
import base64
import calendar
import requests
from datetime import date, timedelta

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Garden Calendar", page_icon="🌿", layout="wide")

# ── GitHub config (from Streamlit secrets) ────────────────────────────────────
# In Streamlit Cloud, add these secrets:
#   [github]
#   token  = "ghp_xxxxxxxxxxxx"
#   repo   = "username/garden-app"      # same repo as the app
#   branch = "main"
try:
    GH_TOKEN  = st.secrets["github"]["token"]
    GH_REPO   = st.secrets["github"]["repo"]
    GH_BRANCH = st.secrets["github"].get("branch", "main")
    GH_HEADERS = {
        "Authorization": f"token {GH_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    GITHUB_OK = True
except Exception:
    GITHUB_OK = False

DATA_PATH   = "data/garden_data.json"
PHOTOS_PATH = "data/fotos"

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
    "plants": [
        {
            "name": "Limonero", "emoji": "🍋", "location": "", "notes": "", "photo": "",
            "treatments": [
                {"name": "Acetamiprid",          "type": "periodic", "interval_days": 12,
                 "last_date": str(date.today() - timedelta(days=1))},
                {"name": "Neem + Jabon potasico", "type": "periodic", "interval_days": 15,
                 "last_date": None},
            ], "events": []
        },
        {
            "name": "Higuera", "emoji": "🌿", "location": "", "notes": "", "photo": "",
            "treatments": [
                {"name": "Neem + Jabon potasico", "type": "periodic", "interval_days": 15,
                 "last_date": str(date.today())},
            ], "events": []
        },
        {
            "name": "Cerezo", "emoji": "🍒", "location": "", "notes": "", "photo": "",
            "treatments": [
                {"name": "Neem + Jabon potasico", "type": "periodic", "interval_days": 15,
                 "last_date": None},
            ], "events": []
        },
    ]
}

# ── GitHub helpers ────────────────────────────────────────────────────────────
def gh_get_file(path):
    """Returns (content_str, sha) or (None, None)"""
    if not GITHUB_OK:
        return None, None
    url = f"https://api.github.com/repos/{GH_REPO}/contents/{path}?ref={GH_BRANCH}"
    r = requests.get(url, headers=GH_HEADERS, timeout=10)
    if r.status_code == 200:
        data = r.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return content, data["sha"]
    return None, None

def gh_put_file(path, content_str, sha=None, message="Update garden data"):
    """Create or update a file on GitHub."""
    if not GITHUB_OK:
        return False
    url = f"https://api.github.com/repos/{GH_REPO}/contents/{path}"
    encoded = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
    payload = {"message": message, "content": encoded, "branch": GH_BRANCH}
    if sha:
        payload["sha"] = sha
    r = requests.put(url, headers=GH_HEADERS, json=payload, timeout=15)
    return r.status_code in (200, 201)

def gh_put_binary(path, raw_bytes, sha=None, message="Upload photo"):
    """Upload binary file (photo) to GitHub."""
    if not GITHUB_OK:
        return False
    url = f"https://api.github.com/repos/{GH_REPO}/contents/{path}"
    encoded = base64.b64encode(raw_bytes).decode("utf-8")
    payload = {"message": message, "content": encoded, "branch": GH_BRANCH}
    if sha:
        payload["sha"] = sha
    r = requests.put(url, headers=GH_HEADERS, json=payload, timeout=30)
    return r.status_code in (200, 201)

def gh_delete_file(path, sha, message="Delete photo"):
    if not GITHUB_OK:
        return False
    url = f"https://api.github.com/repos/{GH_REPO}/contents/{path}"
    payload = {"message": message, "sha": sha, "branch": GH_BRANCH}
    r = requests.delete(url, headers=GH_HEADERS, json=payload, timeout=10)
    return r.status_code == 200

def gh_raw_url(path):
    """Public raw URL for images."""
    return f"https://raw.githubusercontent.com/{GH_REPO}/{GH_BRANCH}/{path}"

# ── Data load / save ──────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def load_data_cached():
    content, sha = gh_get_file(DATA_PATH)
    if content:
        try:
            d = json.loads(content)
            for p in d.get("plants", []):
                p.setdefault("events", [])
                p.setdefault("location", "")
                p.setdefault("notes", "")
                p.setdefault("photo", "")
                for t in p.get("treatments", []):
                    t.setdefault("type", "periodic")
            return d, sha
        except Exception:
            pass
    return DEFAULT_DATA, None

def save_data(data):
    _, sha = gh_get_file(DATA_PATH)
    content_str = json.dumps(data, indent=2, ensure_ascii=False)
    ok = gh_put_file(DATA_PATH, content_str, sha=sha)
    if ok:
        st.cache_data.clear()
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
if not GITHUB_OK:
    st.warning("⚠️ GitHub no configurado. Añade los secrets en Streamlit Cloud. Usando datos de ejemplo.")

data, data_sha = load_data_cached()
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

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_cal, tab_plants, tab_add = st.tabs(["📅 Calendario", "🌱 Plantas", "➕ Añadir"])

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
    for pi, plant in enumerate(data["plants"]):
        with st.expander(f"{plant['emoji']} {plant['name']}", expanded=True):

            # Photo + meta
            photo_url = gh_raw_url(f"{PHOTOS_PATH}/{plant['photo']}") if plant.get("photo") else None
            col_photo, col_meta = st.columns([1, 3])
            with col_photo:
                if photo_url:
                    st.image(photo_url, use_container_width=True)
                else:
                    st.markdown("<div style='background:#f0f4f0;border:1px dashed #b0c8b0;border-radius:8px;"
                                "height:80px;display:flex;align-items:center;justify-content:center;"
                                "color:#ccc;font-size:1.8rem'>🌿</div>", unsafe_allow_html=True)
            with col_meta:
                if plant.get("location"):
                    st.markdown(f"📍 **{plant['location']}**")
                if plant.get("notes"):
                    st.markdown(f"_{plant['notes']}_")
                if not plant.get("location") and not plant.get("notes"):
                    st.caption("Sin ubicación ni notas.")

            # Edit popover
            with st.popover("✏️ Editar planta"):
                e_name  = st.text_input("Nombre", value=plant["name"], key=f"en_{pi}")
                cur_lbl = EMOJI_BY_VALUE.get(plant["emoji"], list(EMOJI_OPTIONS.keys())[0])
                e_emoji = EMOJI_OPTIONS[st.selectbox("Icono", list(EMOJI_OPTIONS.keys()),
                          index=list(EMOJI_OPTIONS.keys()).index(cur_lbl), key=f"ee_{pi}")]
                e_loc   = st.text_input("Ubicación", value=plant.get("location",""), key=f"el_{pi}")
                e_notes = st.text_area("Notas", value=plant.get("notes",""), key=f"eno_{pi}", height=70)

                st.markdown("**Foto**")
                uploaded = st.file_uploader("Subir foto", type=["jpg","jpeg","png","webp"], key=f"up_{pi}")
                if uploaded:
                    ext = uploaded.name.rsplit(".",1)[-1].lower()
                    fname = f"plant_{pi}_{plant['name'].replace(' ','_')}.{ext}"
                    _, old_sha = gh_get_file(f"{PHOTOS_PATH}/{fname}")
                    ok = gh_put_binary(f"{PHOTOS_PATH}/{fname}", uploaded.read(), sha=old_sha)
                    if ok:
                        data["plants"][pi]["photo"] = fname
                        st.success("Foto subida")

                if plant.get("photo"):
                    st.caption(f"Foto: {plant['photo']}")
                    if st.button("🗑 Eliminar foto", key=f"dph_{pi}"):
                        _, ph_sha = gh_get_file(f"{PHOTOS_PATH}/{plant['photo']}")
                        if ph_sha:
                            gh_delete_file(f"{PHOTOS_PATH}/{plant['photo']}", ph_sha)
                        data["plants"][pi]["photo"] = ""
                        save_data(data)
                        st.rerun()

                cs, cd = st.columns(2)
                with cs:
                    if st.button("💾 Guardar", key=f"sp_{pi}"):
                        data["plants"][pi].update({"name": e_name.strip(), "emoji": e_emoji,
                                                    "location": e_loc.strip(), "notes": e_notes.strip()})
                        with st.spinner("Guardando..."):
                            save_data(data)
                        st.rerun()
                with cd:
                    if st.button("🗑 Eliminar", key=f"dp_{pi}", type="primary"):
                        if plant.get("photo"):
                            _, ph_sha = gh_get_file(f"{PHOTOS_PATH}/{plant['photo']}")
                            if ph_sha: gh_delete_file(f"{PHOTOS_PATH}/{plant['photo']}", ph_sha)
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
                        if st.button("✓ Hecho", key=f"done_{pi}_{ti}", use_container_width=True):
                            data["plants"][pi]["treatments"][ti]["last_date"] = str(today)
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

            if past:
                st.markdown('<div class="section-title">Historial</div>', unsafe_allow_html=True)
                for ev in past[:10]:
                    icon = "✂️" if ev.get("kind") == "poda" else "📌"
                    st.caption(f"{icon} {ev['date']} — {ev['name']}")

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
    t_name     = st.text_input("Nombre del tratamiento", key="t_name")
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
    st.markdown("#### 🌳 Nueva planta")
    new_p_name     = st.text_input("Nombre", key="new_p_name", placeholder="ej: Olivo del jardín")
    new_p_location = st.text_input("Ubicación (opcional)", key="new_p_loc", placeholder="ej: Esquina norte")
    emoji_label    = st.selectbox("Icono", list(EMOJI_OPTIONS.keys()), key="new_p_emoji")
    new_p_emoji    = EMOJI_OPTIONS[emoji_label]
    new_p_notes    = st.text_area("Notas (opcional)", key="new_p_notes", placeholder="variedad, año...", height=70)
    if st.button("Añadir planta", type="primary", use_container_width=True):
        if new_p_name.strip():
            data["plants"].append({
                "name": new_p_name.strip(), "emoji": new_p_emoji,
                "location": new_p_location.strip(), "notes": new_p_notes.strip(),
                "photo": "", "treatments": [], "events": []
            })
            with st.spinner("Guardando..."):
                save_data(data)
            st.success(f"{new_p_emoji} '{new_p_name}' añadido")
            st.rerun()
        else:
            st.warning("Escribe un nombre.")