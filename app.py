from flask import Flask, request, abort, jsonify, session, redirect
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (MessageEvent, TextMessage, TextSendMessage,
                             ImageMessage, FileMessage)
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os, re, threading, time
from google import genai
from supabase import create_client
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "hyread-admin-2026-secret")
line_bot_api = LineBotApi(os.environ.get("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("CHANNEL_SECRET"))
supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
WEB_URL = "https://hyreadline-webhook.onrender.com/qa"

# ──────────────────────────────────────────────
# 登入驗證
# ──────────────────────────────────────────────
def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return decorated

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "")
        result = supabase.table("admin_users").select("*")\
            .eq("username", username).eq("is_active", True).execute()
        if result.data and check_password_hash(result.data[0]["password_hash"], password) and result.data[0].get("can_admin", True):
            session["admin_logged_in"] = True
            session["admin_username"] = username
            return redirect("/admin")
        error = "帳號或密碼錯誤"
    # 若無任何管理者帳號，導向初始設定
    try:
        count = supabase.table("admin_users").select("id", count="exact").execute()
        if (count.count or 0) == 0:
            return redirect("/admin/setup")
    except:
        pass
    return '''<!DOCTYPE html>
<html lang="zh-TW"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HyRead Q&A 管理登入</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Microsoft JhengHei",sans-serif;background:#f5f7fa;display:flex;align-items:center;justify-content:center;min-height:100vh}
.box{background:#fff;border-radius:12px;border:.5px solid #e0e0e0;padding:32px 36px;width:340px}
.logo{text-align:center;font-size:28px;margin-bottom:8px}
h2{text-align:center;font-size:16px;font-weight:500;color:#333;margin-bottom:24px}
label{font-size:12px;color:#777;display:block;margin-bottom:4px}
input{width:100%;padding:9px 12px;border:.5px solid #ddd;border-radius:6px;font-size:13px;margin-bottom:14px;font-family:inherit;outline:none}
input:focus{border-color:#00b900}
.btn{width:100%;padding:10px;background:#00b900;color:#fff;border:none;border-radius:6px;font-size:14px;cursor:pointer;font-weight:500}
.err{color:#e53935;font-size:12px;text-align:center;margin-bottom:12px}
</style></head><body>
<div class="box">
  <div class="logo">📋</div>
  <h2>HyRead Q&A 管理介面</h2>
  ''' + (f'<div class="err">{error}</div>' if error else '') + '''
  <form method="POST">
    <label>帳號</label>
    <input type="text" name="username" placeholder="請輸入帳號" autofocus>
    <label>密碼</label>
    <div style="position:relative"><input type="password" id="pwdField" name="password" placeholder="請輸入密碼" style="width:100%;padding-right:38px"><span onclick="var f=document.getElementById('pwdField');f.type=f.type==='password'?'text':'password';this.textContent=f.type==='password'?'👁':'🙈'" style="position:absolute;right:10px;top:50%;transform:translateY(-50%);cursor:pointer;font-size:15px;user-select:none">👁</span></div>
    <button class="btn" type="submit">登入</button>
  </form>
</div></body></html>'''

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    session.pop("admin_username", None)
    return redirect("/admin/login")

# ──────────────────────────────────────────────
# 查詢介面 登入驗證
# ──────────────────────────────────────────────
def require_qa(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("qa_logged_in"):
            return redirect("/qa/login")
        return f(*args, **kwargs)
    return decorated

@app.route("/qa/login", methods=["GET", "POST"])
def qa_login():
    error = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "")
        result = supabase.table("admin_users").select("*")\
            .eq("username", username).eq("is_active", True).execute()
        if result.data and check_password_hash(result.data[0]["password_hash"], password) and result.data[0].get("can_query", True):
            session["qa_logged_in"] = True
            session["qa_username"] = username
            return redirect("/qa")
        error = "帳號或密碼錯誤"
    return '''<!DOCTYPE html>
<html lang="zh-TW"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HyRead Q&A 查詢登入</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Microsoft JhengHei",sans-serif;background:#f5f7fa;display:flex;align-items:center;justify-content:center;min-height:100vh}
.box{background:#fff;border-radius:12px;border:.5px solid #e0e0e0;padding:32px 36px;width:340px}
.logo{text-align:center;font-size:28px;margin-bottom:8px}
h2{text-align:center;font-size:16px;font-weight:500;color:#333;margin-bottom:24px}
label{font-size:12px;color:#777;display:block;margin-bottom:4px}
input{width:100%;padding:9px 12px;border:.5px solid #ddd;border-radius:6px;font-size:13px;margin-bottom:14px;font-family:inherit;outline:none}
input:focus{border-color:#00b900}
.btn{width:100%;padding:10px;background:#00b900;color:#fff;border:none;border-radius:6px;font-size:14px;cursor:pointer;font-weight:500}
.err{color:#e53935;font-size:12px;text-align:center;margin-bottom:12px}
</style></head><body>
<div class="box">
  <div class="logo">🔍</div>
  <h2>HyRead Q&A 查詢系統</h2>
  ''' + (f'<div class="err">{error}</div>' if error else '') + '''
  <form method="POST">
    <label>帳號</label>
    <input type="text" name="username" placeholder="請輸入帳號" autofocus>
    <label>密碼</label>
    <div style="position:relative"><input type="password" id="pwdField" name="password" placeholder="請輸入密碼" style="width:100%;padding-right:38px"><span onclick="var f=document.getElementById('pwdField');f.type=f.type==='password'?'text':'password';this.textContent=f.type==='password'?'👁':'🙈'" style="position:absolute;right:10px;top:50%;transform:translateY(-50%);cursor:pointer;font-size:15px;user-select:none">👁</span></div>
    <button class="btn" type="submit">登入</button>
  </form>
</div></body></html>'''

@app.route("/qa/logout")
def qa_logout():
    session.pop("qa_logged_in", None)
    session.pop("qa_username", None)
    return redirect("/qa/login")

@app.route("/admin/setup", methods=["GET", "POST"])
def admin_setup():
    # 只有無任何管理者時才可使用
    try:
        count = supabase.table("admin_users").select("id", count="exact").execute()
        if (count.count or 0) > 0:
            return redirect("/admin/login")
    except:
        pass
    msg = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "")
        if username and len(password) >= 6:
            hashed = generate_password_hash(password)
            supabase.table("admin_users").insert({
                "username": username,
                "password_hash": hashed,
                "created_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
                "is_active": True
            }).execute()
            return redirect("/admin/login")
        msg = "帳號不可為空，密碼至少 6 個字元"
    return '''<!DOCTYPE html>
<html lang="zh-TW"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>初始設定</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Microsoft JhengHei",sans-serif;background:#f5f7fa;display:flex;align-items:center;justify-content:center;min-height:100vh}
.box{background:#fff;border-radius:12px;border:.5px solid #e0e0e0;padding:32px 36px;width:340px}
.logo{text-align:center;font-size:28px;margin-bottom:8px}
h2{text-align:center;font-size:15px;font-weight:500;color:#333;margin-bottom:6px}
p{text-align:center;font-size:12px;color:#aaa;margin-bottom:20px}
label{font-size:12px;color:#777;display:block;margin-bottom:4px}
input{width:100%;padding:9px 12px;border:.5px solid #ddd;border-radius:6px;font-size:13px;margin-bottom:14px;font-family:inherit;outline:none}
input:focus{border-color:#00b900}
.btn{width:100%;padding:10px;background:#00b900;color:#fff;border:none;border-radius:6px;font-size:14px;cursor:pointer}
.err{color:#e53935;font-size:12px;text-align:center;margin-bottom:12px}
</style></head><body>
<div class="box">
  <div class="logo">🔐</div>
  <h2>建立第一個管理者帳號</h2>
  <p>此頁面只在尚無任何管理者時出現</p>
  ''' + (f'<div class="err">{msg}</div>' if msg else '') + '''
  <form method="POST">
    <label>帳號</label>
    <input type="text" name="username" placeholder="設定帳號" autofocus>
    <label>密碼（至少 6 個字元）</label>
    <input type="password" name="password" placeholder="設定密碼">
    <button class="btn" type="submit">建立管理者</button>
  </form>
</div></body></html>'''

# ──────────────────────────────────────────────
# Keep-alive
# ──────────────────────────────────────────────
@app.route("/ping")
def ping():
    return "pong", 200

