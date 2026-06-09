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
        if result.data and check_password_hash(result.data[0]["password_hash"], password):
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
    <input type="password" name="password" placeholder="請輸入密碼">
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
        if result.data and check_password_hash(result.data[0]["password_hash"], password):
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
    <input type="password" name="password" placeholder="請輸入密碼">
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
    return '''<!DOCTYPE html>
<html lang="zh-TW"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HyRead Q&A 查詢</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Microsoft JhengHei",sans-serif;height:100vh;display:flex;flex-direction:column;background:#f5f7fa}
.topbar{background:#00b900;color:#fff;padding:11px 18px;display:flex;align-items:center;gap:8px;font-size:14px;font-weight:500;flex-shrink:0}
.topbar a{color:rgba(255,255,255,.85);font-size:11px;padding:4px 10px;border-radius:6px;border:.5px solid rgba(255,255,255,.3);text-decoration:none;margin-left:auto}
.wrap{display:flex;flex:1;overflow:hidden}
aside{width:155px;background:#fff;border-right:.5px solid #e0e0e0;padding:10px 8px;display:flex;flex-direction:column;gap:3px;flex-shrink:0;overflow-y:auto}
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
.empty{display:flex;flex-direction:column;align-items:center;justify-content:center;flex:1;color:#bbb;font-size:13px;gap:8px;text-align:center;padding:20px}
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
.tag-add{display:inline-flex;align-items:center;gap:3px;font-size:10px;padding:2px 8px;border-radius:99px;border:1px dashed #aaa;color:#aaa;cursor:pointer;background:transparent;transition:border-color .15s,color .15s,transform .15s}
.tag-add:hover{border-color:#00b900;color:#00b900;transform:scale(1.05)}
/* ── 編輯模式 topbar 指示 ── */
.edit-badge{font-size:10px;background:rgba(255,255,0,.25);color:#fff;padding:2px 8px;border-radius:99px;border:.5px solid rgba(255,255,255,.4)}
/* ── Tag Popover ── */
#tagPopover{position:fixed;background:#fff;border:.5px solid #ddd;border-radius:10px;box-shadow:0 4px 18px rgba(0,0,0,.13);padding:12px;z-index:999;display:none;width:360px;max-width:90vw}
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
  <button id="editToggle" onclick="toggleEditMode()"
    style="margin-left:auto;background:rgba(255,255,255,.15);border:.5px solid rgba(255,255,255,.4);color:#fff;padding:4px 12px;border-radius:6px;font-size:11px;cursor:pointer">
    ✏️ 編輯標籤
  </button>
  <a href="/admin" style="margin-left:6px">⚙ 管理介面</a>
  <a href="/qa/logout" style="margin-left:6px">登出</a>
</div>
<!-- Tag Popover -->
<div id="tagPopover">
  <div class="pop-title">選擇標籤</div>
  <div class="pop-tags" id="popTagList"></div>
</div>
<div class="wrap">
  <aside>
    <div class="sb-lbl">歷史資料瀏覽</div>
    <div class="yr-link" onclick="browseYear(this,'2019')">2019 年</div>
    <div class="yr-link" onclick="browseYear(this,'2020')">2020 年</div>
    <div class="yr-link" onclick="browseYear(this,'2021')">2021 年</div>
    <div class="yr-link" onclick="browseYear(this,'2022')">2022 年</div>
    <div class="yr-link" onclick="browseYear(this,'2023')">2023 年</div>
    <div class="yr-link" onclick="browseYear(this,'2024')">2024 年</div>
    <div class="yr-link" onclick="browseYear(this,'2025')">2025 年</div>
    <div class="yr-link" onclick="browseYear(this,'2026')">2026 年</div>
    <div class="yr-link" onclick="browseYear(this,'日常')">日常新增</div>
    <div class="divider"></div>
    <div class="sb-lbl">標籤篩選</div>
    <input id="tagSearch" type="text" placeholder="搜尋標籤..."
      style="width:100%;padding:5px 8px;border:.5px solid #ddd;border-radius:6px;font-size:11px;margin-bottom:6px;font-family:inherit;outline:none"
      oninput="filterTagChips(this.value)">
    <div id="tagFilterList" style="line-height:1.9"></div>
    <button id="tagShowMore" onclick="showAllTags()" style="font-size:10px;color:#00b900;padding:2px 0;border:none;background:transparent;cursor:pointer;width:100%;margin-top:2px;display:none">＋ 顯示全部標籤</button>
    <button id="tagClearBtn" class="tag-clear-btn" onclick="clearTagFilter()">清除篩選</button>
  </aside>
  <main>
    <div class="search-bar">
      <div class="search-row">
        <input class="kw-input" id="kw" placeholder="輸入關鍵字，例如：召回、APP無法登入、保固..."
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
    </div>
    <div class="results" id="results">
      <div class="empty" id="homeState">
        <div style="font-size:15px;font-weight:600;color:#333;margin-bottom:4px">HyRead 客服歷史問答查詢</div>
        <div style="font-size:12px;color:#aaa;margin-bottom:16px">點選標籤快速篩選，或直接輸入關鍵字搜尋</div>
        <div style="width:100%;max-width:700px;margin-bottom:14px">
          <div style="font-size:10px;color:#bbb;letter-spacing:.5px;margin-bottom:10px">點選標籤篩選</div>
          <div id="homeTagChips" class="chips" style="justify-content:flex-start"></div>
        </div>
      </div>
    </div>
  </main>
</div>
<script>
var selectedTags=[],browseMode=false,browseYr='',currentPage=1,editMode=false;
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
  fetch('/qa/api/tags_summary').then(function(r){return r.json()}).then(function(tags){
    allTagsData=tags;
    renderTagChips(tags,TAGS_DEFAULT_SHOW);
    /* 首頁顯示全部標籤 */
    var homeEl=document.getElementById('homeTagChips');
    if(homeEl){
      var homeHtml='';
      tags.forEach(function(t){
        var active=selectedTags.indexOf(t.tag)>=0?' active':'';
        homeHtml+='<span class="tag-filter-chip'+active+'" data-tag="'+esc(t.tag)+'" onclick="pickHomeTag(''+esc(t.tag)+'')">'  +esc(t.tag)+'</span>';
      });
      homeEl.innerHTML=homeHtml;
    }
  }).catch(function(){});
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

function filterTagChips(kw){
  var filtered=kw?allTagsData.filter(function(t){return t.tag.indexOf(kw)>=0}):allTagsData;
  renderTagChips(filtered,(tagsExpanded||kw)?null:TAGS_DEFAULT_SHOW);
}

function showAllTags(){
  tagsExpanded=true;
  renderTagChips(allTagsData,null);
}

function pickHomeTag(tag){
  exitBrowse();
  if(selectedTags.indexOf(tag)<0){
    selectedTags.push(tag);
    var chip=document.querySelector('.tag-filter-chip[data-tag="'+tag+'"]');
    if(chip)chip.classList.add('active');
    document.getElementById('tagClearBtn').classList.add('visible');
  }
  _doSearch();
}

loadTagsSummary();

function toggleTagFilter(el){
  var tag=el.dataset.tag;
  var idx=selectedTags.indexOf(tag);
  if(idx>=0){selectedTags.splice(idx,1);el.classList.remove('active');}
  else{selectedTags.push(tag);el.classList.add('active');}
  var clearBtn=document.getElementById('tagClearBtn');
  if(selectedTags.length>0)clearBtn.classList.add('visible');
  else clearBtn.classList.remove('visible');
  exitBrowse();
  _doSearch();
}

function clearTagFilter(){
  selectedTags=[];
  document.querySelectorAll('.tag-filter-chip.active').forEach(function(e){e.classList.remove('active')});
  document.getElementById('tagClearBtn').classList.remove('visible');
  _doSearch();
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
function openPopover(itemId, btnEl){
  popTargetId=itemId;
  var pop=document.getElementById('tagPopover');
  var existing=cardTags[itemId]||[];
  /* 只顯示尚未加入的標籤 */
  var available=PRESET_TAGS.filter(function(t){return existing.indexOf(t)<0});
  if(!available.length){
    pop.style.display='none';
    return;
  }
  document.getElementById('popTagList').innerHTML=available.map(function(t){
    return '<div class="pop-tag" data-id="'+itemId+'" data-tag="'+esc(t)+'" onclick="handlePopTag(this)">'+esc(t)+'</div>';
  }).join('');
  var rect=btnEl.getBoundingClientRect();
  pop.style.display='block';
  pop.style.top=(rect.bottom+6)+'px';
  var popW=360;
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
  document.getElementById('results').innerHTML=\'<div class="empty" id="homeState"><div style="font-size:14px;font-weight:500;color:#555;margin-bottom:8px">輸入關鍵字或點選左側標籤開始搜尋</div><div class="chips"><div class="chip" onclick="fill(this.textContent)">召回</div><div class="chip" onclick="fill(this.textContent)">保固</div><div class="chip" onclick="fill(this.textContent)">APP無法登入</div><div class="chip" onclick="fill(this.textContent)">退款</div><div class="chip" onclick="fill(this.textContent)">帳號</div><div class="chip" onclick="fill(this.textContent)">維修</div></div></div>\';
}
function esc(t){return(t||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
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
      html+='<span class="tag tag-cat tag-edit">'
        +esc(t)
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
    var qBody=(r.q_text||'').replace(/^Q\d+[：:]\s*/,'');
    html+='<div class="card" data-id="'+itemId+'">'
      +'<div class="q-row"><div class="q-icon">Q'+(idx+1)+'</div>'
      +'<div class="q-txt">'+hilite(muteMetaInfo(qBody),kw)+'</div></div>'
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
</script></body></html>'''

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
        # 先用 count=exact 取得總筆數（不受 1000 筆限制）
        count_q = supabase.table("qa_items").select("id", count="exact")
        if keyword:
            or_filter = "q_text.ilike.%" + keyword + "%,a_text.ilike.%" + keyword + "%"
            count_q = count_q.or_(or_filter)
        if years:
            count_q = count_q.in_("year", years)
        if tags:
            for tag in tags:
                count_q = count_q.contains("tags", [tag])
        count_res = count_q.execute()
        total = count_res.count or 0
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        # 再取當頁資料
        data_q = supabase.table("qa_items").select("*")
        if keyword:
            or_filter = "q_text.ilike.%" + keyword + "%,a_text.ilike.%" + keyword + "%"
            data_q = data_q.or_(or_filter)
        if years:
            data_q = data_q.in_("year", years)
        if tags:
            for tag in tags:
                data_q = data_q.contains("tags", [tag])
        rows = data_q.order("id").range(start, start + page_size - 1).execute().data
        return jsonify({"results": rows, "total": total,
                        "page": page, "total_pages": total_pages, "page_size": page_size})
    except Exception as e:
        print("搜尋失敗：", e, flush=True)
        return jsonify({"results": [], "total": 0, "error": str(e)})

