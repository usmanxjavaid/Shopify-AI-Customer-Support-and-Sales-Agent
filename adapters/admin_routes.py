"""
adapters/admin_routes.py
--------------------------
Simple password-protected admin dashboard.

Shows summary stats, escalations (with resolve capability), and
recent tool call activity — read-only view into the audit trail
built up in persistence/.

Auth: single shared admin password (via .env), session cookie based.
Not a multi-user system — appropriate for a single store owner's
internal dashboard, not a public-facing feature.
"""

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import URLSafeSerializer, BadSignature

from config import settings
from persistence.queries import (
    get_summary_stats,
    get_escalations,
    get_recent_tool_calls,
    mark_escalation_resolved,
)
from logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

_serializer = URLSafeSerializer(settings.ADMIN_PASSWORD or "fallback-secret-change-me")
SESSION_COOKIE = "velvora_admin_session"


def _is_authenticated(request: Request) -> bool:
    """Checks if the request has a valid admin session cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return False
    try:
        data = _serializer.loads(token)
        return data == "authenticated"
    except BadSignature:
        return False


@router.get("/admin", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    """Shows the login page, or redirects to dashboard if already logged in."""
    if _is_authenticated(request):
        return RedirectResponse(url="/admin/dashboard")

    return HTMLResponse("""
    <html>
    <head><title>Velvora Admin</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #f4f4f4;
               display: flex; align-items: center; justify-content: center;
               height: 100vh; margin: 0; }
        .login-box { background: white; padding: 40px; border-radius: 12px;
                     box-shadow: 0 2px 10px rgba(0,0,0,0.1); width: 320px; }
        h2 { margin-top: 0; }
        input { width: 100%; padding: 10px; margin: 10px 0; border-radius: 6px;
                border: 1px solid #ddd; box-sizing: border-box; }
        button { width: 100%; padding: 10px; background: #1a1a1a; color: white;
                 border: none; border-radius: 6px; cursor: pointer; }
    </style>
    </head>
    <body>
        <div class="login-box">
            <h2>Velvora Admin</h2>
            <form method="post" action="/admin/login">
                <input type="password" name="password" placeholder="Admin password" required />
                <button type="submit">Log in</button>
            </form>
        </div>
    </body>
    </html>
    """)


@router.post("/admin/login")
async def admin_login(password: str = Form(...)):
    """Validates the submitted password and sets the session cookie."""
    if password != settings.ADMIN_PASSWORD:
        logger.warning("Failed admin login attempt")
        return RedirectResponse(url="/admin?error=1", status_code=303)

    token = _serializer.dumps("authenticated")
    response = RedirectResponse(url="/admin/dashboard", status_code=303)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, max_age=86400)
    logger.info("Admin logged in successfully")
    return response


@router.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """Main dashboard — stats, escalations, recent activity."""
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin")

    stats = get_summary_stats()
    escalations = get_escalations()
    tool_calls = get_recent_tool_calls()

    escalations_rows = "".join(
        f"""
        <tr>
            <td>{e['id']}</td>
            <td>{e['channel']}</td>
            <td>{e['user_id']}</td>
            <td>{e['reason']}</td>
            <td>{e['timestamp'].strftime('%Y-%m-%d %H:%M')}</td>
            <td>{'✅ Resolved' if e['resolved'] else '⏳ Pending'}</td>
            <td>
                {'' if e['resolved'] else f'<form method="post" action="/admin/resolve/{e["id"]}"><button>Mark resolved</button></form>'}
            </td>
        </tr>
        """
        for e in escalations
    )

    tool_calls_rows = "".join(
        f"""
        <tr>
            <td>{t['timestamp'].strftime('%Y-%m-%d %H:%M')}</td>
            <td>{t['channel']}</td>
            <td>{t['user_id']}</td>
            <td>{t['tool_name']}</td>
            <td>{'✅' if t['success'] else '❌'}</td>
        </tr>
        """
        for t in tool_calls
    )

    return HTMLResponse(f"""
    <html>
    <head><title>Velvora Admin Dashboard</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #f4f4f4; margin: 0; padding: 30px; }}
        h1 {{ margin-bottom: 4px; }}
        .stats {{ display: flex; gap: 16px; margin: 20px 0; flex-wrap: wrap; }}
        .stat-card {{ background: white; padding: 20px; border-radius: 12px;
                      box-shadow: 0 2px 8px rgba(0,0,0,0.08); min-width: 140px; }}
        .stat-card .number {{ font-size: 28px; font-weight: 700; }}
        .stat-card .label {{ color: #666; font-size: 13px; }}
        table {{ width: 100%; background: white; border-collapse: collapse;
                  border-radius: 12px; overflow: hidden; margin-bottom: 30px; }}
        th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #eee; font-size: 13px; }}
        th {{ background: #1a1a1a; color: white; }}
        button {{ background: #1a1a1a; color: white; border: none; padding: 6px 12px;
                   border-radius: 6px; cursor: pointer; font-size: 12px; }}
        h2 {{ margin-top: 30px; }}
    </style>
    </head>
    <body>
        <h1>Velvora Admin Dashboard</h1>

        <div class="stats">
            <div class="stat-card"><div class="number">{stats['total_conversations']}</div><div class="label">Conversations</div></div>
            <div class="stat-card"><div class="number">{stats['total_tool_calls']}</div><div class="label">Total tool calls</div></div>
            <div class="stat-card"><div class="number">{stats['total_escalations']}</div><div class="label">Escalations</div></div>
            <div class="stat-card"><div class="number">{stats['pending_escalations']}</div><div class="label">Pending escalations</div></div>
            <div class="stat-card"><div class="number">{stats['refunds_issued']}</div><div class="label">Refunds issued</div></div>
            <div class="stat-card"><div class="number">{stats['refunds_blocked']}</div><div class="label">Refunds blocked</div></div>
        </div>

        <h2>Escalations</h2>
        <table>
            <tr><th>ID</th><th>Channel</th><th>User</th><th>Reason</th><th>Time</th><th>Status</th><th></th></tr>
            {escalations_rows or '<tr><td colspan="7">No escalations yet</td></tr>'}
        </table>

        <h2>Recent Tool Activity</h2>
        <table>
            <tr><th>Time</th><th>Channel</th><th>User</th><th>Tool</th><th>Success</th></tr>
            {tool_calls_rows or '<tr><td colspan="5">No activity yet</td></tr>'}
        </table>
    </body>
    </html>
    """)


@router.post("/admin/resolve/{escalation_id}")
async def resolve_escalation(escalation_id: int, request: Request):
    """Marks an escalation as resolved, then redirects back to dashboard."""
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin")

    mark_escalation_resolved(escalation_id)
    return RedirectResponse(url="/admin/dashboard", status_code=303)


logger.debug("adapters.admin_routes loaded successfully")