# ──────────────────────────────────────────────
# Q&A 查詢主頁
# ──────────────────────────────────────────────
@app.route("/qa")
@require_qa
def qa_page():
    uname = session.get("qa_username", "")
    uinfo = supabase.table("admin_users").select("display_name,can_admin,perm_tags").eq("username", uname).execute()
    display_name = uname
    can_admin = False
    perm_tags = False
    if uinfo.data:
        display_name = uinfo.data[0].get("display_name") or uname
        can_admin = bool(uinfo.data[0].get("can_admin", False))
        perm_tags = bool(uinfo.data[0].get("perm_tags", False))
    admin_btn = '<a href="/admin" style="margin-left:6px">⚙ 管理介面</a>' if can_admin else ''
    user_label = f'<span style="margin-left:6px;font-size:11px;color:rgba(255,255,255,.8);background:rgba(255,255,255,.15);padding:3px 10px;border-radius:6px;border:.5px solid rgba(255,255,255,.3)">{display_name}</span>'
    edit_tag_btn = '''<button id="editToggle" onclick="toggleEditMode()"
    style="margin-left:auto;background:rgba(255,255,255,.15);border:.5px solid rgba(255,255,255,.4);color:#fff;padding:4px 12px;border-radius:6px;font-size:11px;cursor:pointer">
    ✏️ 編輯標籤
  </button>''' if perm_tags else '<span style="margin-left:auto"></span>'
    page = '''<!DOCTYPE html>
<html lang="zh-TW"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HyRead Q&A 查詢</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Microsoft JhengHei",sans-serif;height:100vh;display:flex;flex-direction:column;background:#f5f7fa}
.topbar{background:#00b900;color:#fff;padding:11px 18px;display:flex;align-items:center;gap:8px;font-size:14px;font-weight:500;flex-shrink:0}
.topbar a{color:rgba(255,255,255,.85);font-size:11px;padding:4px 10px;border-radius:6px;border:.5px solid rgba(255,255,255,.3);text-decoration:none;margin-left:auto}
.wrap{display:flex;flex:1;overflow:hidden}
aside{width:260px;background:#fff;border-right:.5px solid #e0e0e0;padding:10px 8px;display:flex;flex-direction:column;gap:3px;flex-shrink:0;overflow-y:auto}
.yearbar{background:#1a8c2e;padding:7px 16px;display:flex;align-items:center;gap:6px;flex-wrap:wrap;flex-shrink:0}
.yr-bar-btn{padding:3px 10px;border-radius:6px;font-size:11px;cursor:pointer;border:.5px solid rgba(255,255,255,.35);color:rgba(255,255,255,.9);background:rgba(255,255,255,.12)}
.yr-bar-btn:hover{background:rgba(255,255,255,.25)}
.yr-bar-btn.active{background:rgba(255,255,255,.9);color:#1a6b35;font-weight:500;border-color:transparent}
.tag-group-hdr{font-size:10px;font-weight:600;color:#555;padding:6px 2px 3px;letter-spacing:.4px;display:flex;align-items:center;gap:5px;cursor:pointer}
.tag-group-hdr .grp-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.tag-group-hdr .grp-count{font-size:9px;color:#aaa;margin-left:auto}
.sb-lbl{font-size:10px;color:#aaa;padding:7px 5px 3px;letter-spacing:.5px}
.yr-link{padding:7px 10px;border-radius:6px;font-size:12px;cursor:pointer;border:.5px solid transparent;color:#666;text-align:left}
.yr-link.active{background:#e8f5e9;border:.5px solid #00b900;color:#1b5e20;font-weight:500}
.yr-link:hover:not(.active){background:#f5f5f5}
.yr-checks{display:flex;flex-wrap:wrap;gap:4px 10px;padding:5px 2px 0;font-size:11px;color:#555}
.yr-checks label{display:flex;align-items:center;gap:3px;cursor:pointer;white-space:nowrap}
.yr-checks input[type=checkbox]{accent-color:#00b900;width:13px;height:13px;cursor:pointer}
.divider{height:.5px;background:#eee;margin:5px 0}
.tag-filter-chip{display:inline-block;padding:3px 10px;border:.5px solid #ddd;border-radius:99px;font-size:11px;color:#666;cursor:pointer;background:#fff;margin:2px;transition:background .12s,border-color .12s}
.tag-filter-chip:hover{border-color:#00b900;color:#1b5e20}
.tag-filter-chip.active{background:#e8f5e9;border-color:#00b900;color:#1b5e20;font-weight:500}
.tag-clear-btn{font-size:10px;color:#999;padding:3px 10px;border:.5px solid #e0e0e0;border-radius:99px;cursor:pointer;background:transparent;margin-top:4px;display:none;width:100%}
.side-tab-bar{display:flex;flex-wrap:wrap;gap:2px;margin-bottom:8px;padding:7px 10px;border-radius:8px;background:#e0e0e0;border:.5px solid #ccc}
.side-tab-btn{padding:3px 8px;border-radius:6px;font-size:10px;cursor:pointer;border:.5px solid transparent;color:#888;background:transparent;white-space:nowrap;font-family:inherit}
.side-tab-btn:hover{background:#f0f0f0;color:#333}
.side-tab-btn.active{background:#e8f5e9;color:#1b5e20;border-color:#a5d6a7;font-weight:500}
.home-tab-bar{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:10px;background:#e0e0e0;border-radius:8px;padding:7px 10px;border:.5px solid #ccc}
.home-tab-btn{padding:5px 12px;border-radius:20px;font-size:12px;cursor:pointer;border:.5px solid #ddd;color:#666;background:#fff;white-space:nowrap;font-family:inherit}
.home-tab-btn:hover{border-color:#00b900;color:#1b5e20}
.home-tab-btn.active{background:#e8f5e9;border-color:#00b900;color:#1b5e20;font-weight:500}
.home-tab-cnt{font-size:10px;padding:1px 5px;border-radius:8px;background:rgba(0,0,0,.06);margin-left:3px}
.home-tab-btn.active .home-tab-cnt{background:rgba(27,94,32,.15);color:#1b5e20}
.tag-clear-btn.visible{display:block}
main{flex:1;display:flex;flex-direction:column;overflow:hidden}
.search-bar{padding:12px 16px;border-bottom:.5px solid #e0e0e0;background:#fff}
.search-row{display:flex;gap:8px}
.kw-input{flex:1;padding:9px 14px;border:1.5px solid #00b900;border-radius:20px;font-size:13px;font-family:inherit;outline:none;background:#fff}
.search-btn{width:38px;height:38px;background:#00b900;border:none;border-radius:50%;cursor:pointer;color:#fff;font-size:18px;display:flex;align-items:center;justify-content:center}
.clear-btn{width:38px;height:38px;background:#e0e0e0;border:none;border-radius:50%;cursor:pointer;color:#666;font-size:16px;display:flex;align-items:center;justify-content:center}
.clear-btn:hover{background:#bdbdbd}
.meta{display:flex;align-items:center;gap:8px;margin-top:6px;font-size:11px;color:#aaa}
.meta-badge{background:#e8f5e9;color:#2e7d32;padding:2px 8px;border-radius:99px;font-weight:500}
.sel-tag-bar{display:none;align-items:center;flex-wrap:wrap;gap:6px;padding:7px 12px;background:#f0fff0;border:.5px solid #c8e6c9;border-radius:8px;margin-bottom:8px}
.sel-tag-bar.has-tags{display:flex}
.sel-tag-pill{display:inline-flex;align-items:center;gap:4px;padding:3px 10px 3px 10px;background:#e8f5e9;border:.5px solid #a5d6a7;border-radius:99px;font-size:11px;color:#1b5e20}
.sel-tag-pill span{cursor:pointer;font-size:13px;line-height:1;color:#666;margin-left:2px}
.sel-tag-pill span:hover{color:#e53935}
.sel-clear-all{font-size:11px;color:#e53935;border:.5px solid #e53935;border-radius:99px;padding:3px 10px;background:transparent;cursor:pointer;margin-left:auto;white-space:nowrap}
.results{flex:1;overflow-y:auto;padding:14px 16px;display:flex;flex-direction:column;gap:10px}
.count-row{font-size:12px;color:#888;padding-bottom:6px;border-bottom:.5px solid #eee}
.card{background:#fff;border:.5px solid #e0e0e0;border-radius:10px;padding:13px 15px}
.card:hover{border-color:#b0bec5}
.q-row{display:flex;gap:8px;margin-bottom:8px}
.q-icon{min-width:28px;height:22px;padding:0 4px;background:#e8f5e9;border-radius:11px;display:flex;align-items:center;justify-content:center;font-size:10px;color:#2e7d32;flex-shrink:0;margin-top:1px;font-weight:600}
.pager{display:flex;gap:6px;justify-content:center;padding:16px 0 8px;flex-wrap:wrap}
.pg-btn{padding:6px 12px;border:.5px solid #ddd;border-radius:6px;background:#fff;font-size:12px;cursor:pointer;color:#555}
.pg-btn:hover{border-color:#00b900;color:#00b900}
.pg-cur{background:#00b900;color:#fff;border-color:#00b900;font-weight:600;cursor:default}
.q-txt{font-size:13px;font-weight:500;color:#333;line-height:1.55;flex:1}
.card-tags{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:7px}
.tag{font-size:10px;padding:2px 8px;border-radius:99px}
.tag-cat{background:#e8f5e9;color:#2e7d32}
.tag-yr{background:#f5f5f5;color:#888}
.a-lbl{font-size:10px;color:#aaa;margin-bottom:4px}
.a-txt{font-size:12px;color:#555;line-height:1.75;border-left:2px solid #00b900;padding-left:10px}
.hi{background:#fff176;border-radius:2px;padding:0 1px}
.empty{display:flex;flex-direction:column;align-items:flex-start;justify-content:flex-start;flex:1;color:#bbb;font-size:13px;gap:8px;text-align:left;padding:20px 24px}
.chips{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin-top:6px}
.chip{padding:7px 14px;border:.5px solid #ddd;border-radius:99px;font-size:12px;color:#666;cursor:pointer;background:#fff}
.chip:hover{border-color:#00b900;color:#1b5e20}
.cat-card{background:#fff;border:.5px solid #e0e0e0;border-radius:8px;padding:10px 13px;cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:12px;color:#444}
.cat-card:hover{border-color:#00b900;color:#1b5e20;background:#f0fff0}
.cat-card-cnt{font-size:11px;background:#e8f5e9;color:#2e7d32;border-radius:99px;padding:2px 8px;flex-shrink:0}
.loading{color:#aaa;font-size:13px;text-align:center;padding:40px}
.err{color:#e53935;font-size:13px;text-align:center;padding:20px}
/* ── 時間／發話者弱化 ── */
.meta-info{font-size:10px;color:#bbb;font-weight:400}
/* ── 編輯模式標籤 ── */
.tag-edit{display:inline-flex;align-items:center;gap:3px}
.tag-del{cursor:pointer;font-size:9px;width:14px;height:14px;border-radius:50%;background:rgba(0,0,0,.08);display:inline-flex;align-items:center;justify-content:center;line-height:1;color:#666;transition:background .15s,transform .15s;border:none;padding:0;flex-shrink:0}
.tag-del:hover{background:#e53935;color:#fff;transform:scale(1.2)}
.tag-ren{cursor:pointer;font-size:9px;width:14px;height:14px;border-radius:50%;background:rgba(0,0,0,.08);display:inline-flex;align-items:center;justify-content:center;line-height:1;color:#388e3c;transition:background .15s,transform .15s;border:none;padding:0;flex-shrink:0}
.tag-ren:hover{background:#c8e6c9;color:#1b5e20;transform:scale(1.2)}
.rename-popup{position:absolute;bottom:calc(100% + 6px);left:50%;transform:translateX(-50%);background:var(--surface,#fff);border:1px solid #ddd;border-radius:8px;padding:8px 10px;z-index:100;white-space:nowrap;min-width:170px;box-shadow:0 2px 8px rgba(0,0,0,.1)}
.rename-popup input{width:100%;border:1px solid #ddd;border-radius:6px;padding:4px 8px;font-size:12px;font-family:inherit;box-sizing:border-box;margin-bottom:6px}
.rename-popup-row{display:flex;gap:4px}
.rename-popup-row button{font-size:11px;padding:3px 9px;border-radius:6px;border:1px solid #ddd;background:#fff;cursor:pointer}
.rename-popup-row button.ok{background:#00b900;border-color:#00b900;color:#fff}
.tag-add{display:inline-flex;align-items:center;gap:3px;font-size:10px;padding:2px 8px;border-radius:99px;border:1px dashed #aaa;color:#aaa;cursor:pointer;background:transparent;transition:border-color .15s,color .15s,transform .15s}
.tag-add:hover{border-color:#00b900;color:#00b900;transform:scale(1.05)}
/* ── 編輯模式 topbar 指示 ── */
.edit-badge{font-size:10px;background:rgba(255,255,0,.25);color:#fff;padding:2px 8px;border-radius:99px;border:.5px solid rgba(255,255,255,.4)}
/* ── Tag Popover ── */
#tagPopover{position:fixed;background:#fff;border:.5px solid #ddd;border-radius:10px;box-shadow:0 4px 18px rgba(0,0,0,.13);padding:10px 12px 12px;z-index:999;display:none;width:360px;max-width:90vw}
#popSearch{width:100%;border:1px solid #ddd;border-radius:7px;padding:5px 10px;font-size:12px;font-family:inherit;box-sizing:border-box;margin-bottom:7px;outline:none}
#popSearch:focus{border-color:#66bb6a}
#popTagListWrap{max-height:220px;overflow-y:auto}
#tagPopover .pop-title{font-size:10px;color:#aaa;margin-bottom:7px;letter-spacing:.5px}
#tagPopover .pop-tags{display:flex;flex-wrap:wrap;gap:5px}
#tagPopover .pop-tag{font-size:11px;padding:4px 10px;border-radius:99px;background:#f0fff0;color:#2e7d32;border:.5px solid #c8e6c9;cursor:pointer;transition:background .12s,transform .12s}
#tagPopover .pop-tag:hover{background:#c8e6c9;transform:scale(1.06)}
</style></head><body>
<div class="topbar"><span onclick="clearSearch()" style="cursor:pointer;user-select:none" title="回首頁">📋 HyRead LINE Q&A 查詢系統</span>
  <button onclick="clearSearch()" title="回首頁"
    style="margin-left:10px;background:rgba(255,255,255,.15);border:.5px solid rgba(255,255,255,.35);color:#fff;padding:4px 10px;border-radius:6px;font-size:11px;cursor:pointer">
    🏠 首頁
  </button>
  <span id="editBadge" class="edit-badge" style="display:none">✏️ 標籤編輯模式</span>
  __EDIT_TAG_BTN__
  __ADMIN_BTN__
  __USER_LABEL__
  <a href="/qa/logout" style="margin-left:6px">登出</a>
</div>
<!-- Tag Popover -->
<div id="tagPopover">
  <input id="popSearch" type="text" placeholder="搜尋或新增標籤…" oninput="onPopSearch()" onclick="event.stopPropagation()">
  <div id="popTagListWrap">
    <div id="popTabBar" style="display:flex;flex-wrap:wrap;gap:3px;margin-bottom:8px;padding:5px 7px;border-radius:7px;background:#e8e8e8;border:.5px solid #ccc"></div>
    <div class="pop-tags" id="popTagList"></div>
  </div>
</div>
<div class="yearbar">
  <span style="font-size:11px;color:rgba(255,255,255,.6);margin-right:2px;">歷史資料：</span>
  <div class="yr-bar-btn" onclick="browseYearBar(this,'2019')">2019</div>
  <div class="yr-bar-btn" onclick="browseYearBar(this,'2020')">2020</div>
  <div class="yr-bar-btn" onclick="browseYearBar(this,'2021')">2021</div>
  <div class="yr-bar-btn" onclick="browseYearBar(this,'2022')">2022</div>
  <div class="yr-bar-btn" onclick="browseYearBar(this,'2023')">2023</div>
  <div class="yr-bar-btn" onclick="browseYearBar(this,'2024')">2024</div>
  <div class="yr-bar-btn" onclick="browseYearBar(this,'2025')">2025</div>
  <div class="yr-bar-btn" onclick="browseYearBar(this,'2026')">2026</div>
  <div class="yr-bar-btn" onclick="browseYearBar(this,'日常')">日常新增</div>
</div>
<div class="wrap">
  <aside>
    <div class="sb-lbl">標籤篩選</div>
    <div id="sideTabBar" class="side-tab-bar"></div>
    <div id="tagFilterList" style="line-height:1.9"></div>
    <button id="tagClearBtn" class="tag-clear-btn" onclick="clearTagFilter()">✕ 清除篩選</button>
  </aside>
  <main>
    <div class="search-bar">
      <div class="search-row">
        <input class="kw-input" id="kw" placeholder="輸入關鍵字，例如：無法登入、點數..."
          onkeydown="if(event.key===\'Enter\')search()">
        <button class="search-btn" onclick="search()" title="搜尋">&#x2315;</button>
        <button class="clear-btn" onclick="clearSearch()" title="清除">&#x2715;</button>
      </div>
      <div class="yr-checks">
        <label><input type="checkbox" id="yrAll" checked onchange="toggleAllYrs(this)">全選</label>
        <label><input type="checkbox" class="yr-ck" value="2019" checked onchange="onYrCkChange()">2019</label>
        <label><input type="checkbox" class="yr-ck" value="2020" checked onchange="onYrCkChange()">2020</label>
        <label><input type="checkbox" class="yr-ck" value="2021" checked onchange="onYrCkChange()">2021</label>
        <label><input type="checkbox" class="yr-ck" value="2022" checked onchange="onYrCkChange()">2022</label>
        <label><input type="checkbox" class="yr-ck" value="2023" checked onchange="onYrCkChange()">2023</label>
        <label><input type="checkbox" class="yr-ck" value="2024" checked onchange="onYrCkChange()">2024</label>
        <label><input type="checkbox" class="yr-ck" value="2025" checked onchange="onYrCkChange()">2025</label>
        <label><input type="checkbox" class="yr-ck" value="2026" checked onchange="onYrCkChange()">2026</label>
        <label><input type="checkbox" class="yr-ck" value="日常" checked onchange="onYrCkChange()">日常</label>
      </div>
      <div class="meta">
        <span id="scopeTxt">查詢範圍：全部年份</span>
        <span id="cntBadge" class="meta-badge" style="display:none"></span>
        <span style="margin-left:auto">直接搜尋資料庫，無需 AI 配額</span>
      </div>
      <div class="sel-tag-bar" id="selTagBar">
        <span style="font-size:11px;color:#555;white-space:nowrap">已選標籤：</span>
        <span id="selTagPills"></span>
        <button class="sel-clear-all" onclick="clearTagFilter()">✕ 清除全部</button>
      </div>
    </div>
    <div class="results" id="results">
      <div class="empty" id="homeState">
        <div style="font-size:15px;font-weight:500;color:#333;margin-bottom:4px">HyRead 客服歷史問答查詢</div>
        <div style="font-size:12px;color:#aaa;margin-bottom:16px">點選標籤快速篩選，或直接輸入關鍵字搜尋</div>
        <div style="width:100%;margin-bottom:14px">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
            <div style="font-size:10px;color:#bbb;letter-spacing:.5px">點選標籤篩選</div>
            <button id="homeClearBtn" onclick="clearTagFilter()" style="font-size:10px;color:#999;padding:3px 10px;border:.5px solid #e0e0e0;border-radius:99px;cursor:pointer;background:transparent;width:auto;">✕ 清除篩選</button>
          </div>
          <div id="homeTabBar" class="home-tab-bar"></div>
          <div id="homeTagChips" class="chips" style="justify-content:flex-start"></div>
        </div>
      </div>
    </div>
  </main>
</div>
<script>
var selectedTags=[],browseMode=false,browseYr='',currentPage=1,editMode=false,sidebarActiveGroup=null,homeActiveGroup=null,popActiveGroup=null;
/* Popover 用的預設標籤 */
var PRESET_TAGS=['維修','保固','召回','APP','帳號','物流','閱讀器','書櫃','破屏','線條','出線','忘記密碼','開放式','封閉式'];
/* 各卡片目前的 tags 暫存 {id: [tags]} */
var cardTags={};
/* 目前 Popover 對應的 item id */
var popTargetId=null;

/* ── 載入並渲染側欄標籤 chips ── */
var allTagsData=[];
var TAGS_DEFAULT_SHOW=30;
var tagsExpanded=false;

function loadTagsSummary(){
  var listEl=document.getElementById('tagFilterList');
  if(listEl)listEl.innerHTML='<div style="font-size:11px;color:#aaa;padding:4px">載入中…</div>';
  fetch('/qa/api/tags_with_groups').then(function(r){return r.json()}).then(function(d){
    if(d.error||!d.tags){throw new Error(d.error||'no tags');}
    allTagsData=d.tags||[];
    renderGroupedTagChips(allTagsData);
    var homeEl=document.getElementById('homeTagChips');
    if(homeEl){renderHomeTagChips(allTagsData,homeEl);}
  }).catch(function(err){
    /* 先嘗試 fallback API */
    fetch('/qa/api/tags_summary').then(function(r){return r.json()}).then(function(tags){
      if(!tags||!tags.length)throw new Error('empty');
      allTagsData=tags;
      renderTagChips(tags,TAGS_DEFAULT_SHOW);
    }).catch(function(){
      if(listEl)listEl.innerHTML='<div style="font-size:11px;color:#e53935;padding:4px">標籤載入失敗，<a href="#" onclick="loadTagsSummary();return false;" style="color:#1565c0">重試</a></div>';
    });
  });
}

var GRP_COLORS={'裝置型號':'#1D9E75','問題類型':'#378ADD','配件':'#BA7517','系統與軟體':'#7F77DD','未分群':'#888780'};
function grpColor(g){return GRP_COLORS[g]||'#888780';}

function renderGroupedTagChips(tags){
  var groups={};
  tags.forEach(function(t){var g=t.group||'未分群';if(!groups[g])groups[g]=[];groups[g].push(t);});
  var order=['裝置型號','問題類型','配件','系統與軟體','未分群'];
  var allGrps=[];
  order.forEach(function(g){if(groups[g]&&groups[g].length)allGrps.push(g);});
  Object.keys(groups).forEach(function(g){if(order.indexOf(g)<0&&groups[g].length)allGrps.push(g);});
  if(!allGrps.length){document.getElementById('tagFilterList').innerHTML='<div style="font-size:11px;color:#ccc;padding:4px">尚無標籤資料</div>';return;}
  if(!sidebarActiveGroup||allGrps.indexOf(sidebarActiveGroup)<0)sidebarActiveGroup=allGrps[0];
  var tabHtml='';
  allGrps.forEach(function(g){
    var act=g===sidebarActiveGroup?' active':'';
    tabHtml+='<button class="side-tab-btn'+act+'" data-grp="'+esc(g)+'">'+esc(g)+'</button>';
  });
  var sideTabBar=document.getElementById('sideTabBar');
  if(sideTabBar){sideTabBar.innerHTML=tabHtml;
    document.querySelectorAll('.side-tab-btn').forEach(function(el){
      el.addEventListener('click',function(){switchSideTab(this.dataset.grp);});
    });
  }
  var chipsHtml='';
  (groups[sidebarActiveGroup]||[]).forEach(function(t){
    var active=selectedTags.indexOf(t.tag)>=0?' active':'';
    chipsHtml+='<span class="tag-filter-chip'+active+'" data-tag="'+esc(t.tag)+'" onclick="toggleTagFilter(this)">'+esc(t.tag)+'</span>';
  });
  document.getElementById('tagFilterList').innerHTML=chipsHtml||'<div style="font-size:11px;color:#ccc;padding:4px">（無標籤）</div>';
}
function switchSideTab(group){sidebarActiveGroup=group;renderGroupedTagChips(allTagsData);}

function renderHomeTagChips(tags,el){
  var groups={};
  tags.forEach(function(t){var g=t.group||'未分群';if(!groups[g])groups[g]=[];groups[g].push(t);});
  var order=['裝置型號','問題類型','配件','系統與軟體','未分群'];
  var allGrps=[];
  order.forEach(function(g){if(groups[g]&&groups[g].length)allGrps.push(g);});
  Object.keys(groups).forEach(function(g){if(order.indexOf(g)<0&&groups[g].length)allGrps.push(g);});
  if(!allGrps.length)return;
  if(!homeActiveGroup||allGrps.indexOf(homeActiveGroup)<0)homeActiveGroup=allGrps[0];
  var tabHtml='';
  allGrps.forEach(function(g){
    var act=g===homeActiveGroup?' active':'';
    tabHtml+='<button class="home-tab-btn'+act+'" data-grp="'+esc(g)+'">'+esc(g)+'<span class="home-tab-cnt">'+(groups[g].length)+'</span></button>';
  });
  var homeTabBar=document.getElementById('homeTabBar');
  if(homeTabBar){homeTabBar.innerHTML=tabHtml;
    document.querySelectorAll('.home-tab-btn').forEach(function(b){
      b.addEventListener('click',function(){switchHomeTab(this.dataset.grp);});
    });
  }
  var chipsHtml='';
  (groups[homeActiveGroup]||[]).forEach(function(t){
    var active=selectedTags.indexOf(t.tag)>=0?' active':'';
    chipsHtml+='<span class="tag-filter-chip'+active+'" data-tag="'+esc(t.tag)+'" onclick="pickHomeTag(this.dataset.tag)">'+esc(t.tag)+'</span>';
  });
  el.innerHTML=chipsHtml;
}
function switchHomeTab(group){homeActiveGroup=group;var hEl=document.getElementById('homeTagChips');if(hEl)renderHomeTagChips(allTagsData,hEl);}

function browseYearBar(el,yr){
  document.querySelectorAll('.yr-bar-btn').forEach(function(b){b.classList.remove('active');});
  el.classList.add('active');
  browseYear(null,yr);
}

function renderTagChips(tags,limit){
  var showMore=document.getElementById('tagShowMore');
  var list=limit?tags.slice(0,limit):tags;
  var html='';
  list.forEach(function(t){
    var active=selectedTags.indexOf(t.tag)>=0?' active':'';
    html+='<span class="tag-filter-chip'+active+'" data-tag="'+esc(t.tag)+'" onclick="toggleTagFilter(this)">'+esc(t.tag)+'</span>';
  });
  document.getElementById('tagFilterList').innerHTML=html||'<div style="font-size:11px;color:#ccc;padding:4px">尚無標籤資料</div>';
  if(showMore){showMore.style.display=(!tagsExpanded&&tags.length>TAGS_DEFAULT_SHOW)?'block':'none';}
}

function renderSelTagBar(){
  var bar=document.getElementById('selTagBar');
  var pills=document.getElementById('selTagPills');
  if(!selectedTags.length){bar.classList.remove('has-tags');pills.innerHTML='';return;}
  bar.classList.add('has-tags');
  var html='';
  selectedTags.forEach(function(t){
    html+='<span class="sel-tag-pill" data-tag="'+escAttr(t)+'">'+esc(t)+'<span class="rm-sel-tag" title="移除">×</span></span>';
  });
  pills.innerHTML=html;
  document.querySelectorAll('#selTagPills .rm-sel-tag').forEach(function(el){
    el.addEventListener('click',function(){removeSelTag(this.parentElement.dataset.tag);});
  });
}
function removeSelTag(tag){
  var idx=selectedTags.indexOf(tag);
  if(idx>=0)selectedTags.splice(idx,1);
  document.querySelectorAll('.tag-filter-chip[data-tag="'+tag+'"]').forEach(function(e){e.classList.remove('active');});
  var cb=document.getElementById('tagClearBtn');
  if(selectedTags.length>0)cb.classList.add('visible');else cb.classList.remove('visible');
  renderSelTagBar();
  if(selectedTags.length>0)_doSearch();else clearSearch();
}
function pickHomeTag(tag){
  exitBrowse();
  if(selectedTags.indexOf(tag)<0){
    selectedTags.push(tag);
    var chip=document.querySelector('.tag-filter-chip[data-tag="'+tag+'"]');
    if(chip)chip.classList.add('active');
    var cb=document.getElementById('tagClearBtn');if(cb)cb.classList.add('visible');
  }
  renderSelTagBar();
  _doSearch();
}

loadTagsSummary();

function toggleTagFilter(el){
  var tag=el.dataset.tag;
  var idx=selectedTags.indexOf(tag);
  if(idx>=0){selectedTags.splice(idx,1);el.classList.remove('active');}
  else{selectedTags.push(tag);el.classList.add('active');}
  var clearBtn=document.getElementById('tagClearBtn');
  if(selectedTags.length>0)clearBtn.classList.add('visible');else clearBtn.classList.remove('visible');

  renderSelTagBar();
  exitBrowse();
  _doSearch();
}

function clearTagFilter(){
  selectedTags=[];
  document.querySelectorAll('.tag-filter-chip.active').forEach(function(e){e.classList.remove('active')});
  var cb=document.getElementById('tagClearBtn');if(cb)cb.classList.remove('visible');
  renderSelTagBar();
  var kw=document.getElementById('kw').value.trim();
  if(!kw&&!browseMode)clearSearch();else _doSearch();
}

function toggleEditMode(){
  editMode=!editMode;
  var btn=document.getElementById('editToggle');
  var badge=document.getElementById('editBadge');
  if(editMode){
    btn.textContent='✅ 結束編輯';
    btn.style.background='rgba(255,200,0,.3)';
    badge.style.display='';
  }else{
    btn.textContent='✏️ 編輯標籤';
    btn.style.background='rgba(255,255,255,.15)';
    badge.style.display='none';
    closePopover();
  }
  /* 重新渲染目前結果 */
  var lastD=window._lastSearchResult;
  if(lastD)renderResults(lastD,window._lastKw||'');
}

/* ── Popover 控制 ── */
function renderPopoverTabs(itemId){
  var existing=cardTags[itemId]||[];
  var kw=(document.getElementById('popSearch')||{}).value||'';
  kw=kw.trim().toLowerCase();
  var groups={};
  var order=['裝置型號','問題類型','配件','系統與軟體','未分群'];
  allTagsData.forEach(function(x){
    var t=x.tag||x.name||x; var g=x.group||'未分群';
    if(existing.indexOf(t)<0){if(!groups[g])groups[g]=[];groups[g].push(t);}
  });
  var tabBar=document.getElementById('popTabBar');
  var tagList=document.getElementById('popTagList');
  if(kw){
    // 搜尋模式：跨群組過濾，隱藏頁籤
    tabBar.style.display='none';
    var matched=[];
    var exactMatch=false;
    allTagsData.forEach(function(x){
      var t=x.tag||x.name||x;
      if(existing.indexOf(t)>=0)return;
      if(t.toLowerCase().indexOf(kw)>=0){matched.push(t);}
      if(t.toLowerCase()===kw)exactMatch=true;
    });
    var chips=matched.map(function(t){
      return '<div class="pop-tag" data-id="'+itemId+'" data-tag="'+escAttr(t)+'" onclick="handlePopTag(this)">'+esc(t)+'</div>';
    }).join('');
    if(!exactMatch){
      var kwRaw=(document.getElementById('popSearch')||{}).value||'';
      chips+='<div class="pop-tag" style="background:#e3f2fd;color:#1565c0;border-color:#90caf9;" data-id="'+itemId+'" data-tag="'+escAttr(kwRaw.trim())+'" onclick="createAndAddTag(this)">＋ 新增「'+esc(kwRaw.trim())+'」</div>';
    }
    tagList.innerHTML=chips||'<span style="font-size:11px;color:#aaa;">無符合標籤</span>';
    return true;
  }
  // 正常模式：群組頁籤
  tabBar.style.display='';
  var allGrps=[];
  order.forEach(function(g){if(groups[g]&&groups[g].length)allGrps.push(g);});
  Object.keys(groups).forEach(function(g){if(order.indexOf(g)<0&&groups[g].length)allGrps.push(g);});
  var hasAny=allGrps.length>0;
  if(!popActiveGroup||allGrps.indexOf(popActiveGroup)<0)popActiveGroup=allGrps[0]||null;
  tabBar.innerHTML=allGrps.map(function(g){
    var isAct=g===popActiveGroup;
    var s=isAct?'background:#e8f5e9;color:#1b5e20;border:.5px solid #a5d6a7;font-weight:500':'color:#666;background:transparent;border:.5px solid transparent';
    return '<button class="pop-grp-tab" data-grp="'+escAttr(g)+'" style="font-size:10px;padding:2px 8px;border-radius:5px;cursor:pointer;font-family:inherit;'+s+'">'+esc(g)+'</button>';
  }).join('');
  tabBar.querySelectorAll('.pop-grp-tab').forEach(function(btn){
    btn.addEventListener('click',function(e){e.stopPropagation();popActiveGroup=this.dataset.grp;renderPopoverTabs(itemId);});
  });
  var chips=(groups[popActiveGroup]||[]).map(function(t){
    return '<div class="pop-tag" data-id="'+itemId+'" data-tag="'+escAttr(t)+'" onclick="handlePopTag(this)">'+esc(t)+'</div>';
  }).join('');
  tagList.innerHTML=chips;
  return hasAny||true;
}
function onPopSearch(){
  if(popTargetId!=null)renderPopoverTabs(popTargetId);
}
function createAndAddTag(el){
  var tag=(el.dataset.tag||'').trim();
  if(!tag)return;
  var itemId=parseInt(el.dataset.id);
  addTag(itemId,tag);
  // 新標籤加入 allTagsData 讓下次搜尋可見
  var exists=allTagsData.some(function(x){return (x.tag||x.name||x)===tag;});
  if(!exists)allTagsData.push({tag:tag,count:1,group:'未分群'});
}
function openPopover(itemId, btnEl){
  popTargetId=itemId;
  var srch=document.getElementById('popSearch');if(srch)srch.value='';
  var pop=document.getElementById('tagPopover');
  if(!renderPopoverTabs(itemId)){
    pop.style.display='none';
    return;
  }
  var rect=btnEl.getBoundingClientRect();
  pop.style.display='block';
  var popH=Math.min(260,pop.scrollHeight||260);var popW=360;
  var spaceBelow=window.innerHeight-rect.bottom-8;
  var spaceAbove=rect.top-8;
  if(spaceBelow>=popH||spaceBelow>=spaceAbove){
    pop.style.top=(rect.bottom+6)+'px';
    pop.style.bottom='';
    pop.style.maxHeight=Math.max(120,spaceBelow-8)+'px';
  }else{
    pop.style.top='';
    pop.style.bottom=(window.innerHeight-rect.top+6)+'px';
    pop.style.maxHeight=Math.max(120,spaceAbove-8)+'px';
  }
  var left=Math.min(rect.left, window.innerWidth-popW-12);
  pop.style.left=Math.max(8,left)+'px';
}
function closePopover(){
  document.getElementById('tagPopover').style.display='none';
  popTargetId=null;
}
document.addEventListener('click',function(e){
  var pop=document.getElementById('tagPopover');
  if(pop.style.display==='block'&&!pop.contains(e.target)&&!e.target.classList.contains('tag-add')){
    closePopover();
  }
});

/* ── 年份勾選 ── */
function getCheckedYears(){
  if(document.getElementById('yrAll').checked)return[];
  return Array.from(document.querySelectorAll('.yr-ck:checked')).map(function(c){return c.value});
}
function toggleAllYrs(cb){
  document.querySelectorAll('.yr-ck').forEach(function(c){c.checked=cb.checked});
  updateScopeTxt();
}
function onYrCkChange(){
  var all=document.querySelectorAll('.yr-ck'),ck=document.querySelectorAll('.yr-ck:checked');
  document.getElementById('yrAll').checked=(all.length===ck.length);
  updateScopeTxt();
}
function updateScopeTxt(){
  var years=getCheckedYears();
  document.getElementById('scopeTxt').textContent='查詢範圍：'+(years.length===0?'全部年份':years.join('、'));
}

/* ── 側欄年份瀏覽 ── */
function browseYear(el,y){
  browseMode=true;browseYr=y;
  selectedTags=[];
  document.querySelectorAll('.tag-filter-chip').forEach(function(e){e.classList.remove('active')});
  var cb=document.getElementById('tagClearBtn');if(cb)cb.classList.remove('visible');
  document.getElementById('kw').value='';
  document.querySelectorAll('.yr-link').forEach(function(e){e.classList.remove('active')});
  el.classList.add('active');
  document.getElementById('scopeTxt').textContent='瀏覽：'+y+(y==='日常'?'新增':' 年');
  _doSearch();
}

/* ── 退出瀏覽模式 ── */
function exitBrowse(){
  browseMode=false;browseYr='';
  document.querySelectorAll('.yr-link').forEach(function(e){e.classList.remove('active')});
  updateScopeTxt();
}

function fill(t){exitBrowse();document.getElementById('kw').value=t;_doSearch()}
function clearSearch(){
  document.getElementById('kw').value='';
  document.getElementById('kw').focus();
  exitBrowse();
  document.getElementById('cntBadge').style.display='none';
  document.getElementById('results').innerHTML='<div class="empty" id="homeState"><div style="font-size:15px;font-weight:500;color:#333;margin-bottom:4px">HyRead 客服歷史問答查詢</div><div style="font-size:12px;color:#aaa;margin-bottom:16px">點選標籤快速篩選，或直接輸入關鍵字搜尋</div><div style="width:100%;margin-bottom:14px"><div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px"><div style="font-size:10px;color:#bbb;letter-spacing:.5px">點選標籤篩選</div><button id="homeClearBtn" onclick="clearTagFilter()" style="font-size:10px;color:#999;padding:3px 10px;border:.5px solid #e0e0e0;border-radius:99px;cursor:pointer;background:transparent;width:auto;">✕ 清除篩選</button></div><div id="homeTabBar" class="home-tab-bar"></div><div id="homeTagChips" class="chips" style="justify-content:flex-start"></div></div></div>';
  if(allTagsData.length){var hEl=document.getElementById('homeTagChips');if(hEl)renderHomeTagChips(allTagsData,hEl);}
}
function esc(t){return(t||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function escAttr(t){return(t||'').replace(/"/g,'&quot;')}
function hilite(text,kw){
  if(!kw)return text;
  var result='',lower=text.toLowerCase(),kl=kw.toLowerCase(),i=0;
  while(i<text.length){
    var idx=lower.indexOf(kl,i);
    if(idx<0){result+=text.slice(i);break}
    result+=text.slice(i,idx)+'<span class="hi">'+text.slice(idx,idx+kw.length)+'</span>';
    i=idx+kw.length;
  }
  return result;
}
function search(){
  var kw=document.getElementById('kw').value.trim();
  if(kw)exitBrowse();
  _doSearch();
}
function _doSearch(page){
  currentPage=page||1;
  var kw=document.getElementById('kw').value.trim();
  var years=browseMode?[browseYr]:getCheckedYears();
  if(!kw&&!selectedTags.length&&!browseMode)return;
  document.getElementById('results').innerHTML='<div class="loading">搜尋中...</div>';
  document.getElementById('cntBadge').style.display='none';
  fetch('/qa/api/search',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({keyword:kw,years:years,tags:selectedTags,page:currentPage})})
  .then(function(r){return r.json()}).then(function(d){renderResults(d,kw)})
  .catch(function(){document.getElementById('results').innerHTML='<div class="err">查詢失敗，請稍後再試</div>'});
}
/* 將 Q/A 文字中的 （時間 姓名） 括號部分弱化為灰色小字 */
function muteMetaInfo(text){
  return esc(text).replace(/（([^）]{4,60})）/g,function(m,inner){
    return '<span class="meta-info">（'+inner+'）</span>';
  });
}

/* 渲染一張卡片的 tags 區塊 */
function renderTagsHtml(itemId, tags){
  var arr=tags||[];
  cardTags[itemId]=arr.slice();
  var html='<div class="card-tags" id="tags-'+itemId+'">';
  if(editMode){
    arr.forEach(function(t){
      html+='<span class="tag tag-cat tag-edit" style="position:relative">'
        +esc(t)
        +'<button class="tag-ren" data-id="'+itemId+'" data-tag="'+esc(t)+'" onclick="openRenamePopup(this);event.stopPropagation()" title="改名">✏</button>'
        +'<button class="tag-del" data-id="'+itemId+'" data-tag="'+esc(t)+'" onclick="handleDelTag(this)" title="移除">✕</button>'
        +'</span>';
    });
    html+='<button class="tag-add" onclick="openPopover('+itemId+',this)">＋ 新增標籤</button>';
  }else{
    arr.forEach(function(t){
      html+='<span class="tag tag-cat">'+esc(t)+'</span>';
    });
  }
  html+='</div>';
  return html;
}

function renderResults(d,kw){
  window._lastSearchResult=d;
  window._lastKw=kw;
  var badge=document.getElementById('cntBadge');
  var browseLabel=browseYr+(browseYr==='日常'?'新增':' 年');
  if(!d.results||d.results.length===0){
    badge.style.display='none';
    var label=browseMode?browseLabel:(kw?'「'+esc(kw)+'」':'');
    document.getElementById('results').innerHTML='<div class="empty"><div>找不到相關資料</div><div style="font-size:12px;margin-top:4px">請換個關鍵字或標籤試試</div></div>';
    return;
  }
  badge.textContent='找到 '+d.total+' 筆';badge.style.display='';
  var total=d.total,page=d.page||1,totalPages=d.total_pages||1,pageSize=d.page_size||50;
  var startNum=(page-1)*pageSize+1,endNum=Math.min(page*pageSize,total);
  var parts=[];
  if(selectedTags.length)parts.push('標籤：'+selectedTags.map(function(t){return esc(t)}).join(' × '));
  if(kw)parts.push('關鍵字：「'+esc(kw)+'」');
  if(browseMode)parts.push(browseLabel);
  var cntTxt=(parts.length?parts.join('　')+'　— ':'')+'共 '+total+' 筆Q&A';
  if(total>pageSize)cntTxt+='，第 '+page+'/'+totalPages+' 頁（'+startNum+'～'+endNum+' 筆）';
  var html='<div class="count-row">'+cntTxt+'</div>';
  d.results.forEach(function(r,idx){
    var itemId=r.id;
    var tags=Array.isArray(r.tags)&&r.tags.length?r.tags:
             (r.category||'').split(/[、,，]/).filter(function(c){return c.trim()}).slice(0,3);
    var qBody=(r.q_text||'').replace(/^Q\\d+[：:]\\s*/,'');
    html+='<div class="card" data-id="'+itemId+'">'
      +'<div class="q-row"><div class="q-icon">Q'+(idx+1)+'</div>'
      +'<div class="q-txt">'+hilite(muteMetaInfo(qBody),kw)+'</div>'
      +'<div style="font-size:10px;color:#ccc;flex-shrink:0;align-self:flex-start;padding-top:2px;">ID'+itemId+'</div></div>'
      +renderTagsHtml(itemId,tags)
      +'<div class="a-lbl">回答</div>'
      +'<div class="a-txt">'+hilite(muteMetaInfo(r.a_text||''),kw)+'</div>'
      +'</div>';
  });
  // 分頁列
  if(totalPages>1){
    html+='<div class="pager">';
    if(page>1)html+='<button class="pg-btn" onclick="_doSearch('+(page-1)+')">&#8592; 上一頁</button>';
    var start=Math.max(1,page-3),end=Math.min(totalPages,page+3);
    for(var p=start;p<=end;p++){
      if(p===page)html+='<button class="pg-btn pg-cur">'+p+'</button>';
      else html+='<button class="pg-btn" onclick="_doSearch('+p+')">'+p+'</button>';
    }
    if(page<totalPages)html+='<button class="pg-btn" onclick="_doSearch('+(page+1)+')">下一頁 &#8594;</button>';
    html+='</div>';
  }
  document.getElementById('results').innerHTML=html;
}

/* ── 標籤操作 ── */
function updateTagsOnServer(itemId, tags, onSuccess){
  fetch('/qa/api/update_tags',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id:itemId,tags:tags})})
  .then(function(r){return r.json()}).then(function(d){
    if(d.ok){
      cardTags[itemId]=d.tags;
      /* 重新渲染該卡片的 tags 區塊 */
      var el=document.getElementById('tags-'+itemId);
      if(el)el.outerHTML=renderTagsHtml(itemId,d.tags);
      if(onSuccess)onSuccess();
    }else{
      alert('更新失敗：'+d.error);
    }
  }).catch(function(){alert('網路錯誤，請稍後再試');});
}

function removeTag(itemId, tag){
  var cur=(cardTags[itemId]||[]).filter(function(t){return t!==tag});
  updateTagsOnServer(itemId,cur,null);
}

function addTag(itemId, tag){
  closePopover();
  var cur=(cardTags[itemId]||[]);
  if(cur.indexOf(tag)>=0)return;
  var next=cur.concat([tag]);
  updateTagsOnServer(itemId,next,null);
}
function handleDelTag(el){
  removeTag(parseInt(el.dataset.id), el.dataset.tag);
}
function handlePopTag(el){
  addTag(parseInt(el.dataset.id), el.dataset.tag);
}

var _renamePopupEl=null;
function openRenamePopup(btn){
  closeRenamePopup();
  var tag=btn.dataset.tag;
  var itemId=parseInt(btn.dataset.id);
  var pop=document.createElement('div');
  pop.className='rename-popup';
  pop.innerHTML='<div style="font-size:11px;color:#888;margin-bottom:5px">全域改名（所有 QA 同步）</div>'
    +'<input id="_renInp" data-old="'+esc(tag)+'" value="'+esc(tag)+'" />'
    +'<div class="rename-popup-row">'
    +'<button id="_renOkBtn" class="ok" onclick="confirmRename()">確認</button>'
    +'<button onclick="closeRenamePopup()">取消</button>'
    +'</div>';
  btn.closest('span').appendChild(pop);
  _renamePopupEl=pop;
  var inp=document.getElementById('_renInp');
  if(inp){
    inp.focus();inp.select();
    inp.addEventListener('keydown',function(e){
      if(e.key==='Enter'){e.preventDefault();confirmRename();}
      if(e.key==='Escape'){closeRenamePopup();}
    });
  }
  pop.addEventListener('click',function(e){e.stopPropagation();});
}
function closeRenamePopup(){
  if(_renamePopupEl){_renamePopupEl.remove();_renamePopupEl=null;}
}
function confirmRename(forceMerge){
  var inp=document.getElementById('_renInp');
  if(!inp)return;
  var oldName=inp.dataset.old||'';
  var newName=inp.value.trim();
  if(!newName){alert('新名稱不可空白');return;}
  if(newName===oldName){closeRenamePopup();return;}
  var okBtn=document.getElementById('_renOkBtn');
  if(okBtn){okBtn.disabled=true;okBtn.textContent='存檔中...';}
  fetch('/qa/api/rename_tag',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({old_name:oldName,new_name:newName,force_merge:!!forceMerge})})
  .then(function(r){return r.json();}).then(function(d){
    if(d.conflict){
      var pop=_renamePopupEl;
      if(pop){
        pop.innerHTML='<div style="font-size:12px;font-weight:500;color:#854f0b;margin-bottom:6px">&#9888; 標籤已存在</div>'
          +'<div style="font-size:11px;color:#666;margin-bottom:10px;line-height:1.5">「'+esc(newName)+'」已存在。<br>是否將「'+esc(oldName)+'」合併至「'+esc(newName)+'」？</div>'
          +'<div style="display:flex;gap:5px">'
          +'<button onclick="confirmRename(true)" style="font-size:11px;padding:4px 10px;border-radius:6px;background:#e65100;border:none;color:#fff;cursor:pointer">合併</button>'
          +'<button onclick="closeRenamePopup()" style="font-size:11px;padding:4px 10px;border-radius:6px;border:0.5px solid #ddd;background:transparent;cursor:pointer">取消</button>'
          +'</div>';
        var fakeInp=document.createElement('input');
        fakeInp.id='_renInp';fakeInp.dataset.old=oldName;fakeInp.value=newName;
        fakeInp.style.display='none';pop.appendChild(fakeInp);
      }
      return;
    }
    if(d.ok){
      closeRenamePopup();
      var affected=d.updated||0;
      document.querySelectorAll('[data-tag="'+oldName+'"]').forEach(function(el){
        el.dataset.tag=newName;
        var span=el.closest('span.tag');
        if(span){var txt=span.childNodes[0];if(txt&&txt.nodeType===3)txt.textContent=newName;}
      });
      Object.keys(cardTags).forEach(function(id){
        cardTags[id]=cardTags[id].map(function(t){return t===oldName?newName:t;});
      });
      if(affected>0){loadSidebarTags();loadHomeTags();}
    }else{var okBtn=document.getElementById('_renOkBtn');if(okBtn){okBtn.disabled=false;okBtn.textContent='確認';}alert('改名失敗：'+(d.error||'未知錯誤'));}
  }).catch(function(){var okBtn=document.getElementById('_renOkBtn');if(okBtn){okBtn.disabled=false;okBtn.textContent='確認';}alert('網路錯誤，請稍後再試');});
}
document.addEventListener('click',function(){closeRenamePopup();});
</script></body></html>'''
    return page.replace('__ADMIN_BTN__', admin_btn).replace('__USER_LABEL__', user_label).replace('__EDIT_TAG_BTN__', edit_tag_btn)