@app.route("/qa/api/update_tags", methods=["POST"])
@require_qa
def qa_update_tags():
    """更新單筆 qa_items 的 tags 陣列"""
    data = request.get_json()
    item_id = data.get("id")
    tags    = data.get("tags", [])
    if not item_id:
        return jsonify({"ok": False, "error": "missing id"}), 400
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).strip() for t in tags if str(t).strip()]
    try:
        supabase.table("qa_items").update({"tags": tags}).eq("id", item_id).execute()
        return jsonify({"ok": True, "tags": tags})
    except Exception as e:
        print("update_tags 失敗：", e, flush=True)
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
<div class="topbar">⚙ HyRead Q&A 管理介面
  <a href="/qa">← 回查詢頁面</a>
  <a href="/admin/logout" style="margin-left:6px">登出</a>
</div>
<div class="tabs">
  <div class="tab active" onclick="showTab(this,'filter')">🚫 過濾詞句</div>
  <div class="tab" onclick="showTab(this,'category')">🏷 分類管理</div>
  <div class="tab" onclick="showTab(this,'stats')">📊 分析總覽</div>
  <div class="tab" onclick="showTab(this,'token')">⚡ Token 用量</div>
  <div class="tab" onclick="showTab(this,'users')">👤 帳號管理</div>
  <div class="tab" onclick="showTab(this,'tagmgr')">🏷️ 標籤管理</div>
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
  <div class="stat-grid" id="statCards"></div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
    <div class="card">
      <div class="card-title">📅 各年度資料量</div>
      <div id="yearChart"></div>
    </div>
    <div class="card">
      <div class="card-title">🏷 問題分類分布</div>
      <div id="catChart"></div>
    </div>
  </div>
