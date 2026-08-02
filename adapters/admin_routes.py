"""
adapters/admin_routes.py
--------------------------
Password-protected admin dashboard.

Shows summary stats, tickets (with reply/resolve), and recent tool
call activity — read-only view into the audit trail built up in
persistence/, plus the ability to act on tickets directly.

Auth: single shared admin password (via .env), session cookie based.
"""

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import URLSafeSerializer, BadSignature
import requests as http_requests

from config import settings
from persistence.queries import (
    get_summary_stats,
    get_all_tickets,
    get_ticket,
    get_ticket_messages,
    add_ticket_message,
    set_ticket_status,
    get_recent_tool_calls,
)
from logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

_serializer = URLSafeSerializer(settings.ADMIN_PASSWORD or "fallback-secret-change-me")
SESSION_COOKIE = "velvora_admin_session"


def _is_authenticated(request: Request) -> bool:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return False
    try:
        return _serializer.loads(token) == "authenticated"
    except BadSignature:
        return False


_BASE_STYLES = """
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@600;700;800&family=Inter:wght@400;500;600;700&display=swap');

:root {
    --v-navy: #101B2D;
    --v-navy-light: #1B2C45;
    --v-teal: #1FC6C6;
    --v-amber: #FF8F4D;
    --v-ice: #F5FAFB;
    --v-slate: #64748B;
    --v-border: #E2E8F0;
    --v-red: #E11D48;
    --v-green: #16A34A;
}
* { box-sizing: border-box; }
body { margin: 0; font-family: 'Inter', system-ui, sans-serif; background: var(--v-ice); color: #1E293B; }
.app { display: flex; min-height: 100vh; }
.sidebar {
    width: 230px; background: var(--v-navy); color: white; flex-shrink: 0;
    display: flex; flex-direction: column; padding: 24px 0; position: fixed; height: 100vh;
}
.sidebar-brand { display: flex; align-items: center; gap: 10px; padding: 0 20px 24px; }
.sidebar-mark { width: 34px; height: 34px; border-radius: 9px; background: rgba(255,255,255,0.1); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.sidebar-brand-text { font-family: 'Plus Jakarta Sans', sans-serif; font-weight: 700; font-size: 15px; }
.sidebar-brand-sub { font-size: 10.5px; color: rgba(255,255,255,0.5); margin-top: 1px; }
.nav-section { padding: 0 12px; margin-top: 8px; }
.nav-item {
    display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 8px;
    color: rgba(255,255,255,0.65); font-size: 13.5px; font-weight: 500; margin-bottom: 2px;
    text-decoration: none;
}
.nav-item.active { background: rgba(255,255,255,0.08); color: white; }
.nav-item:hover { background: rgba(255,255,255,0.06); color: white; }
.main { flex: 1; padding: 28px 36px; max-width: 1200px; margin-left: 230px; }
.topbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; }
.topbar h1 { font-family: 'Plus Jakarta Sans', sans-serif; font-size: 22px; margin: 0; }
.topbar p { color: var(--v-slate); font-size: 13px; margin: 2px 0 0; }
.topbar a { color: var(--v-slate); font-size: 13px; text-decoration: none; }
.stats-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 14px; margin-bottom: 28px; }
.stat-card { background: white; border-radius: 14px; padding: 18px; border: 1px solid var(--v-border); }
.stat-icon { width: 32px; height: 32px; border-radius: 9px; display: flex; align-items: center; justify-content: center; margin-bottom: 10px; font-size: 15px; }
.stat-number { font-family: 'Plus Jakarta Sans', sans-serif; font-size: 24px; font-weight: 800; color: var(--v-navy); }
.stat-label { font-size: 12px; color: var(--v-slate); margin-top: 2px; }
.card { background: white; border-radius: 14px; border: 1px solid var(--v-border); overflow: hidden; margin-bottom: 24px; }
.card-header { padding: 16px 20px; border-bottom: 1px solid var(--v-border); display: flex; justify-content: space-between; align-items: center; }
.card-header h2 { font-family: 'Plus Jakarta Sans', sans-serif; font-size: 15px; margin: 0; }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; padding: 10px 20px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.4px; color: var(--v-slate); background: var(--v-ice); font-weight: 600; }
td { padding: 12px 20px; font-size: 13px; border-top: 1px solid var(--v-border); }
tr:hover td { background: #FAFBFC; }
.pill { display: inline-flex; align-items: center; gap: 5px; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }
.pill-dot { width: 6px; height: 6px; border-radius: 50%; }
.pill-open { background: #FFF1E7; color: #C2540A; }
.pill-open .pill-dot { background: var(--v-amber); }
.pill-pending { background: #EAF6FF; color: #0B6FB8; }
.pill-pending .pill-dot { background: #3B9EE8; }
.pill-resolved { background: #E9F9F0; color: #158A4A; }
.pill-resolved .pill-dot { background: var(--v-green); }
.pill-success { background: #E9F9F0; color: #158A4A; }
.pill-fail { background: #FFEFEF; color: #B91C1C; }
.channel-badge { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; color: var(--v-slate); }
.open-link { color: var(--v-teal); font-weight: 600; font-size: 12.5px; text-decoration: none; }
.login-box { background: white; padding: 40px; border-radius: 16px; box-shadow: 0 8px 30px rgba(16,27,45,0.15); width: 340px; }
.login-wrap { display: flex; align-items: center; justify-content: center; height: 100vh; background: var(--v-navy); }
.login-box h2 { font-family: 'Plus Jakarta Sans', sans-serif; margin-top: 0; }
.login-box input { width: 100%; padding: 11px 14px; margin: 10px 0; border-radius: 8px; border: 1px solid var(--v-border); box-sizing: border-box; font-family: inherit; }
.login-box button { width: 100%; padding: 11px; background: var(--v-navy); color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; }
.thread { display: flex; flex-direction: column; gap: 12px; padding: 20px; }
.msg { max-width: 70%; padding: 10px 14px; border-radius: 14px; font-size: 13.5px; line-height: 1.45; }
.msg-customer { background: var(--v-ice); border: 1px solid var(--v-border); align-self: flex-start; border-bottom-left-radius: 4px; }
.msg-agent { background: var(--v-navy); color: white; align-self: flex-end; border-bottom-right-radius: 4px; }
.msg-system { background: #FFF7E6; color: #92600B; align-self: center; font-size: 12px; font-style: italic; }
.msg-meta { font-size: 10.5px; opacity: 0.6; margin-bottom: 3px; }
.reply-box { padding: 16px 20px; border-top: 1px solid var(--v-border); }
.reply-box textarea { width: 100%; padding: 10px 14px; border-radius: 10px; border: 1px solid var(--v-border); font-family: inherit; font-size: 13.5px; resize: vertical; }
.btn { display: inline-block; padding: 9px 18px; border-radius: 8px; border: none; cursor: pointer; font-weight: 600; font-size: 13px; text-decoration: none; }
.btn-primary { background: var(--v-navy); color: white; }
.btn-success { background: var(--v-green); color: white; }
.btn-row { display: flex; gap: 10px; margin-top: 10px; }
"""