# ──────────────────────────────────────────────
# Q&A API
# ──────────────────────────────────────────────
@app.route("/qa/api/tag_definitions")
@require_qa
def qa_tag_definitions():
    """回傳 tag_definitions 完整清單（供查詢頁 Popover 與首頁分區使用）"""
    try:
        rows = supabase.table("tag_definitions").select("*").order("sort_order").execute().data or []
        return jsonify(rows)
    except Exception as e:
        return jsonify([])

@app.route("/qa/api/categories_summary")
@require_qa
def qa_categories_summary():
    """回傳各標籤計數（從 qa_items.tags），同時附帶 tag_definitions 的 type 資訊"""
    try:
        from collections import Counter
        # 1. 從 qa_items 計算每個 tag 的出現次數
        rows = supabase.table("qa_items").select("tags").execute().data
        counter = Counter()
        for r in rows:
            for t in (r.get("tags") or []):
                t = t.strip()
                if t:
                    counter[t] += 1
        # 2. 嘗試讀取 tag_definitions；若資料表不存在則降級輸出所有 tag
        try:
            tag_defs = supabase.table("tag_definitions").select("*").order("sort_order").execute().data or []
        except Exception:
            tag_defs = []
        if tag_defs:
            defined_names = {td["name"] for td in tag_defs}
            result = []
            for td in tag_defs:
                result.append({"cat": td["name"], "cnt": counter.get(td["name"], 0),
                               "type": td["type"], "sort_order": td["sort_order"]})
            for name, cnt in counter.most_common():
                if name not in defined_names:
                    result.append({"cat": name, "cnt": cnt, "type": "未定義", "sort_order": 999})
        else:
            # tag_definitions 尚未建立，直接輸出前10個 tag
            result = [{"cat": k, "cnt": v, "type": "主分類", "sort_order": i}
                      for i, (k, v) in enumerate(counter.most_common(10), 1)]
        return jsonify(result)
    except Exception as e:
        return jsonify([])

