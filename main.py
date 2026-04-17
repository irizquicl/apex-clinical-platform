from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import secrets
import hashlib

app = FastAPI()

# Simple session store (in-memory for now)
valid_sessions = set()

USERS = {
    "admin": ("ApexClinical2026!", "Medical Director"),
    "viewer": ("ApexView2026!", "Administrator"),
}

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PCC Intelligence — Login</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
        body { background: #F8F9FC; display: flex; align-items: center; justify-content: center; min-height: 100vh; }
        .login-card { background: white; border-radius: 16px; padding: 40px; width: 100%; max-width: 400px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); border: 1px solid #E2E8F0; }
        .brand { display: flex; align-items: center; gap: 12px; margin-bottom: 32px; justify-content: center; }
        .brand-icon { font-size: 32px; }
        .brand-text h1 { font-size: 20px; font-weight: 700; color: #0F172A; }
        .brand-text p { font-size: 13px; color: #64748B; margin-top: 2px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; font-size: 13px; font-weight: 500; color: #374151; margin-bottom: 6px; }
        input { width: 100%; padding: 10px 14px; border: 1px solid #E2E8F0; border-radius: 8px; font-size: 14px; color: #0F172A; outline: none; transition: border-color 0.2s; }
        input:focus { border-color: #6366F1; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }
        .btn-login { width: 100%; background: #6366F1; color: white; border: none; padding: 12px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; transition: background 0.2s; }
        .btn-login:hover { background: #4F46E5; }
        .error { background: #FEE2E2; color: #991B1B; padding: 10px 14px; border-radius: 8px; font-size: 13px; margin-bottom: 16px; }
        .footer { text-align: center; margin-top: 24px; font-size: 12px; color: #94A3B8; }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="brand">
            <span class="brand-icon">🧬</span>
            <div class="brand-text">
                <h1>PCC Intelligence</h1>
                <p>AI-Powered Clinical Command Center</p>
            </div>
        </div>
        {error_html}
        <form method="post" action="/login">
            <div class="form-group">
                <label>Username</label>
                <input type="text" name="username" placeholder="Enter username" required autofocus>
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" placeholder="Enter password" required>
            </div>
            <button type="submit" class="btn-login">Sign In →</button>
        </form>
        <div class="footer">Apex Healthcare Advanced Medicine Division</div>
    </div>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    error_html = f'<div class="error">❌ {error}</div>' if error else ""
    return LOGIN_HTML.replace("{error_html}", error_html)

@app.post("/login")
async def do_login(response: Response, username: str = Form(...), password: str = Form(...)):
    if username in USERS and USERS[username][0] == password:
        token = secrets.token_hex(32)
        valid_sessions.add(token)
        resp = RedirectResponse(url="/dashboard", status_code=302)
        resp.set_cookie("session", token, httponly=True, max_age=28800)  # 8 hours
        return resp
    return RedirectResponse(url="/?error=Invalid+username+or+password", status_code=302)

@app.get("/logout")
async def logout(request: Request):
    session = request.cookies.get("session")
    if session in valid_sessions:
        valid_sessions.discard(session)
    resp = RedirectResponse(url="/", status_code=302)
    resp.delete_cookie("session")
    return resp

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    session = request.cookies.get("session")
    if session not in valid_sessions:
        return RedirectResponse(url="/", status_code=302)
    # Read and serve the V7 dashboard
    with open("static/dashboard.html", "r") as f:
        content = f.read()
    # Inject logout button into the dashboard
    logout_btn = '<a href="/logout" style="position:fixed;top:12px;right:16px;z-index:999;background:#EF4444;color:white;padding:6px 14px;border-radius:6px;font-size:12px;font-weight:600;text-decoration:none;">Sign Out</a>'
    content = content.replace("</body>", f"{logout_btn}</body>")
    return HTMLResponse(content=content)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "apex-clinical-platform"}