_MARK_SVG = """
<svg width="20" height="20" viewBox="0 0 512 512">
    <circle cx="356" cy="168" r="34" fill="#FF8F4D"/>
    <path d="M96 336 L206 176 L268 262 L232 300 L96 336 Z" fill="rgba(255,255,255,0.25)"/>
    <path d="M118 356 L246 168 L338 300 L292 300 L246 236 L188 320 L118 356 Z" fill="#1FC6C6"/>
    <path d="M246 168 L268 200 L246 214 L224 200 Z" fill="#F5FAFB"/>
    <rect x="96" y="356" width="320" height="10" rx="5" fill="#F5FAFB" opacity="0.9"/>
</svg>
"""


def _sidebar(active: str) -> str:
    def item(label, icon, href, key):
        cls = "nav-item active" if key == active else "nav-item"
        return f'<a class="{cls}" href="{href}">{icon} {label}</a>'

    return f"""
    <div class="sidebar">
        <div class="sidebar-brand">
            <div class="sidebar-mark">{_MARK_SVG}</div>
            <div>
                <div class="sidebar-brand-text">Velvora</div>
                <div class="sidebar-brand-sub">Admin Dashboard</div>
            </div>
        </div>
        <div class="nav-section">
            {item("Overview", "&#128202;", "/admin/dashboard", "overview")}
            {item("Tickets", "&#127991;", "/admin/dashboard", "tickets")}
        </div>
    </div>
    """