@app.route("/qa/api/batches")
@require_qa
def qa_batches():
    result = supabase.table("qa_results").select("id,year,batch_num,title,analyzed_at,total_msgs,categories,user_category,category_confirmed").order("id").execute()
    return jsonify(result.data)

@app.route("/qa/api/tags_summary")
@require_qa
def qa_tags_summary():
    """回傳所有 tags 及出現次數，依次數由高到低排序（分頁取全量）"""
    try:
        from collections import Counter
        counter = Counter()
        offset = 0
        batch = 1000
        while True:
            rows = supabase.table("qa_items").select("tags").range(offset, offset + batch - 1).execute().data
            if not rows:
                break
            for r in rows:
                for t in (r.get("tags") or []):
                    t = t.strip()
                    if t:
                        counter[t] += 1
            if len(rows) < batch:
                break
            offset += batch
        result = [{"tag": k, "cnt": v} for k, v in counter.most_common()]
        return jsonify(result)
    except Exception as e:
        print("tags_summary error:", e, flush=True)
        return jsonify([])

@app.route("/qa/api/search", methods=["POST"])
@require_qa
def qa_search():
    data = request.get_json()
    keyword = (data.get("keyword") or "").strip()
    years = data.get("years", [])
    tags = data.get("tags", [])   # 多選標籤篩選
    page = int(data.get("page", 1))
    page_size = 50
    if not keyword and not tags and not years:
        return jsonify({"results": [], "total": 0, "page": 1, "total_pages": 0})
    try:
        # 兩段式搜尋：先搜 q_text+a_text，無結果才擴大到 source_text
        source_text_fallback = False

        def build_query(base, kw, use_source):
            if kw:
                if use_source:
                    f = "q_text.ilike.%" + kw + "%,a_text.ilike.%" + kw + "%,source_text.ilike.%" + kw + "%"
                else:
                    f = "q_text.ilike.%" + kw + "%,a_text.ilike.%" + kw + "%"
                base = base.or_(f)
            if years:
                base = base.in_("year", years)
            if tags:
                for tag in tags:
                    base = base.contains("tags", [tag])
            return base

        # 第一次：只搜 q_text + a_text
        count_res = build_query(supabase.table("qa_items").select("id", count="exact"), keyword, False).execute()
        total = count_res.count or 0

        # 無結果且有關鍵字 → 擴大搜尋含 source_text
        if total == 0 and keyword:
            count_res = build_query(supabase.table("qa_items").select("id", count="exact"), keyword, True).execute()
            total = count_res.count or 0
            source_text_fallback = True

        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size

        # 取當頁資料
        rows = build_query(supabase.table("qa_items").select("*"), keyword, source_text_fallback).order("id").range(start, start + page_size - 1).execute().data
        return jsonify({"results": rows, "total": total,
                        "page": page, "total_pages": total_pages, "page_size": page_size,
                        "source_text_fallback": source_text_fallback})
    except Exception as e:
        print("搜尋失敗：", e, flush=True)
        return jsonify({"results": [], "total": 0, "error": str(e)})

@app.route("/qa/api/update_tags", methods=["POST"])
@require_qa
def qa_update_tags():
    """更新單筆 qa_items 的 tags 陣列，並同步 tag_groups"""
    data = request.get_json()
    item_id = data.get("id")
    tags    = data.get("tags", [])
    if not item_id:
        return jsonify({"ok": False, "error": "missing id"}), 400
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).strip() for t in tags if str(t).strip()]
    try:
        old_row = supabase.table("qa_items").select("tags").eq("id", item_id).single().execute().data
        old_tags = set(old_row.get("tags") or []) if old_row else set()
        new_tags_set = set(tags)
        added   = new_tags_set - old_tags
        removed = old_tags - new_tags_set

        supabase.table("qa_items").update({"tags": tags}).eq("id", item_id).execute()

        if added:
            existing = supabase.table("tag_groups").select("tag_name").in_("tag_name", list(added)).execute().data or []
            existing_names = {r["tag_name"] for r in existing}
            for t in added:
                if t not in existing_names:
                    supabase.table("tag_groups").upsert(
                        {"tag_name": t, "group_name": "未分群"},
                        on_conflict="tag_name"
                    ).execute()

        for t in removed:
            still_used = supabase.table("qa_items").select("id").contains("tags", [t]).neq("id", item_id).limit(1).execute().data or []
            if not still_used:
                supabase.table("tag_groups").delete().eq("tag_name", t).execute()

        return jsonify({"ok": True, "tags": tags})
    except Exception as e:
        print("update_tags 失敗：", e, flush=True)
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/qa/api/rename_tag", methods=["POST"])
@require_qa
def qa_rename_tag():
    """全域改名：更新所有 qa_items.tags + tag_groups.tag_name"""
    data = request.get_json()
    old_name = (data.get("old_name") or "").strip()
    new_name = (data.get("new_name") or "").strip()
    force_merge = bool(data.get("force_merge"))
    if not old_name or not new_name:
        return jsonify({"ok": False, "error": "名稱不可空白"}), 400
    if old_name == new_name:
        return jsonify({"ok": True, "updated": 0})
    try:
        exists = supabase.table("tag_groups").select("tag_name").eq("tag_name", new_name).execute().data
        if exists and not force_merge:
            return jsonify({"ok": False, "conflict": True, "new_name": new_name})
        updated = 0
        offset = 0
        while True:
            rows = supabase.table("qa_items").select("id,tags").contains("tags", [old_name]).range(offset, offset + 199).execute().data or []
            for row in rows:
                new_tags = [new_name if t == old_name else t for t in (row["tags"] or [])]
                supabase.table("qa_items").update({"tags": new_tags}).eq("id", row["id"]).execute()
                updated += 1
            if len(rows) < 200:
                break
            offset += 200
        if exists:
            supabase.table("tag_groups").delete().eq("tag_name", old_name).execute()
        else:
            supabase.table("tag_groups").update({"tag_name": new_name}).eq("tag_name", old_name).execute()
        return jsonify({"ok": True, "updated": updated, "merged": bool(exists)})
    except Exception as e:
        print("rename_tag 失敗：", e, flush=True)
        return jsonify({"ok": False, "error": str(e)}), 500