</div>

<!-- 帳號管理 -->
<div class="panel" id="tab-users">
  <div class="card" style="margin-bottom:10px;background:#f0fff0;border-color:#a5d6a7">
    <div style="font-size:12px;color:#2e7d32">ℹ️ 以下帳號同時適用於 <b>管理介面</b> 和 <b>查詢介面（/qa）</b> 的登入。如需新增只能查詢、不能進管理介面的帳號，請聯絡工程師另行設定。</div>
  </div>
  <div class="card">
    <div class="card-title">➕ 新增帳號</div>
    <div class="add-row">
      <input type="text" id="newUsr" placeholder="帳號" style="width:150px">
      <input type="password" id="newPwd" placeholder="密碼（至少6個字元）" style="width:200px">
      <button class="btn-green" onclick="addUser()">新增</button>
    </div>
    <div id="userMsg"></div>
  </div>
  <div class="card">
    <div class="card-title">👥 帳號清單</div>
    <table>
      <thead><tr><th>帳號</th><th>建立時間</th><th>狀態</th><th>操作</th></tr></thead>
      <tbody id="userTable"><tr><td colspan="4" style="color:#aaa;text-align:center;padding:20px">載入中...</td></tr></tbody>
    </table>
  </div>
  <div class="card">
    <div class="card-title">🔑 修改密碼</div>
    <div class="add-row">
      <select id="chgUsr" style="width:140px"></select>
      <input type="password" id="chgPwd" placeholder="新密碼（至少6個字元）" style="width:200px">
      <button class="btn-green" onclick="changePassword()">修改密碼</button>
    </div>
    <div id="pwdMsg"></div>
  </div>