@router.get("/admin", response_class=HTMLResponse)
async def admin_login_page(request: Request, error: str = None):
    if _is_authenticated(request):
        return RedirectResponse(url="/admin/dashboard")

    error_html = (
        '<p style="color:#B91C1C; font-size:12.5px; margin-top:-4px;">Incorrect password.</p>'
        if error else ""
    )

    return HTMLResponse(f"""
    <html><head><title>Velvora Admin</title>
    <style>{_BASE_STYLES}</style></head>
    <body>
        <div class="login-wrap">
            <div class="login-box">
                <div style="display:flex; align-items:center; gap:10px; margin-bottom:16px;">
                    <div style="width:38px;height:38px;border-radius:10px;background:var(--v-ice);display:flex;align-items:center;justify-content:center;">
                        <svg width="22" height="22" viewBox="0 0 512 512">
                            <circle cx="356" cy="168" r="34" fill="#FF8F4D"/>
                            <path d="M96 336 L206 176 L268 262 L232 300 L96 336 Z" fill="#24354F"/>
                            <path d="M118 356 L246 168 L338 300 L292 300 L246 236 L188 320 L118 356 Z" fill="#1FC6C6"/>
                            <path d="M246 168 L268 200 L246 214 L224 200 Z" fill="#101B2D"/>
                        </svg>
                    </div>
                    <h2 style="margin:0;">Velvora Admin</h2>
                </div>
                <form method="post" action="/admin/login">
                    <input type="password" name="password" placeholder="Admin password" required />
                    {error_html}
                    <button type="submit">Log in</button>
                </form>
            </div>
        </div>
    </body></html>
    """)


@router.post("/admin/login")
async def admin_login(password: str = Form(...)):
    if password != settings.ADMIN_PASSWORD:
        logger.warning("Failed admin login attempt")
        return RedirectResponse(url="/admin?error=1", status_code=303)

    token = _serializer.dumps("authenticated")
    response = RedirectResponse(url="/admin/dashboard", status_code=303)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, max_age=86400)
    logger.info("Admin logged in successfully")
    return response


def _channel_badge(channel: str) -> str:
    icon = "&#9992;" if channel == "telegram" else "&#127760;"
    return f'<span class="channel-badge">{icon} {channel}</span>'


def _status_pill(status: str) -> str:
    label = status.capitalize()
    return f'<span class="pill pill-{status}"><span class="pill-dot"></span>{label}</span>'


@router.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin")

    stats = get_summary_stats()
    tickets = get_all_tickets()
    tool_calls = get_recent_tool_calls(limit=15)

    tickets_rows = "".join(
        f"""
        <tr>
            <td>#{t['id']}</td>
            <td>{_channel_badge(t['channel'])}</td>
            <td>{t['subject'][:70]}</td>
            <td>{_status_pill(t['status'])}</td>
            <td>{t['updated_at'].strftime('%b %d, %H:%M')}</td>
            <td><a class="open-link" href="/admin/ticket/{t['id']}">Open &rarr;</a></td>
        </tr>
        """
        for t in tickets
    ) or '<tr><td colspan="6" style="text-align:center; color:var(--v-slate);">No tickets yet</td></tr>'

    activity_rows = "".join(
        f"""
        <tr>
            <td>{t['timestamp'].strftime('%b %d, %H:%M')}</td>
            <td>{_channel_badge(t['channel'])}</td>
            <td>{t['tool_name']}</td>
            <td><span class="pill {'pill-success' if t['success'] else 'pill-fail'}">{'Success' if t['success'] else 'Failed'}</span></td>
        </tr>
        """
        for t in tool_calls
    ) or '<tr><td colspan="4" style="text-align:center; color:var(--v-slate);">No activity yet</td></tr>'

    return HTMLResponse(f"""
    <html><head><title>Velvora Admin Dashboard</title>
    <style>{_BASE_STYLES}</style></head>
    <body>
    <div class="app">
        {_sidebar("overview")}
        <div class="main">
            <div class="topbar">
                <div>
                    <h1>Overview</h1>
                    <p>Everything your AI agent has been doing</p>
                </div>
            </div>

            <div class="stats-grid">
                <div class="stat-card"><div class="stat-icon" style="background:#EAF6FF;">&#128172;</div><div class="stat-number">{stats['total_conversations']}</div><div class="stat-label">Conversations</div></div>
                <div class="stat-card"><div class="stat-icon" style="background:#F1F0FF;">&#9881;</div><div class="stat-number">{stats['total_tool_calls']}</div><div class="stat-label">Tool calls</div></div>
                <div class="stat-card"><div class="stat-icon" style="background:#FFF1E7;">&#127991;</div><div class="stat-number">{stats['total_escalations']}</div><div class="stat-label">Tickets</div></div>
                <div class="stat-card"><div class="stat-icon" style="background:#FFE9EC;">&#9203;</div><div class="stat-number">{stats['pending_escalations']}</div><div class="stat-label">Pending</div></div>
                <div class="stat-card"><div class="stat-icon" style="background:#E9F9F0;">&#9989;</div><div class="stat-number">{stats['refunds_issued']}</div><div class="stat-label">Refunds issued</div></div>
                <div class="stat-card"><div class="stat-icon" style="background:#FFEFEF;">&#128683;</div><div class="stat-number">{stats['refunds_blocked']}</div><div class="stat-label">Refunds blocked</div></div>
            </div>

            <div class="card">
                <div class="card-header"><h2>Tickets</h2></div>
                <table>
                    <tr><th>ID</th><th>Channel</th><th>Subject</th><th>Status</th><th>Updated</th><th></th></tr>
                    {tickets_rows}
                </table>
            </div>

            <div class="card">
                <div class="card-header"><h2>Recent Activity</h2></div>
                <table>
                    <tr><th>Time</th><th>Channel</th><th>Tool</th><th>Result</th></tr>
                    {activity_rows}
                </table>
            </div>
        </div>
    </div>
    </body></html>
    """)