# ──────────────────────────────────────────────
# 管理介面主頁
# ──────────────────────────────────────────────
@app.route("/admin")
@require_admin
def admin_page():
    return '''<!DOCTYPE html>
<html lang="zh-TW"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HyRead Q&A 管理介面</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Microsoft JhengHei",sans-serif;background:#f5f7fa;min-height:100vh}
#adminToast{position:fixed;bottom:30px;left:50%;transform:translateX(-50%);background:#323232;color:#fff;padding:10px 22px;border-radius:8px;font-size:13px;z-index:9999;display:none;white-space:nowrap;box-shadow:0 4px 12px rgba(0,0,0,.25)}
.topbar{background:#00b900;color:#fff;padding:11px 18px;display:flex;align-items:center;gap:8px;font-size:14px;font-weight:500}
.topbar a{color:rgba(255,255,255,.85);font-size:11px;padding:4px 10px;border-radius:6px;border:.5px solid rgba(255,255,255,.3);text-decoration:none;margin-left:auto}
.tabs{display:flex;background:#fff;border-bottom:1px solid #e0e0e0;padding:0 18px}
.tab{padding:12px 20px;font-size:13px;color:#777;cursor:pointer;border-bottom:2px solid transparent}
.tab.active{color:#00b900;border-bottom-color:#00b900;font-weight:500}
.panel{display:none;padding:20px}
.panel.active{display:block}
.card{background:#fff;border-radius:10px;border:.5px solid #e0e0e0;padding:16px 18px;margin-bottom:16px}
.card-title{font-size:13px;font-weight:500;color:#333;margin-bottom:12px;display:flex;align-items:center;gap:6px}
.add-row{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}
input[type=text]{padding:8px 12px;border:.5px solid #ddd;border-radius:6px;font-size:13px;font-family:inherit;outline:none}
input[type=text]:focus{border-color:#00b900}
select{padding:8px 10px;border:.5px solid #ddd;border-radius:6px;font-size:12px;font-family:inherit}
.btn-green{padding:8px 16px;background:#00b900;color:#fff;border:none;border-radius:6px;font-size:12px;cursor:pointer}
.btn-outline{padding:6px 12px;background:transparent;color:#777;border:.5px solid #ddd;border-radius:6px;font-size:11px;cursor:pointer}
.btn-outline:hover{border-color:#e53935;color:#e53935}
.tags{display:flex;flex-wrap:wrap;gap:7px}
.tag{display:flex;align-items:center;gap:5px;padding:5px 10px;border-radius:99px;font-size:12px}
.tag-phrase{background:#e3f2fd;color:#1565c0}
.tag-sender{background:#fce4ec;color:#880e4f}
.tag-keyword{background:#fff3e0;color:#e65100}
.tag-system{background:#f5f5f5;color:#aaa}
.tag-del{cursor:pointer;opacity:.6;font-size:14px}
.tag-del:hover{opacity:1}
.sec-lbl{font-size:11px;color:#aaa;margin:12px 0 6px;letter-spacing:.3px}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;padding:8px 10px;border-bottom:1px solid #eee;color:#777;font-weight:500}
td{padding:9px 10px;border-bottom:.5px solid #f5f5f5;color:#333}
tr:hover td{background:#fafafa}
.cat-disp{display:flex;align-items:center;gap:6px}
.cat-pill{font-size:11px;padding:3px 9px;border-radius:99px;background:#e8f5e9;color:#2e7d32}
.cat-edit{font-size:11px;padding:3px 9px;border-radius:99px;background:#fff8e1;color:#f57f17}
.edit-inline{display:flex;gap:6px;align-items:center}
.edit-inline input{font-size:12px;padding:5px 8px;width:160px}
.btn-sm{padding:5px 10px;font-size:11px;border:none;border-radius:5px;cursor:pointer;background:#00b900;color:#fff}
.btn-cancel{background:#f5f5f5;color:#777}
.stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:16px}
.stat-card{background:#f9f9f9;border-radius:8px;padding:14px;text-align:center}
.stat-num{font-size:24px;font-weight:500;color:#00b900}
.stat-lbl{font-size:11px;color:#aaa;margin-top:4px}
.bar-row{display:flex;align-items:center;gap:10px;margin-bottom:7px}
.bar-name{font-size:12px;color:#555;width:60px;text-align:right;flex-shrink:0}
.bar-wrap{flex:1;background:#f0f0f0;border-radius:99px;height:8px;overflow:hidden}
.bar-fill{height:100%;background:#00b900;border-radius:99px}
.bar-val{font-size:11px;color:#aaa;width:30px}
.msg{font-size:12px;color:#00b900;margin-top:8px}
.msg.err{color:#e53935}
</style></head><body>
<div id="adminToast"></div>
<div class="topbar">⚙ HyRead Q&A 管理介面<span id="adminUsername" style="font-size:11px;opacity:.75;margin-left:8px;"></span>
  <a href="/qa">← 回查詢頁面</a>
  <a href="/admin/logout" style="margin-left:6px">登出</a>
</div>
<div class="tabs">
  <div class="tab active" data-tab="filter" onclick="showTab(this,'filter')">🚫 過濾詞句</div>
  <div class="tab" data-tab="category" onclick="showTab(this,'category')">🏷 分類管理</div>
  <div class="tab" data-tab="stats" onclick="showTab(this,'stats')">📊 分析總覽</div>
  <div class="tab" data-tab="token" onclick="showTab(this,'token')">⚡ Token 用量</div>
  <div class="tab" data-tab="users" onclick="showTab(this,'users')">👤 帳號管理</div>
  <div class="tab" data-tab="groupmgr" onclick="showTab(this,'groupmgr')">🗂️ 標籤群組管理</div>
</div>

<!-- 過濾詞句 -->
<div class="panel active" id="tab-filter">
  <div class="card">
    <div class="card-title">➕ 新增過濾詞句</div>
    <div class="add-row">
      <input type="text" id="newWord" placeholder="輸入要過濾的詞句..." style="flex:1;min-width:200px">
      <select id="newType">
        <option value="phrase">短句（完整符合）</option>
        <option value="sender">發話者名稱</option>
        <option value="keyword">關鍵字（包含即過濾）</option>
      </select>
      <input type="text" id="newNote" placeholder="備註（選填）" style="width:130px">
      <button class="btn-green" onclick="addWord()">新增</button>
    </div>
    <div id="addMsg"></div>
  </div>
  <div class="card">
    <div class="card-title">📋 目前過濾清單</div>
    <div id="filterList"><div style="color:#aaa;font-size:13px">載入中...</div></div>
  </div>
</div>

<!-- 分類管理 -->
<div class="panel" id="tab-category">
  <div class="card">
    <div class="card-title">🏷 批次分類管理
      <select id="catYrFilter" onchange="loadCategories()" style="margin-left:auto;font-size:12px">
        <option value="">全部年份</option>
        <option>2019</option><option>2020</option><option>2021</option>
        <option>2022</option><option>2023</option><option>2024</option>
        <option>2025</option><option>2026</option><option value="日常">日常</option>
      </select>
    </div>
    <table>
      <thead><tr><th>批次</th><th>時間</th><th>訊息數</th><th>Gemini 建議分類</th><th>你的分類</th><th>操作</th></tr></thead>
      <tbody id="catTable"><tr><td colspan="6" style="color:#aaa;text-align:center;padding:20px">載入中...</td></tr></tbody>
    </table>
  </div>
</div>

<!-- 分析總覽 -->
<div class="panel" id="tab-stats">
  <div class="card" style="margin-bottom:14px">
    <div class="card-title">🔄 補跑解析舊資料</div>
    <div style="font-size:12px;color:#777;margin-bottom:10px">將已整理的批次資料重新解析存入 qa_items，讓查詢頁面可以搜尋。第一次部署或有新批次時點此執行。</div>
    <div style="display:flex;align-items:center;gap:10px">
      <button class="btn-green" onclick="reparse()">▶ 立即補跑解析</button>
      <span id="reparseMsg" style="font-size:12px;color:#2e7d32"></span>
    </div>
  </div>
  <div class="card" style="margin-bottom:14px">
    <div class="card-title" style="justify-content:space-between">
      <span>📋 歷年 QA 筆數</span>
      <button class="btn-outline" onclick="loadQaYearCount()" id="qaYearRefreshBtn">🔄 更新數據</button>
    </div>
    <div id="qaYearCountArea" style="font-size:12px;color:#aaa;">載入中...</div>
  </div>
  <div class="stat-grid" id="statCards"></div>
  <div class="card">
    <div class="card-title">📅 各年度資料量</div>
    <div id="yearChart"></div>
  </div>
</div>

<!-- 帳號管理 -->
<div class="panel" id="tab-users">
  <div class="card">
    <div class="card-title" style="justify-content:space-between">
      <span>👥 帳號管理</span>
      <div style="display:flex;gap:8px">
        <button class="btn-outline" onclick="openBatchModal()">📋 批次新增</button>
        <button class="btn-green" onclick="openAddModal()">＋ 新增帳號</button>
      </div>
    </div>
    <table>
      <thead><tr><th style="width:40px">ID</th><th>帳號</th><th>顯示名稱</th><th style="width:80px;text-align:center">查詢模組</th><th style="text-align:center">後台權限</th><th style="width:60px">狀態</th><th style="width:80px">操作</th></tr></thead>
      <tbody id="userTableBody"><tr><td colspan="7" style="color:#aaa;text-align:center;padding:20px">載入中...</td></tr></tbody>
    </table>
  </div>
</div>

<!-- 新增帳號 Modal -->
<div id="userAddModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:1000;align-items:center;justify-content:center">
  <div style="background:#fff;border-radius:12px;padding:28px 32px;width:420px;max-width:95vw">
    <div style="font-size:15px;font-weight:500;margin-bottom:20px">＋ 新增帳號</div>
    <div style="display:grid;gap:12px">
      <div><label style="font-size:11px;color:#777;display:block;margin-bottom:4px">帳號 *</label><input id="addUsr" type="text" placeholder="登入用帳號" style="width:100%;padding:8px 10px;border:.5px solid #ddd;border-radius:6px;font-size:13px;box-sizing:border-box"></div>
      <div><label style="font-size:11px;color:#777;display:block;margin-bottom:4px">密碼 *（至少6字元）</label><input id="addPwd" type="text" placeholder="密碼" style="width:100%;padding:8px 10px;border:.5px solid #ddd;border-radius:6px;font-size:13px;box-sizing:border-box"></div>
      <div><label style="font-size:11px;color:#777;display:block;margin-bottom:4px">顯示名稱</label><input id="addDisplayName" type="text" placeholder="姓名（顯示用）" style="width:100%;padding:8px 10px;border:.5px solid #ddd;border-radius:6px;font-size:13px;box-sizing:border-box"></div>
      <div style="display:flex;gap:20px;margin-bottom:4px"><label style="font-size:12px;display:flex;align-items:center;gap:6px;cursor:pointer"><input type="checkbox" id="addCanQuery" checked> 查詢模組</label><label style="font-size:12px;display:flex;align-items:center;gap:6px;cursor:pointer"><input type="checkbox" id="addCanAdmin"> 可進入後台</label></div><div style="padding:6px 10px;background:#f0f9f0;border-radius:6px;border-left:3px solid #a5d6a7;margin-bottom:6px"><div style="font-size:10px;color:#888;margin-bottom:4px">查詢功能細項</div><label style="font-size:11px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="addPerm_tags"> ✏️ 編輯標籤</label></div><div style="padding:8px 10px;background:#f5f5f5;border-radius:6px;border-left:3px solid #ddd"><div style="font-size:10px;color:#999;margin-bottom:6px">後台功能細項</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 16px"><label style="font-size:11px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="addPerm_filter" checked> 過濾詞句</label><label style="font-size:11px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="addPerm_category" checked> 分類管理</label><label style="font-size:11px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="addPerm_stats" checked> 分析總覽</label><label style="font-size:11px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="addPerm_token" checked> Token 用量</label><label style="font-size:11px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="addPerm_users" checked> 帳號管理</label><label style="font-size:11px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="addPerm_groups" checked> 標籤群組管理</label></div></div>
    </div>
    <div id="addModalMsg" style="font-size:12px;margin-top:10px;min-height:18px;color:#e53935"></div>
    <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:20px">
      <button class="btn-outline" onclick="closeAddModal()">取消</button>
      <button class="btn-green" onclick="submitAddUser()">新增</button>
    </div>
  </div>
</div>

<!-- 編輯帳號 Modal -->
<div id="userEditModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:1000;align-items:center;justify-content:center">
  <div style="background:#fff;border-radius:12px;padding:28px 32px;width:420px;max-width:95vw">
    <div style="font-size:15px;font-weight:500;margin-bottom:20px">✏️ 編輯帳號</div>
    <input type="hidden" id="editUserId">
    <div style="display:grid;gap:12px">
      <div><label style="font-size:11px;color:#777;display:block;margin-bottom:4px">帳號（不可修改）</label><input id="editUsrName" type="text" disabled style="width:100%;padding:8px 10px;border:.5px solid #eee;border-radius:6px;font-size:13px;background:#f9f9f9;box-sizing:border-box"></div>
      <div><label style="font-size:11px;color:#777;display:block;margin-bottom:4px">新密碼（留空則不修改）</label><input id="editPwd" type="text" autocomplete="new-password" placeholder="留空不更改密碼" style="width:100%;padding:8px 10px;border:.5px solid #ddd;border-radius:6px;font-size:13px;box-sizing:border-box"></div>
      <div><label style="font-size:11px;color:#777;display:block;margin-bottom:4px">顯示名稱</label><input id="editDisplayName" type="text" style="width:100%;padding:8px 10px;border:.5px solid #ddd;border-radius:6px;font-size:13px;box-sizing:border-box"></div>
      <div style="display:flex;gap:20px;margin-bottom:4px"><label style="font-size:12px;display:flex;align-items:center;gap:6px;cursor:pointer"><input type="checkbox" id="editCanQuery"> 查詢模組</label><label style="font-size:12px;display:flex;align-items:center;gap:6px;cursor:pointer"><input type="checkbox" id="editCanAdmin"> 可進入後台</label><label style="font-size:12px;display:flex;align-items:center;gap:6px;cursor:pointer"><input type="checkbox" id="editIsActive"> 啟用</label></div><div style="padding:6px 10px;background:#f0f9f0;border-radius:6px;border-left:3px solid #a5d6a7;margin-bottom:6px"><div style="font-size:10px;color:#888;margin-bottom:4px">查詢功能細項</div><label style="font-size:11px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="editPerm_tags"> ✏️ 編輯標籤</label></div><div style="padding:8px 10px;background:#f5f5f5;border-radius:6px;border-left:3px solid #ddd"><div style="font-size:10px;color:#999;margin-bottom:6px">後台功能細項</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 16px"><label style="font-size:11px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="editPerm_filter"> 過濾詞句</label><label style="font-size:11px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="editPerm_category"> 分類管理</label><label style="font-size:11px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="editPerm_stats"> 分析總覽</label><label style="font-size:11px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="editPerm_token"> Token 用量</label><label style="font-size:11px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="editPerm_users"> 帳號管理</label><label style="font-size:11px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="editPerm_groups"> 標籤群組管理</label></div></div>
    </div>
    <div id="editModalMsg" style="font-size:12px;margin-top:10px;min-height:18px;color:#e53935"></div>
    <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:20px">
      <button class="btn-outline" onclick="closeEditModal()">取消</button>
      <button class="btn-green" onclick="submitEditUser()">儲存</button>
    </div>
  </div>
</div>

<!-- 批次新增 Modal -->
<div id="userBatchModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:1000;align-items:center;justify-content:center">
  <div style="background:#fff;border-radius:12px;padding:28px 32px;width:540px;max-width:95vw">
    <div style="font-size:15px;font-weight:500;margin-bottom:8px">📋 批次新增帳號</div>
    <div style="font-size:12px;color:#777;margin-bottom:14px">每行一個帳號，格式：帳號,密碼,顯示名稱（第三欄選填）<br>查詢模組預設開啟，後台模組預設關閉。</div>
    <textarea id="batchCsv" rows="8" placeholder="stacy,pass123,陳玲儒&#10;john,pass456,王大明" style="width:100%;padding:10px;border:.5px solid #ddd;border-radius:6px;font-size:12px;font-family:monospace;resize:vertical;box-sizing:border-box"></textarea>
    <div id="batchMsg" style="font-size:12px;margin-top:10px;min-height:18px"></div>
    <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">
      <button class="btn-outline" onclick="closeBatchModal()">取消</button>
      <button class="btn-green" onclick="submitBatch()">批次新增</button>
    </div>
  </div>
</div>

<!-- 群組管理 -->
<div class="panel" id="tab-groupmgr">
  <div class="card">
    <div class="card-title">🗂️ 標籤群組管理</div>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
      <span style="font-size:12px;color:#aaa;">拖曳標籤到其他欄位即可移動群組</span>
      <button onclick="cleanupGhostTags()" id="cleanupBtn" style="font-size:11px;padding:3px 10px;border-radius:6px;border:.5px solid #e57373;color:#c62828;background:transparent;cursor:pointer;">🧹 清除幽靈標籤</button>
      <span id="ghostStats" style="font-size:11px;color:#888;"></span>
      <button onclick="exportTagsCSV(this)" style="font-size:11px;padding:3px 10px;border-radius:6px;border:.5px solid #1565c0;color:#1565c0;background:transparent;cursor:pointer;margin-left:auto;">📥 匯出標籤</button><button onclick="createGroup()">＋ 新增群組</button>
    </div>
    <div id="dragLog" style="font-size:12px;color:#1b5e20;background:#e8f5e9;padding:5px 10px;border-radius:6px;margin-bottom:8px;display:none;"></div>
    <div id="dragBoard" style="display:flex;flex-wrap:wrap;gap:10px;padding-bottom:8px;align-items:flex-start;min-height:120px;"></div>
  </div>
</div>
<script>
var allGroups=[];
var allGroupsData={};
var dragState={};
var customGroupOrder=null;
var colDragSrc=null;

function loadGroups(){
  var board=document.getElementById('dragBoard');
  if(board)board.innerHTML='<span style="font-size:12px;color:#aaa;padding:8px;">載入中...</span>';
  fetch('/admin/api/groups/all_tags').then(r=>r.json()).then(d=>{
    if(d.error){if(board)board.innerHTML='<span style="font-size:12px;color:#e53935;">載入失敗：'+d.error+'</span>';return;}
    allGroupsData=d.groups||{};
    allGroups=Object.keys(allGroupsData).map(function(name){
      return {name:name,count:allGroupsData[name].length};
    });
    var totalTags=allGroups.reduce(function(s,g){return s+g.count;},0);
    var gs=document.getElementById('ghostStats');
    if(gs&&!gs.innerHTML.includes('清除前')){gs.textContent='tag_groups 共 '+totalTags+' 筆';}
    if(!allGroups.length&&board){board.innerHTML='<span style="font-size:12px;color:#aaa;">尚無群組資料（請先執行標籤同步）</span>';return;}
    renderDragBoard();
  }).catch(function(e){if(board)board.innerHTML='<span style="font-size:12px;color:#e53935;">連線失敗</span>';});
}

function escAttrG(s){return (s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;');}
function escHtmlG(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

function renderDragBoard(){
  var board=document.getElementById('dragBoard');
  if(!board)return;
  var orderedGrps;
  if(customGroupOrder){
    orderedGrps=customGroupOrder.filter(function(g){return allGroupsData[g]!==undefined;});
    Object.keys(allGroupsData).forEach(function(g){if(orderedGrps.indexOf(g)<0)orderedGrps.push(g);});
  } else {
    var order=['裝置型號','問題類型','配件','系統與軟體','未分群'];
    orderedGrps=[];
    order.forEach(function(g){if(allGroupsData[g]!==undefined)orderedGrps.push(g);});
    Object.keys(allGroupsData).forEach(function(g){if(order.indexOf(g)<0)orderedGrps.push(g);});
  }
  board.innerHTML='';
  orderedGrps.forEach(function(grpName){
    var tags=(allGroupsData[grpName]||[]).slice().sort();
    var col=document.createElement('div');
    col.style.cssText='min-width:200px;max-width:340px;flex:1;border-radius:8px;border:0.5px solid #e0e0e0;overflow:hidden;background:#fafafa;';
    col.dataset.grp=grpName;
    var hdr='<div class="col-hdr" draggable="true" data-grp="'+escAttrG(grpName)+'" style="padding:7px 10px;background:#f0f0f0;border-bottom:0.5px solid #e0e0e0;display:flex;align-items:center;gap:5px;flex-wrap:wrap;cursor:grab;">'
      +'<span style="font-size:10px;color:#bbb;margin-right:1px;">&#8942;</span>'
      +'<span style="font-size:13px;font-weight:500;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+escHtmlG(grpName)+'</span>'
      +'<span style="font-size:10px;background:#e8f5e9;color:#1b5e20;padding:1px 6px;border-radius:9px;">'+tags.length+'</span>'
      +'<button class="col-act" data-act="rename" data-n="'+escAttrG(grpName)+'" style="font-size:10px;padding:1px 5px;cursor:pointer;">改名</button>'
      +(grpName!=='未分群'?'<button class="col-act" data-act="merge" data-n="'+escAttrG(grpName)+'" style="font-size:10px;padding:1px 5px;cursor:pointer;">合併</button>':'')
      +(grpName!=='未分群'?'<button class="col-act" data-act="delete" data-n="'+escAttrG(grpName)+'" style="font-size:10px;padding:1px 5px;cursor:pointer;color:#c62828;">刪除</button>':'')
      +'</div>';
    var zone='<div class="drag-zone" data-grp="'+escAttrG(grpName)+'" style="padding:8px;min-height:60px;max-height:400px;overflow-y:auto;display:flex;flex-wrap:wrap;gap:5px;align-content:flex-start;">';
    tags.forEach(function(t){
      zone+='<span class="drag-chip" draggable="true" data-tag="'+escAttrG(t)+'" data-grp="'+escAttrG(grpName)+'" style="padding:3px 6px 3px 9px;border-radius:99px;font-size:11px;border:0.5px solid #ddd;background:#fff;cursor:grab;user-select:text;display:inline-flex;align-items:center;gap:2px;position:relative;">'+escHtmlG(t)+'<button class="adm-tag-ren" data-tag="'+escAttrG(t)+'" onclick="openAdminRenamePopup(this);event.stopPropagation()" title="改名" style="cursor:pointer;font-size:9px;width:14px;height:14px;border-radius:50%;border:none;background:rgba(0,0,0,.08);display:inline-flex;align-items:center;justify-content:center;color:#388e3c;flex-shrink:0;padding:0;">✏</button>'+'<button class="adm-tag-del" data-tag="'+escAttrG(t)+'" onclick="deleteTagChip(this);event.stopPropagation()" title="刪除標籤" style="cursor:pointer;font-size:9px;width:14px;height:14px;border-radius:50%;border:none;background:rgba(0,0,0,.08);display:inline-flex;align-items:center;justify-content:center;color:#c62828;flex-shrink:0;padding:0;">✕</button></span>';
    });
    zone+='</div>';
    col.innerHTML=hdr+zone;
    board.appendChild(col);
    var hdrEl=col.querySelector('.col-hdr');
    if(hdrEl){
      hdrEl.addEventListener('dragstart',function(e){
        if(dragState.tag)return;
        colDragSrc=grpName;
        e.dataTransfer.effectAllowed='move';
        e.dataTransfer.setData('text/plain',grpName);
        setTimeout(function(){col.style.opacity='0.4';},0);
      });
      hdrEl.addEventListener('dragend',function(){col.style.opacity='';colDragSrc=null;});
      hdrEl.addEventListener('dragover',function(e){
        if(!colDragSrc||colDragSrc===grpName)return;
        e.preventDefault();col.style.outline='2px solid #66bb6a';
      });
      hdrEl.addEventListener('dragleave',function(){col.style.outline='';});
      hdrEl.addEventListener('drop',function(e){
        e.preventDefault();col.style.outline='';
        if(!colDragSrc||colDragSrc===grpName)return;
        var cur=Array.from(document.querySelectorAll('#dragBoard > [data-grp]')).map(function(c){return c.dataset.grp;});
        var from=cur.indexOf(colDragSrc),to=cur.indexOf(grpName);
        if(from<0||to<0)return;
        cur.splice(from,1);cur.splice(to,0,colDragSrc);
        customGroupOrder=cur;
        renderDragBoard();
      });
    }
    col.querySelectorAll('.col-act').forEach(function(el){
      el.addEventListener('click',function(){
        var n=this.dataset.n,act=this.dataset.act;
        if(act==='rename')renameGroup(n);
        else if(act==='merge')mergeGroup(n);
        else if(act==='delete')deleteGroup(n);
      });
    });
    var zoneEl=col.querySelector('.drag-zone');
    zoneEl.addEventListener('dragover',function(e){e.preventDefault();this.style.background='#e8f5e9';});
    zoneEl.addEventListener('dragleave',function(){this.style.background='';});
    zoneEl.addEventListener('drop',function(e){
      e.preventDefault();this.style.background='';
      var toGrp=this.dataset.grp;
      if(!dragState.tag||dragState.fromGroup===toGrp)return;
      moveTagDrag(dragState.tag,dragState.fromGroup,toGrp);
    });
    col.querySelectorAll('.drag-chip').forEach(function(chip){
      chip.addEventListener('dragstart',function(e){
        dragState={tag:this.dataset.tag,fromGroup:this.dataset.grp};
        e.dataTransfer.effectAllowed='move';
        setTimeout(function(){chip.style.opacity='0.35';},0);
      });
      chip.addEventListener('dragend',function(){this.style.opacity='';});
    });
  });
}

function moveTagDrag(tagName,fromGroup,toGroup){
  fetch('/admin/api/groups/tag',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({tag_name:tagName,group_name:toGroup})})
  .then(r=>r.json()).then(function(d){
    if(d.ok){showDragLog('「'+tagName+'」已移至「'+toGroup+'」');loadGroups();}
    else alert('移動失敗：'+(d.error||''));
  });
}
function showDragLog(msg){
  var el=document.getElementById('dragLog');if(!el)return;
  el.style.display='';el.textContent=msg;
  setTimeout(function(){el.style.display='none';},2500);
}
var _admRenPopEl=null;
function openAdminRenamePopup(btn){
  if(_admRenPopEl){_admRenPopEl.remove();_admRenPopEl=null;}
  var tag=btn.dataset.tag;
  var rect=btn.getBoundingClientRect();
  var pop=document.createElement('div');
  pop.style.cssText='position:fixed;background:#fff;border:1px solid #ddd;border-radius:8px;padding:10px 12px;z-index:9999;min-width:210px;box-shadow:0 2px 12px rgba(0,0,0,.15);';
  pop.innerHTML='<div style="font-size:11px;color:#888;margin-bottom:6px">全域改名（所有 QA 同步）</div>'
    +'<input id="_admRenInp" draggable="false" data-old="'+escAttrG(tag)+'" value="'+escHtmlG(tag)+'" style="width:100%;border:1px solid #ddd;border-radius:6px;padding:5px 8px;font-size:12px;font-family:inherit;box-sizing:border-box;margin-bottom:8px;user-select:text;cursor:text;" />'
    +'<div style="display:flex;gap:5px;">'
    +'<button onclick="confirmAdminRename()" style="font-size:11px;padding:4px 10px;border-radius:6px;background:#00b900;border:none;color:#fff;cursor:pointer;">確認</button>'
    +'<button onclick="closeAdminRenamePopup()" style="font-size:11px;padding:4px 10px;border-radius:6px;border:1px solid #ddd;background:#fff;cursor:pointer;">取消</button>'
    +'</div>';
  var top=rect.bottom+4;
  var left=rect.left;
  if(top+120>window.innerHeight)top=rect.top-120;
  if(left+220>window.innerWidth)left=window.innerWidth-225;
  pop.style.top=top+'px';
  pop.style.left=Math.max(4,left)+'px';
  document.body.appendChild(pop);
  _admRenPopEl=pop;
  var inp=document.getElementById('_admRenInp');
  if(inp){inp.focus();inp.select();}
  pop.addEventListener('click',function(e){e.stopPropagation();});
  pop.addEventListener('mousedown',function(e){e.stopPropagation();});
  pop.addEventListener('dragstart',function(e){e.stopPropagation();e.preventDefault();});
}
function closeAdminRenamePopup(){
  if(_admRenPopEl){_admRenPopEl.remove();_admRenPopEl=null;}
}
function deleteTagChip(btn){
  var tag=btn.dataset.tag;
  if(!tag)return;
  fetch('/admin/api/tags/delete_chip',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({tag_name:tag})})
  .then(function(r){return r.json();})
  .then(function(d){
    if(d.ok){
      showDragLog('標籤「'+tag+'」已刪除'+(d.removed_from?' (已從 '+d.removed_from+' 筆 QA 移除)':''));
      loadGroups();
    } else if(d.in_use_count){
      showDeleteConfirmModal(tag, d.in_use_count, d.qa_items||[]);
    } else {
      alert('刪除失敗：'+(d.error||'未知錯誤'));
    }
  })
  .catch(function(){alert('連線失敗，請稍後再試');});
}
function showDeleteConfirmModal(tag, count, items){
  var existing=document.getElementById('_delConfirmModal');
  if(existing)existing.remove();
  var rows=items.map(function(item){
    var q=(item.q_text||'').substring(0,120);
    var a=(item.a_text||'').substring(0,80);
    return '<div style="border:.5px solid #eee;border-radius:6px;padding:8px 10px;margin-bottom:6px;background:#fff;">'
      +'<div style="font-size:10px;color:#aaa;margin-bottom:3px;">ID: '+item.id+'</div>'
      +'<div style="font-size:11px;color:#333;line-height:1.5;margin-bottom:3px;"><b>Q：</b>'+escHtmlG(q)+(item.q_text&&item.q_text.length>120?'…':'')+'</div>'
      +'<div style="font-size:11px;color:#555;line-height:1.5;"><b>A：</b>'+escHtmlG(a)+(item.a_text&&item.a_text.length>80?'…':'')+'</div>'
      +'</div>';
  }).join('');
  var more=count>items.length?'<div style="font-size:11px;color:#aaa;text-align:center;margin-top:4px;">…共 '+count+' 筆，僅顯示前 '+items.length+' 筆</div>':'';
  var modal=document.createElement('div');
  modal.id='_delConfirmModal';
  modal.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9999;display:flex;align-items:center;justify-content:center;';
  modal.innerHTML='<div style="background:#fff;border-radius:10px;padding:20px;width:500px;max-width:90vw;max-height:80vh;display:flex;flex-direction:column;box-shadow:0 8px 32px rgba(0,0,0,.2);">'
    +'<div style="font-size:14px;font-weight:500;margin-bottom:6px;color:#c62828;">⚠ 確認刪除標籤「'+escHtmlG(tag)+'」</div>'
    +'<div style="font-size:12px;color:#666;margin-bottom:10px;">此標籤被 <b>'+count+'</b> 筆 QA 使用中，以下為相關 QA 原文：</div>'
    +'<div style="overflow-y:auto;flex:1;margin-bottom:14px;padding-right:2px;">'+rows+more+'</div>'
    +'<div style="display:flex;gap:8px;justify-content:flex-end;">'
    +'<button onclick="document.getElementById(\'_delConfirmModal\').remove()" style="padding:6px 16px;border-radius:6px;border:.5px solid #ddd;background:#fff;cursor:pointer;font-size:12px;">取消</button>'
    +'<button onclick="forceDeleteTag(\''+escAttrG(tag)+'\')" style="padding:6px 16px;border-radius:6px;border:none;background:#c62828;color:#fff;cursor:pointer;font-size:12px;font-weight:500;">強制刪除（從所有 QA 移除）</button>'
    +'</div>'
    +'</div>';
  document.body.appendChild(modal);
  modal.addEventListener('click',function(e){if(e.target===modal)modal.remove();});
}
function forceDeleteTag(tag){
  var modal=document.getElementById('_delConfirmModal');
  if(modal)modal.remove();
  fetch('/admin/api/tags/delete_chip',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({tag_name:tag,force:true})})
  .then(function(r){return r.json();})
  .then(function(d){
    if(d.ok){showDragLog('標籤「'+tag+'」已強制刪除，從 '+d.removed_from+' 筆 QA 移除');loadGroups();}
    else{alert('刪除失敗：'+(d.error||'未知'));}
  });
}
function confirmAdminRename(forceMerge){
  var inp=document.getElementById('_admRenInp');
  if(!inp)return;
  var oldName=inp.dataset.old||'';
  var newName=inp.value.trim();
  if(!newName){alert('新名稱不可空白');return;}
  if(newName===oldName){closeAdminRenamePopup();return;}
  fetch('/admin/api/tags/rename_global',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({old_name:oldName,new_name:newName,force_merge:!!forceMerge})})
  .then(function(r){return r.json();}).then(function(d){
    if(d.conflict){
      var pop=_admRenPopEl;
      if(pop){
        pop.style.minWidth='280px';
        pop.innerHTML='<div style="font-size:12px;font-weight:500;color:#854f0b;margin-bottom:8px">&#9888; 標籤已存在</div>'
          +'<div style="font-size:12px;color:#555;margin-bottom:6px;line-height:1.6">「<b>'+escHtmlG(newName)+'</b>」已存在於群組中。</div>'
          +'<div style="font-size:12px;color:#555;margin-bottom:12px;line-height:1.6">是否將「<b>'+escHtmlG(oldName)+'</b>」<br>合併至「<b>'+escHtmlG(newName)+'</b>」？</div>'
          +'<div style="display:flex;gap:6px">'
          +'<button onclick="confirmAdminRename(true)" style="font-size:12px;padding:5px 14px;border-radius:6px;background:#e65100;border:none;color:#fff;cursor:pointer">合併</button>'
          +'<button onclick="closeAdminRenamePopup()" style="font-size:12px;padding:5px 14px;border-radius:6px;border:1px solid #ddd;background:#fff;cursor:pointer">取消</button>'
          +'</div>';
        var fakeInp=document.createElement('input');
        fakeInp.id='_admRenInp';fakeInp.dataset.old=oldName;fakeInp.value=newName;
        fakeInp.style.display='none';pop.appendChild(fakeInp);
      }
      return;
    }
    if(d.ok){
      closeAdminRenamePopup();
      var msg=d.merged?'「'+oldName+'」已合併至「'+newName+'」（共 '+d.updated+' 筆）':'「'+oldName+'」已改名為「'+newName+'」（共 '+d.updated+' 筆）';
      showDragLog(msg);
      loadGroups();
    }else{alert('改名失敗：'+(d.error||'未知錯誤'));}
  }).catch(function(){alert('網路錯誤');});
}
document.addEventListener('click',function(e){if(_admRenPopEl&&!_admRenPopEl.contains(e.target))closeAdminRenamePopup();});

function cleanupGhostTags(){
  if(!confirm('將刪除 tag_groups 中所有未被任何 QA 使用的標籤，確定執行？'))return;
  var btn=document.getElementById('cleanupBtn');
  if(btn){btn.textContent='清理中...';btn.disabled=true;}
  fetch('/admin/api/groups/cleanup',{method:'POST'})
  .then(function(r){return r.json();}).then(function(d){
    if(btn){btn.textContent='🧹 清除幽靈標籤';btn.disabled=false;}
    if(d.ok){
      var gs=document.getElementById('ghostStats');
      if(gs){gs.innerHTML='清除前 <b>'+d.before+'</b> 筆 → 清除後 <b>'+d.after+'</b> 筆（刪除 '+d.deleted+' 筆）';}
      showDragLog('清理完成，共刪除 '+d.deleted+' 個幽靈標籤');
      loadGroups();
    }else{alert('清理失敗：'+(d.error||''));}
  }).catch(function(){if(btn){btn.textContent='🧹 清除幽靈標籤';btn.disabled=false;}alert('網路錯誤');});
}

function exportTagsCSV(btn){
  btn.disabled=true;btn.textContent='載入中...';
  fetch('/admin/api/tags/export_csv').then(r=>r.json()).then(function(d){
    btn.disabled=false;btn.textContent='📥 匯出標籤';
    if(d.error){alert('錯誤：'+d.error);return;}
    var rows=d.rows||[];
    var csv='\\uFEFF群組,標籤,QA數量\\n';
    rows.forEach(function(r){
      csv+='"'+(r.group||'').replace(/"/g,'""')+'","'+(r.tag||'').replace(/"/g,'""')+'",'+r.count+'\\n';
    });
    var blob=new Blob([csv],{type:'text/csv;charset=utf-8;'});
    var url=URL.createObjectURL(blob);
    var a=document.createElement('a');
    a.href=url;
    var today=new Date();var mm=String(today.getMonth()+1).padStart(2,'0');var dd=String(today.getDate()).padStart(2,'0');
    a.download='HyRead_標籤盤點_'+today.getFullYear()+mm+dd+'.csv';
    a.click();URL.revokeObjectURL(url);
  }).catch(function(){btn.disabled=false;btn.textContent='📥 匯出標籤';alert('匯出失敗');});
}
function createGroup(){
  var name=prompt('請輸入新群組名稱：','');
  if(name===null)return;name=name.trim();
  if(!name){alert('名稱不可空白');return;}
  fetch('/admin/api/groups',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:name})})
  .then(r=>r.json()).then(function(d){
    if(d.error){alert('建立失敗：'+d.error);return;}
    loadGroups();
  });
}
function renameGroup(name){
  var newName=prompt('將「'+name+'」改名為：',name);
  if(!newName||newName===name)return;
  fetch('/admin/api/groups/rename',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({old_name:name,new_name:newName.trim()})})
  .then(r=>r.json()).then(function(d){
    if(d.ok)loadGroups();else alert('失敗：'+d.error);
  });
}
function mergeGroup(source){
  var targets=allGroups.filter(function(g){return g.name!==source;}).map(function(g){return g.name;});
  var target=prompt('將「'+source+'」合併至哪個群組？\\n選項：'+targets.join('、'));
  if(!target)return;
  if(!allGroupsData[target]){alert('找不到群組「'+target+'」');return;}
  if(!confirm('確定將「'+source+'」所有標籤移至「'+target+'」？'))return;
  fetch('/admin/api/groups/merge',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({source:source,target:target})})
  .then(r=>r.json()).then(function(d){
    if(d.ok)loadGroups();else alert('失敗：'+d.error);
  });
}
function deleteGroup(name){
  if(!confirm('刪除群組「'+name+'」？\\n其下所有標籤將移至「未分群」'))return;
  fetch('/admin/api/groups/delete',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:name})})
  .then(r=>r.json()).then(function(d){
    if(d.ok)loadGroups();else alert('失敗：'+d.error);
  });
}
</script>

<!-- 標籤管理 -->
<!-- Token 用量 -->
<div class="panel" id="tab-token">
  <div id="tokenWarn"></div>
  <div class="stat-grid" id="tokenCards"></div>
  <div class="card">
    <div class="card-title">📅 近14天每日用量</div>
    <div id="tokenChart"><div style="color:#aaa;font-size:13px">載入中...</div></div>
  </div>
  <div class="card">
    <div class="card-title">📋 近期批次記錄</div>
    <div id="tokenRecent" style="overflow-x:auto"><div style="color:#aaa;font-size:13px">載入中...</div></div>
  </div>
</div>

<script>
function showTab(el,name){
  document.querySelectorAll('.tab').forEach(function(t){t.classList.remove('active')});
  document.querySelectorAll('.panel').forEach(function(p){p.classList.remove('active')});
  el.classList.add('active');
  document.getElementById('tab-'+name).classList.add('active');
  if(name==='filter')loadWords();
  if(name==='category')loadCategories();
  if(name==='stats'){loadStats();loadQaYearCount();}
  if(name==='token')loadTokens();
  if(name==='users')loadUsers();
  if(name==='groupmgr')loadGroups();
}

/* ── 過濾詞句 ── */
function loadWords(){
  fetch('/admin/api/filter_words').then(function(r){return r.json()}).then(function(data){
    var phrases=data.filter(function(d){return d.type==='phrase'});
    var senders=data.filter(function(d){return d.type==='sender'});
    var keywords=data.filter(function(d){return d.type==='keyword'});
    var sys=data.filter(function(d){return d.is_system});
    var user=data.filter(function(d){return !d.is_system});
    var html='';
    if(user.length){
      html+='<div class="sec-lbl">你新增的（可刪除）</div><div class="tags">';
      user.forEach(function(w){
        var cls=w.type==='sender'?'tag-sender':w.type==='keyword'?'tag-keyword':'tag-phrase';
        html+='<div class="tag '+cls+'">'+esc(w.word)+'<span class="tag-del" onclick="delWord('+w.id+')">×</span></div>';
      });
      html+='</div>';
    }
    if(sys.length){
      html+='<div class="sec-lbl">系統預設（不可刪除）</div><div class="tags">';
      sys.forEach(function(w){html+='<div class="tag tag-system">'+esc(w.word)+'</div>';});
      html+='</div>';
    }
    document.getElementById('filterList').innerHTML=html||'<div style="color:#aaa;font-size:13px">尚無過濾詞句</div>';
  });
}
function addWord(){
  var w=document.getElementById('newWord').value.trim();
  if(!w){showMsg('addMsg','請輸入詞句',true);return}
  fetch('/admin/api/filter_words',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({word:w,type:document.getElementById('newType').value,note:document.getElementById('newNote').value})})
  .then(function(r){return r.json()}).then(function(d){
    if(d.error){showMsg('addMsg',d.error,true)}else{
      document.getElementById('newWord').value='';
      document.getElementById('newNote').value='';
      showMsg('addMsg','新增成功！',false);
      loadWords();
    }
  });
}
function delWord(id){
  if(!confirm('確定刪除這個過濾詞句？'))return;
  fetch('/admin/api/filter_words/'+id,{method:'DELETE'}).then(function(r){return r.json()}).then(function(d){
    if(d.error)alert(d.error);else loadWords();
  });
}

/* ── 分類管理 ── */
var editId=null;
function loadCategories(){
  var yr=document.getElementById('catYrFilter').value;
  fetch('/admin/api/categories'+(yr?'?year='+yr:'')).then(function(r){return r.json()}).then(function(data){
    var html='';
    data.forEach(function(row){
      var aiCat=row.categories||'—';
      var userCat=row.user_category||'';
      var confirmed=row.category_confirmed;
      html+='<tr id="row-'+row.id+'">'
        +'<td>'+esc(row.title)+'</td>'
        +'<td>'+esc(row.analyzed_at)+'</td>'
        +'<td>'+row.total_msgs+'</td>'
        +'<td><span class="cat-pill">'+esc(aiCat)+'</span></td>'
        +'<td id="cat-'+row.id+'" data-cur="'+escAttr(userCat||aiCat)+'">'+(userCat?'<span class="cat-edit">'+esc(userCat)+'</span>':'<span style="color:#ccc">未設定</span>')+'</td>'
        +'<td><button class="btn-outline" onclick="startEdit('+row.id+')">修改</button></td>'
        +'</tr>';
    });
    document.getElementById('catTable').innerHTML=html||'<tr><td colspan="6" style="color:#aaa;text-align:center;padding:20px">尚無資料</td></tr>';
  });
}
function startEdit(id){
  var cell=document.getElementById('cat-'+id);
  var cur=cell.getAttribute('data-cur')||'';
  cell.innerHTML='<div class="edit-inline"><input type="text" id="ei-'+id+'" value="'+escAttr(cur)+'"><button class="btn-sm" onclick="saveEdit('+id+')">儲存</button><button class="btn-sm btn-cancel" onclick="loadCategories()">取消</button></div>';
  document.getElementById('ei-'+id).focus();
}
function saveEdit(id){
  var val=document.getElementById('ei-'+id).value.trim();
  fetch('/admin/api/categories/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({user_category:val,confirmed:true})})
  .then(function(){loadCategories()});
}

/* ── 補跑解析 ── */
function reparse(){
  var btn=event.target;
  btn.disabled=true;btn.textContent='解析中，請稍候...';
  document.getElementById('reparseMsg').textContent='';
  fetch('/admin/api/reparse',{method:'POST'}).then(function(r){return r.json()}).then(function(d){
    btn.disabled=false;btn.textContent='▶ 立即補跑解析';
    if(d.success){
      document.getElementById('reparseMsg').textContent='✅ '+d.message;
      loadStats();loadQaYearCount();
    } else {
      document.getElementById('reparseMsg').style.color='#e53935';
      document.getElementById('reparseMsg').textContent='失敗：'+d.error;
    }
  }).catch(function(){
    btn.disabled=false;btn.textContent='▶ 立即補跑解析';
    document.getElementById('reparseMsg').style.color='#e53935';
    document.getElementById('reparseMsg').textContent='連線失敗，請稍後再試';
  });
}

/* ── 分析總覽 ── */
function loadStats(){
  fetch('/admin/api/stats').then(function(r){return r.json()}).then(function(d){
    var totalBatches=0,totalMsgs=0;
    Object.values(d.year_stats).forEach(function(v){totalBatches+=v.batches;totalMsgs+=v.msgs});
    document.getElementById('statCards').innerHTML=
      '<div class="stat-card"><div class="stat-num">'+totalBatches+'</div><div class="stat-lbl">已整理批次</div></div>'
      +'<div class="stat-card"><div class="stat-num">'+totalMsgs+'</div><div class="stat-lbl">訊息總數</div></div>'
      +'<div class="stat-card"><div class="stat-num">'+Object.keys(d.year_stats).length+'</div><div class="stat-lbl">涵蓋年份</div></div>'
;

    /* 年度長條圖 */
    var maxM=Math.max.apply(null,Object.values(d.year_stats).map(function(v){return v.msgs}))||1;
    var yHtml='';
    Object.keys(d.year_stats).sort().forEach(function(yr){
      var v=d.year_stats[yr];
      yHtml+='<div class="bar-row"><div class="bar-name">'+yr+'</div><div class="bar-wrap"><div class="bar-fill" style="width:'+(v.msgs/maxM*100)+'%"></div></div><div class="bar-val">'+v.msgs+'</div></div>';
    });
    document.getElementById('yearChart').innerHTML=yHtml||'<div style="color:#aaa;font-size:13px">無資料</div>';

  });
}

function loadQaYearCount(){
  var area=document.getElementById('qaYearCountArea');
  var btn=document.getElementById('qaYearRefreshBtn');
  if(area)area.innerHTML='<span style="color:#aaa">載入中...</span>';
  if(btn)btn.disabled=true;
  fetch('/admin/api/qa_year_count').then(function(r){return r.json();}).then(function(d){
    if(btn)btn.disabled=false;
    if(!d.ok){if(area)area.textContent='載入失敗：'+(d.error||'');return;}
    var html='<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:8px">'
      +'<span style="font-size:11px;color:#555;">合計：</span>'
      +'<span style="font-weight:600;color:#1b5e20;font-size:13px;">'+d.total+' 筆</span></div>';
    html+='<table style="width:100%;border-collapse:collapse;font-size:12px;">'
      +'<thead><tr>'
      +'<th style="text-align:left;padding:4px 8px;border-bottom:1px solid #eee;color:#888;font-weight:500">年份</th>'
      +'<th style="text-align:right;padding:4px 8px;border-bottom:1px solid #eee;color:#888;font-weight:500">QA 筆數</th>'
      +'<th style="padding:4px 8px;border-bottom:1px solid #eee;"></th>'
      +'</tr></thead><tbody>';
    var maxC=Math.max.apply(null,d.rows.map(function(r){return r.count}))||1;
    d.rows.forEach(function(r){
      var pct=Math.round(r.count/maxC*100);
      html+='<tr>'
        +'<td style="padding:5px 8px;color:#333;">'+r.year+'</td>'
        +'<td style="text-align:right;padding:5px 8px;font-weight:500;color:#1b5e20;">'+r.count+'</td>'
        +'<td style="padding:5px 8px;width:160px">'
        +'<div style="background:#e8f5e9;border-radius:4px;height:8px;">'
        +'<div style="background:#43a047;border-radius:4px;height:8px;width:'+pct+'%"></div>'
        +'</div></td>'
        +'</tr>';
    });
    html+='</tbody></table>';
    if(area)area.innerHTML=html;
  }).catch(function(){
    if(btn)btn.disabled=false;
    if(area)area.textContent='連線失敗';
  });
}

/* ── 帳號管理 ── */
var _userCache={};
function loadUsers(){
  fetch('/admin/api/users').then(function(r){return r.json()}).then(function(rows){
    _userCache={};
    var html='';
    rows.forEach(function(u){
      _userCache[u.id]=u;
      var canQ=u.can_query!==false;
      var canA=u.can_admin!==false;
      var active=u.is_active!==false;
      var statusBadge=active?'<span style="color:#2e7d32;font-weight:500">啟用</span>':'<span style="color:#aaa">停用</span>';
      var qBadge=canQ?'<span style="color:#1565c0">✓</span>':'<span style="color:#ddd">✗</span>';
      var permChips='';
      if(canA){
        var pMap={filter:'過濾',category:'分類',stats:'總覽',token:'Token',users:'帳號',tags:'標籤',groups:'群組'};
        Object.keys(pMap).forEach(function(k){
          var on=u['perm_'+k]!==false;
          permChips+='<span style="font-size:10px;padding:1px 5px;border-radius:3px;margin:1px;display:inline-block;background:'+(on?'#e3f2fd':'#f5f5f5')+';color:'+(on?'#1565c0':'#bbb')+'">'+pMap[k]+'</span>';
        });
      } else { permChips='<span style="color:#bbb;font-size:11px">—</span>'; }
      html+='<tr>'
        +'<td style="color:#aaa">'+u.id+'</td>'
        +'<td style="font-weight:500">'+esc(u.username)+'</td>'
        +'<td>'+esc(u.display_name||'')+'</td>'
        +'<td style="text-align:center;font-size:15px">'+qBadge+'</td>'
        +'<td style="text-align:center;line-height:1.6">'+permChips+'</td>'
        +'<td>'+statusBadge+'</td>'
        +'<td><button style="background:none;border:none;cursor:pointer;font-size:15px;padding:2px 4px" title="編輯" onclick="openEditModal('+u.id+')">✏️</button>'
        +'<button style="background:none;border:none;cursor:pointer;font-size:15px;padding:2px 4px" title="刪除" onclick="delUser('+u.id+')">🗑</button></td></tr>';
    });
    document.getElementById('userTableBody').innerHTML=html||'<tr><td colspan="7" style="color:#aaa;text-align:center;padding:20px">無帳號</td></tr>';
  });
}
function openAddModal(){
  ['addUsr','addPwd','addDisplayName'].forEach(function(id){document.getElementById(id).value='';});
  document.getElementById('addCanQuery').checked=true;
  document.getElementById('addCanAdmin').checked=false;
  ['filter','category','stats','token','tags','groups'].forEach(function(k){document.getElementById('addPerm_'+k).checked=true;});
  document.getElementById('addPerm_users').checked=false;
  document.getElementById('addModalMsg').textContent='';
  document.getElementById('userAddModal').style.display='flex';
}
function closeAddModal(){document.getElementById('userAddModal').style.display='none';}
function submitAddUser(){
  var u=document.getElementById('addUsr').value.trim();
  var p=document.getElementById('addPwd').value;
  if(!u||p.length<6){document.getElementById('addModalMsg').textContent='帳號不可為空，密碼至少6個字元';return;}
  fetch('/admin/api/users',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({username:u,password:p,display_name:document.getElementById('addDisplayName').value.trim(),
      can_query:document.getElementById('addCanQuery').checked,
      can_admin:document.getElementById('addCanAdmin').checked,
      perm_filter:document.getElementById('addPerm_filter').checked,
      perm_category:document.getElementById('addPerm_category').checked,
      perm_stats:document.getElementById('addPerm_stats').checked,
      perm_token:document.getElementById('addPerm_token').checked,
      perm_users:document.getElementById('addPerm_users').checked,
      perm_tags:document.getElementById('addPerm_tags').checked,
      perm_groups:document.getElementById('addPerm_groups').checked})})
  .then(function(r){return r.json()}).then(function(d){
    if(d.error){document.getElementById('addModalMsg').textContent=d.error;}
    else{closeAddModal();loadUsers();}
  });
}
function openEditModal(id){
  var u=_userCache[id];
  if(!u)return;
  document.getElementById('editUserId').value=u.id;
  document.getElementById('editUsrName').value=u.username;
  document.getElementById('editPwd').value='';setTimeout(function(){document.getElementById('editPwd').value='';},100);
  document.getElementById('editDisplayName').value=u.display_name||'';
  document.getElementById('editCanQuery').checked=u.can_query!==false;
  document.getElementById('editCanAdmin').checked=u.can_admin!==false;
  document.getElementById('editIsActive').checked=u.is_active!==false;
  ['filter','category','stats','token','users','tags','groups'].forEach(function(k){
    var el=document.getElementById('editPerm_'+k);
    if(el) el.checked=(u['perm_'+k]!==false);
  });
  document.getElementById('editModalMsg').textContent='';
  document.getElementById('userEditModal').style.display='flex';
}
function showToast(msg){
  var t=document.getElementById('adminToast');t.textContent=msg;t.style.display='block';
  setTimeout(function(){t.style.display='none';},2500);
}
function closeEditModal(){document.getElementById('userEditModal').style.display='none';}
function submitEditUser(){
  var id=document.getElementById('editUserId').value;
  var pwd=document.getElementById('editPwd').value;
  var payload={display_name:document.getElementById('editDisplayName').value.trim(),
    can_query:document.getElementById('editCanQuery').checked,
    can_admin:document.getElementById('editCanAdmin').checked,
    perm_filter:document.getElementById('editPerm_filter').checked,
    perm_category:document.getElementById('editPerm_category').checked,
    perm_stats:document.getElementById('editPerm_stats').checked,
    perm_token:document.getElementById('editPerm_token').checked,
    perm_users:document.getElementById('editPerm_users').checked,
    perm_tags:document.getElementById('editPerm_tags').checked,
    perm_groups:document.getElementById('editPerm_groups').checked,
    is_active:document.getElementById('editIsActive').checked};
  if(pwd){if(pwd.length<6){document.getElementById('editModalMsg').textContent='密碼至少6個字元';return;}payload.password=pwd;}
  fetch('/admin/api/users/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
  .then(function(r){
    if(!r.ok){return r.text().then(function(t){throw new Error('HTTP '+r.status+': '+t.slice(0,200));});}
    return r.json();
  }).then(function(d){
    if(d.error){document.getElementById('editModalMsg').textContent='儲存失敗：'+d.error;}
    else{closeEditModal();loadUsers();showToast('已更新 '+(payload.display_name||'帳號')+'');}
  }).catch(function(e){document.getElementById('editModalMsg').textContent='連線錯誤：'+e.message;});
}
function delUser(id){
  if(!confirm('確定刪除此帳號？'))return;
  fetch('/admin/api/users/'+id,{method:'DELETE'}).then(function(r){return r.json()}).then(function(d){
    if(d.error)alert(d.error);else loadUsers();
  });
}
function openBatchModal(){
  document.getElementById('batchCsv').value='';
  document.getElementById('batchMsg').textContent='';
  document.getElementById('userBatchModal').style.display='flex';
}
function closeBatchModal(){document.getElementById('userBatchModal').style.display='none';}
function submitBatch(){
  var csv=document.getElementById('batchCsv').value.trim();
  if(!csv){document.getElementById('batchMsg').textContent='請輸入資料';return;}
  fetch('/admin/api/users/batch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csv:csv})})
  .then(function(r){return r.json()}).then(function(d){
    if(d.error){document.getElementById('batchMsg').style.color='#e53935';document.getElementById('batchMsg').textContent=d.error;}
    else{document.getElementById('batchMsg').style.color='#2e7d32';document.getElementById('batchMsg').textContent='成功新增 '+d.added+' 筆，跳過 '+d.skipped+' 筆';loadUsers();}
  });
}


/* ── Token 用量 ── */
function loadTokens(){
  fetch('/admin/api/token_stats').then(function(r){return r.json()}).then(function(d){
    var pct=d.today_pct;
    var barColor=pct>=80?'#e53935':pct>=60?'#f57f17':'#00b900';
    document.getElementById('tokenCards').innerHTML=
      '<div class="stat-card"><div class="stat-num" style="color:'+barColor+'">'+d.today_total.toLocaleString()+'</div><div class="stat-lbl">今日累積 tokens</div></div>'
      +'<div class="stat-card"><div class="stat-num">'+d.all_total.toLocaleString()+'</div><div class="stat-lbl">歷史總計 tokens</div></div>'
      +'<div class="stat-card"><div class="stat-num" style="color:'+barColor+'">'+pct+'%</div><div class="stat-lbl">今日使用率（上限 1M）</div></div>'
      +'<div class="stat-card"><div class="stat-num">'+((d.limit-d.today_total)).toLocaleString()+'</div><div class="stat-lbl">今日剩餘額度</div></div>';

    /* 每日長條圖 */
    var days=Object.keys(d.daily).sort().slice(-14);
    var maxT=Math.max.apply(null,days.map(function(k){return d.daily[k].total}))||1;
    var dHtml='';
    days.forEach(function(day){
      var v=d.daily[day];
      var pct2=Math.round(v.total/1000000*100);
      var c2=pct2>=80?'#e53935':pct2>=60?'#f57f17':'#00b900';
      dHtml+='<div class="bar-row"><div class="bar-name" style="width:80px;font-size:10px">'+day.slice(5)+'</div>'
        +'<div class="bar-wrap"><div class="bar-fill" style="width:'+(v.total/maxT*100)+'%;background:'+c2+'"></div></div>'
        +'<div class="bar-val" style="width:70px;font-size:10px">'+v.total.toLocaleString()+'</div></div>';
    });
    document.getElementById('tokenChart').innerHTML=dHtml||'<div style="color:#aaa;font-size:13px">無資料</div>';

    /* 近期記錄 */
    var rHtml='<table><thead><tr><th>時間</th><th>批次</th><th>輸入</th><th>輸出</th><th>總計</th></tr></thead><tbody>';
    (d.recent||[]).forEach(function(r){
      rHtml+='<tr><td>'+esc(r.analyzed_at||'')+'</td><td>'+esc(r.title||'')+'</td>'
        +'<td>'+((r.input_tokens||0)).toLocaleString()+'</td>'
        +'<td>'+((r.output_tokens||0)).toLocaleString()+'</td>'
        +'<td><b>'+((r.total_tokens||0)).toLocaleString()+'</b></td></tr>';
    });
    rHtml+='</tbody></table>';
    document.getElementById('tokenRecent').innerHTML=rHtml;

    /* 警告提示 */
    if(d.today_total>=d.warning_threshold){
      document.getElementById('tokenWarn').innerHTML='<div style="background:#ffebee;border:1px solid #ef9a9a;border-radius:8px;padding:12px 16px;color:#c62828;font-size:13px;margin-bottom:12px">⚠️ 今日 token 用量已超過 80% 上限（'+d.today_total.toLocaleString()+' / 1,000,000），系統將自動暫停分析。</div>';
    } else {
      document.getElementById('tokenWarn').innerHTML='';
    }
  });
}

/* ── 工具 ── */
function esc(t){return(t||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function escQ(t){return(t||'').replace(/\'/g,'\\\'').replace(/"/g,'&quot;')}
function escAttr(t){return(t||'').replace(/"/g,'&quot;')}
function showMsg(id,msg,isErr){var el=document.getElementById(id);el.className='msg'+(isErr?' err':'');el.textContent=msg;setTimeout(function(){el.textContent=''},3000)}

/* 預設載入 */
loadWords();
/* 依目前登入者的後台權限隱藏無存取權的分頁 */
(function(){
  fetch('/admin/api/me').then(function(r){return r.json();}).then(function(p){
    var uEl=document.getElementById('adminUsername');if(uEl)(uEl.textContent=p.display_name||p.username||'')
    var map={filter:'filter',category:'category',stats:'stats',token:'token',users:'users',groupmgr:'groups'};
    Object.keys(map).forEach(function(tabName){
      var permKey='perm_'+map[tabName];
      if(p[permKey]===false){
        var tabEl=document.querySelector('.tab[data-tab="'+tabName+'"]');
        var panelEl=document.getElementById('tab-'+tabName);
        if(tabEl) tabEl.style.display='none';
        if(panelEl) panelEl.style.display='none';
      }
    });
  }).catch(function(){});
})();
</script></body></html>'''