</div>

<!-- 標籤管理 -->
<div class="panel" id="tab-tagmgr">
  <div class="card">
    <div class="card-title">&#128260; 從 Q&amp;A 資料同步標籤</div>
    <div style="font-size:12px;color:#888;margin-bottom:10px">將 Q&amp;A 資料中所有標籤匯入管理清單，已存在的不重複新增。</div>
    <button class="btn-green" onclick="syncTagNames()" id="syncTagBtn">立即同步</button>
    <span id="syncTagMsg" class="msg" style="margin-left:10px"></span>
  </div>
  <div class="card">
    <div class="card-title">&#127991;&#65039; 標籤清單
      <span style="font-size:11px;color:#aaa;font-weight:400;margin-left:8px" id="tagNameCount"></span>
    </div>
    <table>
      <thead><tr><th>標籤名稱</th><th style="width:60px;text-align:center">筆數</th><th style="width:120px">操作</th></tr></thead>
      <tbody id="tagNamesTable"><tr><td colspan="3" style="color:#aaa;text-align:center;padding:20px">載入中...</td></tr></tbody>
    </table>
  </div>
</div>

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
  if(name==='stats')loadStats();
  if(name==='token')loadTokens();
  if(name==='users')loadUsers();
  if(name==='tagmgr')loadTagDefs();
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
      loadStats();
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
      +'<div class="stat-card"><div class="stat-num">'+Object.keys(d.category_stats).length+'</div><div class="stat-lbl">問題類別數</div></div>';

    /* 年度長條圖 */
    var maxM=Math.max.apply(null,Object.values(d.year_stats).map(function(v){return v.msgs}))||1;
    var yHtml='';
    Object.keys(d.year_stats).sort().forEach(function(yr){
      var v=d.year_stats[yr];
      yHtml+='<div class="bar-row"><div class="bar-name">'+yr+'</div><div class="bar-wrap"><div class="bar-fill" style="width:'+(v.msgs/maxM*100)+'%"></div></div><div class="bar-val">'+v.msgs+'</div></div>';
    });
    document.getElementById('yearChart').innerHTML=yHtml||'<div style="color:#aaa;font-size:13px">無資料</div>';

    /* 分類長條圖 */
    var cats=Object.entries(d.category_stats).sort(function(a,b){return b[1]-a[1]}).slice(0,10);
    var maxC=(cats[0]||[0,1])[1]||1;
    var cHtml='';
    cats.forEach(function(c){
      cHtml+='<div class="bar-row"><div class="bar-name">'+esc(c[0])+'</div><div class="bar-wrap"><div class="bar-fill" style="width:'+(c[1]/maxC*100)+'%;background:#1565c0"></div></div><div class="bar-val">'+c[1]+'</div></div>';
    });
    document.getElementById('catChart').innerHTML=cHtml||'<div style="color:#aaa;font-size:13px">無分類資料</div>';
  });
}