@router.get("/admin/ticket/{ticket_id}", response_class=HTMLResponse)
async def ticket_detail(ticket_id: int, request: Request):
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin")

    ticket = get_ticket(ticket_id)
    if not ticket:
        return HTMLResponse("Ticket not found", status_code=404)

    messages = get_ticket_messages(ticket_id)

    messages_html = "".join(
        f"""
        <div class="msg msg-{m['sender']}">
            <div class="msg-meta">{m['sender']} &middot; {m['created_at'].strftime('%b %d, %H:%M')}</div>
            {m['message']}
        </div>
        """
        for m in messages
    )

    resolve_button = (
        ""
        if ticket["status"] == "resolved"
        else f"""
        <form method="post" action="/admin/ticket/{ticket_id}/resolve">
            <button type="submit" class="btn btn-success">Mark Resolved</button>
        </form>
        """
    )

    return HTMLResponse(f"""
    <html><head><title>Ticket #{ticket_id}</title>
    <style>{_BASE_STYLES}</style></head>
    <body>
    <div class="app">
        {_sidebar("tickets")}
        <div class="main">
            <div class="topbar">
                <div>
                    <a href="/admin/dashboard">&larr; Back to dashboard</a>
                    <h1 style="margin-top:6px;">Ticket #{ticket_id} {_status_pill(ticket['status'])}</h1>
                    <p>{_channel_badge(ticket['channel'])} &middot; {ticket['user_id']} &middot; {ticket['customer_email'] or 'no email on file'}</p>
                </div>
            </div>

            <div class="card">
                <div class="thread">{messages_html}</div>
                <div class="reply-box">
                    <form method="post" action="/admin/ticket/{ticket_id}/reply">
                        <textarea name="message" rows="3" placeholder="Reply to customer..." required></textarea>
                        <div class="btn-row">
                            <button type="submit" class="btn btn-primary">Send Reply</button>
                        </div>
                    </form>
                    <div class="btn-row">{resolve_button}</div>
                </div>
            </div>
        </div>
    </div>
    </body></html>
    """)


@router.post("/admin/ticket/{ticket_id}/reply")
async def ticket_reply(ticket_id: int, request: Request, message: str = Form(...)):
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin")

    ticket = get_ticket(ticket_id)
    if ticket:
        add_ticket_message(ticket_id, "agent", message)
        channel = ticket["channel"]
        user_id = ticket["user_id"]

        if channel == "telegram":
            try:
                http_requests.post(
                    f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={"chat_id": user_id, "text": f"[Support Team] {message}"},
                    timeout=10,
                )
            except http_requests.exceptions.RequestException as e:
                logger.error(f"Failed to deliver reply via Telegram: {e}")
        elif ticket.get("customer_email"):
            from integrations.email_service import send_email
            send_email(
                to=ticket["customer_email"],
                subject=f"Re: Ticket #{ticket_id}",
                body=message,
            )
        set_ticket_status(ticket_id, "pending")

    return RedirectResponse(url=f"/admin/ticket/{ticket_id}", status_code=303)


@router.post("/admin/ticket/{ticket_id}/resolve")
async def ticket_resolve(ticket_id: int, request: Request):
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin")

    set_ticket_status(ticket_id, "resolved")
    return RedirectResponse(url=f"/admin/ticket/{ticket_id}", status_code=303)


logger.debug("adapters.admin_routes loaded successfully")