@app.route('/admin/api/tags/rename_global', methods=['POST'])
@require_admin
def admin_rename_tag_global():
    """全域改名：更新所有 qa_items.tags + tag_groups.tag_name"""
    d = request.get_json()
    old_name = (d.get('old_name') or '').strip()
    new_name = (d.get('new_name') or '').strip()
    force_merge = bool(d.get('force_merge'))
    if not old_name or not new_name:
        return jsonify({'ok': False, 'error': '名稱不可空白'}), 400
    if old_name == new_name:
        return jsonify({'ok': True, 'updated': 0})
    try:
        exists = supabase.table('tag_groups').select('tag_name').eq('tag_name', new_name).execute().data
        if exists and not force_merge:
            return jsonify({'ok': False, 'conflict': True, 'new_name': new_name})
        updated = 0
        offset = 0
        while True:
            rows = supabase.table('qa_items').select('id,tags').contains('tags', [old_name]).range(offset, offset + 199).execute().data or []
            for row in rows:
                new_tags = [new_name if t == old_name else t for t in (row['tags'] or [])]
                supabase.table('qa_items').update({'tags': new_tags}).eq('id', row['id']).execute()
                updated += 1
            if len(rows) < 200:
                break
            offset += 200
        if exists:
            supabase.table('tag_groups').delete().eq('tag_name', old_name).execute()
        else:
            supabase.table('tag_groups').update({'tag_name': new_name}).eq('tag_name', old_name).execute()
        return jsonify({'ok': True, 'updated': updated, 'merged': bool(exists)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# ──────────────────────────────────────────────
# 管理 API — 標籤定義
# ──────────────────────────────────────────────
@app.route("/admin/api/tag_definitions", methods=["GET"])
@require_admin
def admin_get_tag_defs():
    rows = supabase.table("tag_definitions").select("*").order("sort_order").execute().data or []
    return jsonify(rows)

@app.route("/admin/api/tag_definitions", methods=["POST"])
@require_admin
def admin_add_tag_def():
    data = request.get_json()
    name = (data.get("name") or "").strip()
    typ  = data.get("type", "次分類")
    if not name:
        return jsonify({"error": "標籤名稱不可為空"}), 400
    if typ not in ("主分類", "次分類"):
        typ = "次分類"
    try:
        # sort_order = 現有最大值 + 1
        existing = supabase.table("tag_definitions").select("sort_order").order("sort_order", desc=True).limit(1).execute().data
        next_order = (existing[0]["sort_order"] + 1) if existing else 1
        supabase.table("tag_definitions").insert({
            "name": name, "type": typ,
            "sort_order": next_order,
            "created_at": datetime.now().strftime("%Y/%m/%d %H:%M")
        }).execute()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin/api/tag_definitions/<int:tag_id>", methods=["PATCH"])
@require_admin
def admin_update_tag_def(tag_id):
    data = request.get_json()
    update = {}
    if "type" in data and data["type"] in ("主分類", "次分類"):
        update["type"] = data["type"]
    if "name" in data and data["name"].strip():
        update["name"] = data["name"].strip()
    if "sort_order" in data:
        update["sort_order"] = int(data["sort_order"])
    if not update:
        return jsonify({"error": "no fields"}), 400
    try:
        supabase.table("tag_definitions").update(update).eq("id", tag_id).execute()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin/api/tag_definitions/<int:tag_id>", methods=["DELETE"])
@require_admin
def admin_delete_tag_def(tag_id):
    try:
        supabase.table("tag_definitions").delete().eq("id", tag_id).execute()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ──────────────────────────────────────────────
# 管理 API — 帳號管理
# ──────────────────────────────────────────────

# ── 群組管理 API ────────────────────────────────────────────────────

@app.route('/admin/api/groups/cleanup', methods=['POST'])
@require_admin
def cleanup_ghost_tags():
    """刪除 tag_groups 中未被任何 qa_items 使用的幽靈 tag"""
    try:
        # 1. 蒐集所有 qa_items 實際使用的 tags
        used = set()
        offset = 0
        while True:
            rows = supabase.table('qa_items').select('tags').not_.is_('tags','null').range(offset, offset+999).execute().data or []
            for r in rows:
                for t in (r.get('tags') or []):
                    if t: used.add(t)
            if len(rows) < 1000: break
            offset += 1000
        # 2. 蒐集 tag_groups 所有非 __def__ 的 tag_name（分頁）
        all_tg = []
        tg_offset = 0
        while True:
            tg_rows = supabase.table('tag_groups').select('tag_name').range(tg_offset, tg_offset+999).execute().data or []
            if not tg_rows: break
            all_tg.extend(tg_rows)
            if len(tg_rows) < 1000: break
            tg_offset += 1000
        ghost = [r['tag_name'] for r in all_tg
                 if not r['tag_name'].startswith('__def__:') and r['tag_name'] not in used]
        # 3. 批次刪除
        deleted = 0
        for i in range(0, len(ghost), 50):
            batch = ghost[i:i+50]
            supabase.table('tag_groups').delete().in_('tag_name', batch).execute()
            deleted += len(batch)
        before = len(ghost) + (len(all_tg) - len(ghost))  # total non-def
        before_count = len([r for r in all_tg if not r['tag_name'].startswith('__def__:')])
        return jsonify({'ok': True, 'deleted': deleted, 'before': before_count, 'after': before_count - deleted})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/admin/api/groups', methods=['GET'])
@require_admin
def get_groups():
    """列出所有群組及其標籤數（排除 __def__: 定義列）"""
    try:
        rows = supabase.table('tag_groups').select('group_name,tag_name').execute().data or []
        group_counts = {}
        for r in rows:
            gn = r['group_name']
            if gn not in group_counts:
                group_counts[gn] = 0
            if not r['tag_name'].startswith('__def__:'):
                group_counts[gn] += 1
        result = [{'name': k, 'count': v} for k, v in sorted(group_counts.items())]
        total_tags = sum(v for v in group_counts.values())
        return jsonify({'groups': result, 'total_tags': total_tags})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/groups', methods=['POST'])
@require_admin
def create_group():
    """新增空群組（寫入 __def__:NAME 定義列）"""
    name = ((request.get_json() or {}).get('name') or '').strip()
    if not name:
        return jsonify({'ok': False, 'error': '群組名稱不可空白'}), 400
    try:
        supabase.table('tag_groups').upsert(
            {'tag_name': '__def__:' + name, 'group_name': name},
            on_conflict='tag_name'
        ).execute()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/groups/tags', methods=['GET'])
@require_admin
def get_group_tags():
    """列出某群組的所有標籤（?group=xxx），排除 __def__: 定義列"""
    group = request.args.get('group', '')
    try:
        rows = supabase.table('tag_groups').select('tag_name,group_name').eq('group_name', group).order('tag_name').execute().data or []
        filtered = [r for r in rows if not r['tag_name'].startswith('__def__:')]
        return jsonify({'tags': filtered})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/groups/all_tags', methods=['GET'])
@require_admin
def get_all_group_tags():
    """返回所有群組的標籤清單 {group_name: [tag_names]}"""
    try:
        result = {}
        offset = 0
        batch = 1000
        while True:
            rows = supabase.table('tag_groups').select('tag_name,group_name').range(offset, offset + batch - 1).execute().data or []
            for r in rows:
                gn = r['group_name']
                if gn not in result:
                    result[gn] = []
                if r['tag_name'].startswith('__def__:'):
                    continue
                result[gn].append(r['tag_name'])
            if len(rows) < batch:
                break
            offset += batch
        return jsonify({'groups': result, 'total': sum(len(v) for v in result.values())})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/groups/rename', methods=['POST'])
@require_admin
def rename_group():
    """改群組名稱（整批）"""
    d = request.get_json()
    old_name = (d.get('old_name') or '').strip()
    new_name = (d.get('new_name') or '').strip()
    if not old_name or not new_name:
        return jsonify({'ok': False, 'error': 'missing params'}), 400
    try:
        supabase.table('tag_groups').update({'group_name': new_name}).eq('group_name', old_name).execute()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/admin/api/groups/merge', methods=['POST'])
@require_admin
def merge_groups():
    """合併：把 source 群組的所有標籤移到 target 群組"""
    d = request.get_json()
    source = (d.get('source') or '').strip()
    target = (d.get('target') or '').strip()
    if not source or not target:
        return jsonify({'ok': False, 'error': 'missing params'}), 400
    try:
        supabase.table('tag_groups').update({'group_name': target}).eq('group_name', source).execute()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/admin/api/groups/delete', methods=['POST'])
@require_admin
def delete_group():
    """刪除群組：該群組標籤移至「未分群」"""
    d = request.get_json()
    name = (d.get('name') or '').strip()
    if not name or name == '未分群':
        return jsonify({'ok': False, 'error': 'invalid group'}), 400
    try:
        supabase.table('tag_groups').update({'group_name': '未分群'}).eq('group_name', name).execute()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/admin/api/groups/tag', methods=['POST'])
@require_admin
def update_tag_group():
    """修改單一標籤的群組"""
    d = request.get_json()
    tag_name  = (d.get('tag_name') or '').strip()
    group_name = (d.get('group_name') or '').strip()
    if not tag_name or not group_name:
        return jsonify({'ok': False, 'error': 'missing params'}), 400
    try:
        supabase.table('tag_groups').upsert(
            {'tag_name': tag_name, 'group_name': group_name},
            on_conflict='tag_name'
        ).execute()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/admin/api/tags/delete_chip', methods=['POST'])
@require_admin
def admin_delete_tag_chip():
    data = request.get_json()
    tag_name = (data or {}).get('tag_name', '').strip()
    force = bool((data or {}).get('force', False))
    if not tag_name:
        return jsonify({'error': '缺少 tag_name'}), 400
    try:
        res = supabase.table('qa_items').select('id').contains('tags', [tag_name]).execute()
        in_use_rows = res.data or []
        in_use = len(in_use_rows)
        if in_use > 0 and not force:
            ids = [r['id'] for r in in_use_rows[:10]]
            details = supabase.table('qa_items').select('id,q_text,a_text').in_('id', ids).execute().data or []
            return jsonify({'error': f'標籤被 {in_use} 筆 QA 使用', 'in_use_count': in_use, 'qa_items': details})
        if in_use > 0 and force:
            # 從每筆 qa_items 移除此標籤
            for row in in_use_rows:
                item = supabase.table('qa_items').select('id,tags').eq('id', row['id']).single().execute().data
                if item:
                    new_tags = [t for t in (item.get('tags') or []) if t != tag_name]
                    supabase.table('qa_items').update({'tags': new_tags}).eq('id', row['id']).execute()
        supabase.table('tag_groups').delete().eq('tag_name', tag_name).execute()
        return jsonify({'ok': True, 'removed_from': in_use})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/tags/export_csv', methods=['GET'])
@require_admin
def admin_export_tags_csv():
    # Export all tags with group and QA count
    try:
        tag_count = {}
        offset = 0
        while True:
            rows = supabase.table('qa_items').select('tags').not_.is_('tags','null').range(offset, offset+999).execute().data or []
            if not rows: break
            for r in rows:
                for t in (r.get('tags') or []):
                    if t:
                        tag_count[t] = tag_count.get(t, 0) + 1
            if len(rows) < 1000: break
            offset += 1000
        grp_map = {}
        g_offset = 0
        while True:
            grp_rows = supabase.table('tag_groups').select('tag_name,group_name').range(g_offset, g_offset+999).execute().data or []
            if not grp_rows: break
            for r in grp_rows:
                if not r['tag_name'].startswith('__def__:'):
                    grp_map[r['tag_name']] = r['group_name']
            if len(grp_rows) < 1000: break
            g_offset += 1000
        all_tags = set(tag_count.keys()) | set(grp_map.keys())
        rows_out = sorted(
            [{'tag': t, 'group': grp_map.get(t, '未分群'), 'count': tag_count.get(t, 0)} for t in all_tags],
            key=lambda x: (x['group'], -x['count'])
        )
        return jsonify({'rows': rows_out, 'total_tags': len(rows_out), 'total_qa': sum(r['count'] for r in rows_out)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/qa/api/tags_with_groups', methods=['GET'])
@require_qa
def qa_tags_with_groups():
    """回傳所有標籤及出現次數，附群組資訊"""
    try:
        # 抓所有 tags（分頁）
        tag_count = {}
        offset = 0
        while True:
            rows = supabase.table('qa_items').select('tags').not_.is_('tags','null').range(offset, offset+999).execute().data or []
            if not rows: break
            for r in rows:
                for t in (r.get('tags') or []):
                    if t:
                        tag_count[t] = tag_count.get(t, 0) + 1
            if len(rows) < 1000: break
            offset += 1000
        # 抓群組對應（分頁，避免 Supabase 1000 筆限制）
        grp_map = {}
        g_offset = 0
        while True:
            grp_rows = supabase.table('tag_groups').select('tag_name,group_name').range(g_offset, g_offset+999).execute().data or []
            if not grp_rows: break
            for r in grp_rows:
                if not r['tag_name'].startswith('__def__:'):
                    grp_map[r['tag_name']] = r['group_name']
            if len(grp_rows) < 1000: break
            g_offset += 1000
        result = [
            {'tag': t, 'count': c, 'group': grp_map.get(t, '未分群')}
            for t, c in sorted(tag_count.items(), key=lambda x: -x[1])
        ]
        return jsonify({'tags': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/admin/api/me", methods=["GET"])
@require_admin
def get_me():
    username = session.get("admin_username", "")
    result = supabase.table("admin_users").select("username,display_name,perm_filter,perm_category,perm_stats,perm_token,perm_users,perm_tags,perm_groups").eq("username", username).execute()
    if result.data:
        d = result.data[0]
        d["username"] = d.get("username") or username
        return jsonify(d)
    return jsonify({})

@app.route("/admin/api/users", methods=["GET"])
@require_admin
def get_users():
    result = supabase.table("admin_users").select("id,username,display_name,role,can_query,can_admin,created_at,is_active,perm_filter,perm_category,perm_stats,perm_token,perm_users,perm_tags,perm_groups").order("id").execute()
    return jsonify(result.data)

@app.route("/admin/api/users", methods=["POST"])
@require_admin
def add_user():
    data = request.get_json()
    username = (data.get("username") or "").strip()
    password = data.get("password", "")
    if not username or len(password) < 6:
        return jsonify({"error": "帳號不可為空，密碼至少6個字元"}), 400
    try:
        supabase.table("admin_users").insert({
            "username": username,
            "password_hash": generate_password_hash(password),
            "display_name": (data.get("display_name") or "").strip(),
            "can_query": data.get("can_query", True),
            "can_admin": data.get("can_admin", False),
            "perm_filter": data.get("perm_filter", True),
            "perm_category": data.get("perm_category", True),
            "perm_stats": data.get("perm_stats", True),
            "perm_token": data.get("perm_token", True),
            "perm_users": data.get("perm_users", True),
            "perm_tags": data.get("perm_tags", True),
            "perm_groups": data.get("perm_groups", True),
            "created_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
            "is_active": True
        }).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": "帳號已存在或發生錯誤：" + str(e)}), 400

@app.route("/admin/api/users/<int:user_id>", methods=["DELETE"])
@require_admin
def delete_user(user_id):
    # 不可刪除自己
    me = supabase.table("admin_users").select("username").eq("id", user_id).execute()
    if me.data and me.data[0]["username"] == session.get("admin_username"):
        return jsonify({"error": "不可刪除自己的帳號"}), 403
    supabase.table("admin_users").delete().eq("id", user_id).execute()
    return jsonify({"success": True})

@app.route("/admin/api/users/<int:user_id>", methods=["PUT"])
@require_admin
def edit_user(user_id):
    data = request.get_json()
    update = {
        "display_name": (data.get("display_name") or "").strip(),
        "can_query": bool(data.get("can_query", True)),
        "can_admin": bool(data.get("can_admin", False)),
        "perm_filter": bool(data.get("perm_filter", True)),
        "perm_category": bool(data.get("perm_category", True)),
        "perm_stats": bool(data.get("perm_stats", True)),
        "perm_token": bool(data.get("perm_token", True)),
        "perm_users": bool(data.get("perm_users", True)),
        "perm_tags": bool(data.get("perm_tags", True)),
        "perm_groups": bool(data.get("perm_groups", True)),
        "is_active": bool(data.get("is_active", True))
    }
    if data.get("password"):
        if len(data["password"]) < 6:
            return jsonify({"error": "密碼至少6個字元"}), 400
        update["password_hash"] = generate_password_hash(data["password"])
    try:
        result = supabase.table("admin_users").update(update).eq("id", user_id).execute()
        return jsonify({"success": True, "updated": update})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin/api/users/<int:user_id>", methods=["PATCH"])
@require_admin
def toggle_user(user_id):
    data = request.get_json()
    supabase.table("admin_users").update({"is_active": data.get("is_active", True)}).eq("id", user_id).execute()
    return jsonify({"success": True})

@app.route("/admin/api/users/<int:user_id>/password", methods=["POST"])
@require_admin
def change_password(user_id):
    data = request.get_json()
    password = data.get("password", "")
    if len(password) < 6:
        return jsonify({"error": "密碼至少6個字元"}), 400
    supabase.table("admin_users").update({
        "password_hash": generate_password_hash(password)
    }).eq("id", user_id).execute()
    return jsonify({"success": True})

@app.route("/admin/api/users/batch", methods=["POST"])
@require_admin
def batch_add_users():
    csv_text = (request.get_json() or {}).get("csv", "")
    added = 0
    skipped = 0
    errors = []
    for line in csv_text.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            skipped += 1
            continue
        username, password = parts[0], parts[1]
        display_name = parts[2] if len(parts) > 2 else ""
        if not username or len(password) < 6:
            skipped += 1
            continue
        try:
            supabase.table("admin_users").insert({
                "username": username,
                "password_hash": generate_password_hash(password),
                "display_name": display_name,
                "can_query": True,
                "can_admin": False,
                "perm_filter": True,
                "perm_category": True,
                "perm_stats": True,
                "perm_token": True,
                "perm_users": True,
                "perm_tags": True,
                "perm_groups": True,
                "created_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
                "is_active": True
            }).execute()
            added += 1
        except Exception:
            skipped += 1
    return jsonify({"added": added, "skipped": skipped})

# ──────────────────────────────────────────────
# 管理 API — 過濾詞句
# ──────────────────────────────────────────────
@app.route("/admin/api/filter_words", methods=["GET"])
@require_admin
def get_filter_words():
    result = supabase.table("filter_words").select("*").order("id").execute()
    return jsonify(result.data)

@app.route("/admin/api/filter_words", methods=["POST"])
@require_admin
def add_filter_word():
    data = request.get_json()
    word = (data.get("word") or "").strip()
    if not word:
        return jsonify({"error": "詞句不可為空"}), 400
    supabase.table("filter_words").insert({
        "word": word,
        "type": data.get("type", "phrase"),
        "is_system": False,
        "note": data.get("note", ""),
        "created_at": datetime.now().strftime("%Y/%m/%d %H:%M")
    }).execute()
    return jsonify({"success": True})

@app.route("/admin/api/filter_words/<int:word_id>", methods=["DELETE"])
@require_admin
def delete_filter_word(word_id):
    existing = supabase.table("filter_words").select("is_system").eq("id", word_id).execute()
    if existing.data and existing.data[0].get("is_system"):
        return jsonify({"error": "系統預設詞句不可刪除"}), 403
    supabase.table("filter_words").delete().eq("id", word_id).execute()
    return jsonify({"success": True})

# ──────────────────────────────────────────────
# 管理 API — 分類管理
# ──────────────────────────────────────────────
@app.route("/admin/api/categories", methods=["GET"])
@require_admin
def get_categories():
    year = request.args.get("year", "")
    query = supabase.table("qa_results").select(
        "id,year,batch_num,title,categories,user_category,category_confirmed,analyzed_at,total_msgs")
    if year:
        query = query.eq("year", year)
    result = query.order("id").execute()
    return jsonify(result.data)

@app.route("/admin/api/categories/<int:result_id>", methods=["PATCH"])
@require_admin
def update_category(result_id):
    data = request.get_json()
    supabase.table("qa_results").update({
        "user_category": data.get("user_category", ""),
        "category_confirmed": data.get("confirmed", True)
    }).eq("id", result_id).execute()
    return jsonify({"success": True})

# ──────────────────────────────────────────────
# 管理 API — 分析總覽
# ──────────────────────────────────────────────
@app.route("/admin/api/stats", methods=["GET"])
@require_admin
def get_stats():
    result = supabase.table("qa_results").select("year,categories,user_category,total_msgs").execute()
    year_stats, cat_stats = {}, {}
    for row in result.data:
        yr = row.get("year") or "未知"
        if yr not in year_stats:
            year_stats[yr] = {"batches": 0, "msgs": 0}
        year_stats[yr]["batches"] += 1
        year_stats[yr]["msgs"] += row.get("total_msgs") or 0
        cats_str = row.get("user_category") or row.get("categories") or ""
        for c in re.split(r"[、,，]", cats_str):
            c = c.strip()
            if c:
                cat_stats[c] = cat_stats.get(c, 0) + 1
    return jsonify({"year_stats": year_stats, "category_stats": cat_stats})

@app.route("/admin/api/qa_year_count", methods=["GET"])
@require_admin
def get_qa_year_count():
    """從 qa_items 統計各年份 QA 筆數（分頁）"""
    try:
        counts = {}
        offset = 0
        while True:
            rows = supabase.table("qa_items").select("year").range(offset, offset+999).execute().data or []
            if not rows: break
            for r in rows:
                yr = r.get("year") or "未知"
                counts[yr] = counts.get(yr, 0) + 1
            if len(rows) < 1000: break
            offset += 1000
        total = sum(counts.values())
        result = [
            {"year": yr, "count": counts[yr]}
            for yr in sorted(counts.keys())
        ]
        return jsonify({"ok": True, "rows": result, "total": total})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ──────────────────────────────────────────────
# 管理 API — Token 用量統計
# ──────────────────────────────────────────────
@app.route("/admin/api/reparse", methods=["POST"])
@require_admin
def reparse_qa_items():
    """將 qa_results 的舊資料重新解析存入 qa_items"""
    try:
        # 清除現有 qa_items（避免重複）
        supabase.table("qa_items").delete().neq("id", 0).execute()
        # 讀取所有 qa_results
        rows = supabase.table("qa_results").select("*").order("id").execute().data
        total_items = 0
        for row in rows:
            parse_and_save_qa_items(
                content=row.get("content") or "",
                year=row.get("year") or "",
                batch_num=row.get("batch_num") or 0,
                batch_id=row.get("id"),
                categories=row.get("categories") or ""
            )
            total_items += 1
        return jsonify({"success": True, "batches": len(rows), "message": "已重新解析 " + str(len(rows)) + " 個批次"})
    except Exception as e:
        print("reparse 失敗：", e, flush=True)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/admin/api/token_stats")
@require_admin
def get_token_stats():
    result = supabase.table("token_logs").select("*").order("id", desc=False).execute()
    rows = result.data
    today = datetime.now().strftime("%Y/%m/%d")

    today_total = sum((r.get("total_tokens") or 0) for r in rows
                      if (r.get("analyzed_at") or "").startswith(today))
    all_total   = sum((r.get("total_tokens") or 0) for r in rows)

    # 每日彙整
    daily = {}
    for r in rows:
        day = (r.get("analyzed_at") or "")[:10]
        if not day:
            continue
        if day not in daily:
            daily[day] = {"input": 0, "output": 0, "total": 0, "batches": 0}
        daily[day]["input"]   += r.get("input_tokens",  0) or 0
        daily[day]["output"]  += r.get("output_tokens", 0) or 0
        daily[day]["total"]   += r.get("total_tokens",  0) or 0
        daily[day]["batches"] += 1

    return jsonify({
        "today_total":        today_total,
        "all_total":          all_total,
        "today_pct":          round(today_total / 1000000 * 100, 1),
        "warning_threshold":  800000,
        "limit":              1000000,
        "daily":              daily,
        "recent":             list(reversed(rows))[:30]
    })

# ──────────────────────────────────────────────
# 基本工具函式
# ──────────────────────────────────────────────
def get_sender_name(event):
    try:
        profile = line_bot_api.get_group_member_profile(event.source.group_id, event.source.user_id)
        return profile.display_name
    except:
        return "未知用戶"

def get_setting(key):
    result = supabase.table("settings").select("value").eq("key", key).execute()
    return result.data[0]["value"] if result.data else None

def set_setting(key, value):
    existing = supabase.table("settings").select("value").eq("key", key).execute()
    if existing.data:
        supabase.table("settings").update({"value": value}).eq("key", key).execute()
    else:
        supabase.table("settings").insert({"key": key, "value": value}).execute()

def save_message(text, sender, file_url="", file_type="none"):
    supabase.table("messages").insert({
        "text": text, "sender": sender, "type": "message",
        "file_url": file_url, "file_type": file_type,
        "created_at": datetime.now().strftime("%Y/%m/%d %H:%M")
    }).execute()

def save_token_log(title, token_info):
    try:
        supabase.table("token_logs").insert({
            "analyzed_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
            "title": title,
            "input_tokens": token_info.get("input", 0),
            "output_tokens": token_info.get("output", 0),
            "total_tokens": token_info.get("total", 0)
        }).execute()
    except Exception as e:
        print("Token log 失敗：", e, flush=True)

def get_today_tokens():
    """查詢今日累積 token 使用量"""
    try:
        today = datetime.now().strftime("%Y/%m/%d")
        result = supabase.table("token_logs").select("total_tokens")\
            .like("analyzed_at", today + "%").execute()
        return sum((r.get("total_tokens") or 0) for r in result.data)
    except:
        return 0

def parse_and_save_qa_items(content, year, batch_num, batch_id, categories):
    """將 Gemini Q&A 輸出解析成獨立記錄存入 qa_items"""
    try:
        items = []
        lines = (content or "").split("\n")
        current_q, current_a = None, []

        for line in lines:
            s = line.strip()
            if not s:
                continue
            if "【一般訊息】" in s or "【分類標籤】" in s:
                if current_q and current_a:
                    items.append({"batch_id": batch_id, "year": year,
                        "batch_num": batch_num, "q_text": current_q,
                        "a_text": " ".join(current_a), "category": categories,
                        "created_at": datetime.now().strftime("%Y/%m/%d %H:%M")})
                break
            if s == "---":
                if current_q and current_a:
                    items.append({"batch_id": batch_id, "year": year,
                        "batch_num": batch_num, "q_text": current_q,
                        "a_text": " ".join(current_a), "category": categories,
                        "created_at": datetime.now().strftime("%Y/%m/%d %H:%M")})
                    current_q, current_a = None, []
                continue
            if re.match(r"^Q\d+[：:]", s):
                if current_q and current_a:
                    items.append({"batch_id": batch_id, "year": year,
                        "batch_num": batch_num, "q_text": current_q,
                        "a_text": " ".join(current_a), "category": categories,
                        "created_at": datetime.now().strftime("%Y/%m/%d %H:%M")})
                current_q = s
                current_a = []
            elif re.match(r"^A[：:]", s) and current_q:
                current_a.append(s)
            elif current_a and s:
                current_a.append(s)

        if current_q and current_a:
            items.append({"batch_id": batch_id, "year": year,
                "batch_num": batch_num, "q_text": current_q,
                "a_text": " ".join(current_a), "category": categories,
                "created_at": datetime.now().strftime("%Y/%m/%d %H:%M")})

        if items:
            supabase.table("qa_items").insert(items).execute()
            print("qa_items 儲存：", len(items), "筆", flush=True)
    except Exception as e:
        print("qa_items 儲存失敗：", e, flush=True)

def save_qa_result(year, batch_num, title, content, start_row, end_row, total_msgs, categories=""):
    try:
        supabase.table("qa_results").insert({
            "year": year, "batch_num": batch_num, "title": title,
            "content": content, "analyzed_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
            "start_row": start_row, "end_row": end_row,
            "total_msgs": total_msgs, "categories": categories
        }).execute()
        print("QA 儲存成功", flush=True)
    except Exception as e:
        print("QA 儲存失敗：", e, flush=True)

def upload_file(content, filename, content_type):
    try:
        supabase.storage.from_("line-files").upload(filename, content, {"content-type": content_type})
        return supabase.storage.from_("line-files").get_public_url(filename)
    except:
        return ""

# ──────────────────────────────────────────────
# 訊息過濾
# ──────────────────────────────────────────────
EMOJI_RE = re.compile(
    "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251"
    "\U0001F926-\U0001F937\U00010000-\U0010FFFF♀-♂☀-⭕‍⏏⏩⌚️〰]+", re.UNICODE)

HARD_PHRASES = {
    "好","好的","好喔","好!","好！","ok","OK","Ok","OK!","OK！",
    "嗯","嗯嗯","喔","喔喔","謝","謝謝","感謝","謝謝你","謝謝您",
    "收到","了解","知道了","知道","沒問題","哈","哈哈","哈哈哈","👍","🙏",
    "是","是的","對","對的","1","2","3",
}
HARD_SYSTEM = ["加入了聊天","已加入群組","已離開群組","撤回了一則訊息",
               "joined the group","left the group","已將您移除"]
HARD_BOT_SENDERS = {"HyRead客服","HyRead Bot","bot"}
HARD_BOT_PREFIXES = ("⏳ ","✅ ","🎉 ","📊 ","⚠️ ","整理失敗","目前沒有")

def get_db_filters():
    """從 Supabase 讀取使用者自訂過濾詞"""
    try:
        rows = supabase.table("filter_words").select("word,type,is_system").execute().data
        phrases, senders, keywords = set(), set(), []
        for r in rows:
            t = r.get("type", "phrase")
            w = (r.get("word") or "").strip()
            if not w:
                continue
            if t == "phrase":
                phrases.add(w)
            elif t == "sender":
                senders.add(w)
            else:
                keywords.append(w)
        return phrases, senders, keywords
    except Exception:
        return set(), set(), []


def should_skip(msg, db_phrases, db_senders, db_keywords):
    text   = (msg.get("text") or "").strip()
    sender = (msg.get("sender") or "").strip()
    mtype  = msg.get("type", "text")
    if mtype in ("system",): return True
    if sender in HARD_BOT_SENDERS: return True
    if db_senders and sender in db_senders: return True
    if any(text.startswith(p) for p in HARD_BOT_PREFIXES): return True
    if text.startswith("QA"): return True
    if any(kw in text for kw in HARD_SYSTEM): return True
    if db_keywords and any(kw in text for kw in db_keywords): return True
    if not EMOJI_RE.sub("", text).strip(): return True
    if text in HARD_PHRASES: return True
    if db_phrases and text in db_phrases: return True
    if text in ("[圖片]", "[貼圖]", "[Sticker]") and not msg.get("file_url"): return True
    return False


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