/* ── 帳號管理 ── */
function loadUsers(){
  fetch('/admin/api/users').then(function(r){return r.json()}).then(function(data){
    var html='';
    var selHtml='';
    data.forEach(function(u){
      html+='<tr><td>'+esc(u.username)+'</td><td>'+esc(u.created_at||'')+'</td>'
        +'<td>'+(u.is_active?'<span style="color:#2e7d32">啟用</span>':'<span style="color:#aaa">停用</span>')+'</td>'
        +'<td><button class="btn-outline" onclick="toggleUser('+u.id+','+(!u.is_active)+')">'+(u.is_active?'停用':'啟用')+'</button>'
        +' <button class="btn-outline" style="color:#e53935;border-color:#e53935" onclick="delUser('+u.id+')">刪除</button></td></tr>';
      selHtml+='<option value="'+u.id+'">'+esc(u.username)+'</option>';
    });
    document.getElementById('userTable').innerHTML=html||'<tr><td colspan="4" style="color:#aaa;text-align:center;padding:20px">無帳號</td></tr>';
    document.getElementById('chgUsr').innerHTML=selHtml;
  });
}
function addUser(){
  var u=document.getElementById('newUsr').value.trim();
  var p=document.getElementById('newPwd').value;
  if(!u||p.length<6){showMsg('userMsg','帳號不可為空，密碼至少6個字元',true);return}
  fetch('/admin/api/users',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({username:u,password:p})})
  .then(function(r){return r.json()}).then(function(d){
    if(d.error){showMsg('userMsg',d.error,true)}
    else{document.getElementById('newUsr').value='';document.getElementById('newPwd').value='';showMsg('userMsg','新增成功！',false);loadUsers()}
  });
}
function delUser(id){
  if(!confirm('確定刪除此帳號？'))return;
  fetch('/admin/api/users/'+id,{method:'DELETE'}).then(function(r){return r.json()}).then(function(d){
    if(d.error)alert(d.error);else loadUsers();
  });
}
function toggleUser(id,active){
  fetch('/admin/api/users/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({is_active:active})}).then(function(){loadUsers()});
}
function changePassword(){
  var id=document.getElementById('chgUsr').value;
  var p=document.getElementById('chgPwd').value;
  if(!id||p.length<6){showMsg('pwdMsg','請選擇帳號，密碼至少6個字元',true);return}
  fetch('/admin/api/users/'+id+'/password',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({password:p})})
  .then(function(r){return r.json()}).then(function(d){
    if(d.error){showMsg('pwdMsg',d.error,true)}
    else{document.getElementById('chgPwd').value='';showMsg('pwdMsg','密碼修改成功！',false)}
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

/* ── 標籤名稱管理 ── */
function loadTagDefs(){
  fetch('/admin/api/tag_names').then(function(r){return r.json()}).then(function(rows){
    var countEl=document.getElementById('tagNameCount');
    if(countEl)countEl.textContent='共 '+rows.length+' 個標籤';
    var html='';
    rows.forEach(function(r){
      html+='<tr id="tagrow-'+r.id+'">'
        +'<td><span id="tagname-'+r.id+'" style="font-weight:500">'+esc(r.name)+'</span>'
        +'<input id="taginput-'+r.id+'" type="text" value="'+esc(r.name)+'" style="display:none;padding:4px 8px;border:.5px solid #ddd;border-radius:4px;font-size:12px;width:160px"></td>'
        +'<td style="text-align:center;color:#aaa;font-size:12px">'+r.cnt+'</td>'
        +'<td>'
        +'<button class="btn-outline" id="editbtn-'+r.id+'" onclick="startEditTag('+r.id+')" style="margin-right:4px">改名</button>'
        +'<button class="btn-green" id="savebtn-'+r.id+'" onclick="saveTagName('+r.id+')" style="display:none;margin-right:4px">儲存</button>'
        +'<button class="btn-outline" id="cancelbtn-'+r.id+'" onclick="cancelEditTag('+r.id+')" style="display:none">取消</button>'
        +'</td></tr>';
    });
    document.getElementById('tagNamesTable').innerHTML=html||'<tr><td colspan="3" style="color:#aaa;text-align:center;padding:20px">尚無標籤，請先點「立即同步」</td></tr>';
  });
}
function startEditTag(id){
  document.getElementById('tagname-'+id).style.display='none';
  document.getElementById('taginput-'+id).style.display='';
  document.getElementById('editbtn-'+id).style.display='none';
  document.getElementById('savebtn-'+id).style.display='';
  document.getElementById('cancelbtn-'+id).style.display='';
  document.getElementById('taginput-'+id).focus();
}
function cancelEditTag(id){
  var orig=document.getElementById('tagname-'+id).textContent;
  document.getElementById('taginput-'+id).value=orig;
  document.getElementById('tagname-'+id).style.display='';
  document.getElementById('taginput-'+id).style.display='none';
  document.getElementById('editbtn-'+id).style.display='';
  document.getElementById('savebtn-'+id).style.display='none';
  document.getElementById('cancelbtn-'+id).style.display='none';
}
function saveTagName(id){
  var newName=document.getElementById('taginput-'+id).value.trim();
  var oldName=document.getElementById('tagname-'+id).textContent;
  if(!newName){alert('標籤名稱不可為空');return;}
  if(newName===oldName){cancelEditTag(id);return;}
  document.getElementById('savebtn-'+id).textContent='更新中...';
  fetch('/admin/api/tag_names/'+id+'/rename',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({new_name:newName})})
  .then(function(r){return r.json()}).then(function(d){
    if(d.ok){showMsg('syncTagMsg','「'+oldName+'」已更新為「'+newName+'」（'+d.updated_items+' 筆 Q&A 同步）',false);loadTagDefs();}
    else{alert('失敗：'+d.error);document.getElementById('savebtn-'+id).textContent='儲存';}
  });
}
function syncTagNames(){
  var btn=document.getElementById('syncTagBtn');
  btn.textContent='同步中...';btn.disabled=true;
  fetch('/admin/api/tag_names/sync',{method:'POST'})
  .then(function(r){return r.json()}).then(function(d){
    btn.textContent='立即同步';btn.disabled=false;
    showMsg('syncTagMsg','同步完成，新增 '+d.added+' 個標籤',false);
    loadTagDefs();
  }).catch(function(){btn.textContent='立即同步';btn.disabled=false;});
}

/* 預設載入 */
loadWords();
</script></body></html>'''

# ──────────────────────────────────────────────
# 管理 API — 標籤名稱管理
# ──────────────────────────────────────────────
@app.route("/admin/api/tag_names")
@require_admin
def admin_get_tag_names():
    try:
        from collections import Counter
        names = supabase.table("tag_names").select("id,name,created_at").order("name").execute().data or []
        rows  = supabase.table("qa_items").select("tags").execute().data or []
        counter = Counter()
        for r in rows:
            for t in (r.get("tags") or []):
                t = t.strip()
                if t: counter[t] += 1
        for n in names:
            n["cnt"] = counter.get(n["name"], 0)
        return jsonify(names)
    except Exception as e:
        return jsonify([])

@app.route("/admin/api/tag_names/sync", methods=["POST"])
@require_admin
def admin_sync_tag_names():
    try:
        from collections import Counter
        rows = supabase.table("qa_items").select("tags").execute().data or []
        counter = Counter()
        for r in rows:
            for t in (r.get("tags") or []):
                t = t.strip()
                if t: counter[t] += 1
        existing = {n["name"] for n in (supabase.table("tag_names").select("name").execute().data or [])}
        added = 0
        for tag in counter.keys():
            if tag not in existing:
                supabase.table("tag_names").insert({"name": tag}).execute()
                added += 1
        return jsonify({"ok": True, "added": added})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/admin/api/tag_names/<int:tag_id>/rename", methods=["POST"])
@require_admin
def admin_rename_tag(tag_id):
    try:
        data = request.get_json()
        new_name = (data.get("new_name") or "").strip()
        if not new_name:
            return jsonify({"ok": False, "error": "新名稱不可為空"}), 400
        row = supabase.table("tag_names").select("name").eq("id", tag_id).execute().data
        if not row:
            return jsonify({"ok": False, "error": "找不到此標籤"}), 404
        old_name = row[0]["name"]
        if old_name == new_name:
            return jsonify({"ok": True, "updated_items": 0})
        supabase.table("tag_names").update({"name": new_name}).eq("id", tag_id).execute()
        items = supabase.table("qa_items").select("id,tags").contains("tags", [old_name]).execute().data or []
        updated = 0
        for item in items:
            new_tags = [new_name if t == old_name else t for t in (item.get("tags") or [])]
            supabase.table("qa_items").update({"tags": new_tags}).eq("id", item["id"]).execute()
            updated += 1
        return jsonify({"ok": True, "updated_items": updated})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

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
@app.route("/admin/api/users", methods=["GET"])
@require_admin
def get_users():
    result = supabase.table("admin_users").select("id,username,created_at,is_active").order("id").execute()
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
