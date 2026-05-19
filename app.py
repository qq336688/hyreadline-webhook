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
.yr-btn{padding:7px 10px;border-radius:6px;font-size:12px;cursor:pointer;border:.5px solid transparent;color:#666;text-align:left}
.yr-btn.active{background:#e8f5e9;border-color:#00b900;color:#1b5e20;font-weight:500}
.yr-btn:hover:not(.active){background:#f5f5f5}
.divider{height:.5px;background:#eee;margin:5px 0}
.cat-item{display:flex;align-items:center;gap:6px;padding:5px 8px;border-radius:6px;font-size:11px;color:#666;cursor:pointer}
.cat-item:hover,.cat-item.active{background:#f0fff0;color:#1b5e20}
.cat-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.cat-cnt{font-size:10px;color:#aaa;margin-left:auto}
main{flex:1;display:flex;flex-direction:column;overflow:hidden}
.search-bar{padding:12px 16px;border-bottom:.5px solid #e0e0e0;background:#fff}
.search-row{display:flex;gap:8px}
.kw-input{flex:1;padding:9px 14px;border:1.5px solid #00b900;border-radius:20px;font-size:13px;font-family:inherit;outline:none;background:#fff}
.search-btn{width:38px;height:38px;background:#00b900;border:none;border-radius:50%;cursor:pointer;color:#fff;font-size:18px;display:flex;align-items:center;justify-content:center}
.meta{display:flex;align-items:center;gap:8px;margin-top:6px;font-size:11px;color:#aaa}
.meta-badge{background:#e8f5e9;color:#2e7d32;padding:2px 8px;border-radius:99px;font-weight:500}
.results{flex:1;overflow-y:auto;padding:14px 16px;display:flex;flex-direction:column;gap:10px}
.count-row{font-size:12px;color:#888;padding-bottom:6px;border-bottom:.5px solid #eee}
.card{background:#fff;border:.5px solid #e0e0e0;border-radius:10px;padding:13px 15px}
.card:hover{border-color:#b0bec5}
.q-row{display:flex;gap:8px;margin-bottom:8px}
.q-icon{width:22px;height:22px;background:#e8f5e9;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;color:#2e7d32;flex-shrink:0;margin-top:1px;font-weight:500}
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
</style></head><body>
<div class="topbar">📋 HyRead LINE Q&A 查詢系統
  <a href="/admin">⚙ 管理介面</a>
  <a href="/qa/logout" style="margin-left:6px">登出</a>
</div>
<div class="wrap">
  <aside>
    <div class="sb-lbl">查詢範圍</div>
    <div class="yr-btn active" onclick="setYr(this,'')">全部年份</div>
    <div class="yr-btn" onclick="setYr(this,'2019')">2019 年</div>
    <div class="yr-btn" onclick="setYr(this,'2020')">2020 年</div>
    <div class="yr-btn" onclick="setYr(this,'2021')">2021 年</div>
    <div class="yr-btn" onclick="setYr(this,'2022')">2022 年</div>
    <div class="yr-btn" onclick="setYr(this,'2023')">2023 年</div>
    <div class="yr-btn" onclick="setYr(this,'2024')">2024 年</div>
    <div class="yr-btn" onclick="setYr(this,'2025')">2025 年</div>
    <div class="yr-btn" onclick="setYr(this,'2026')">2026 年</div>
    <div class="yr-btn" onclick="setYr(this,'日常')">日常新增</div>
    <div class="divider"></div>
    <div class="sb-lbl">問題分類</div>
    <div id="catList"></div>
  </aside>
  <main>
    <div class="search-bar">
      <div class="search-row">
        <input class="kw-input" id="kw" placeholder="輸入關鍵字，例如：召回、APP無法登入、保固..."
          onkeydown="if(event.key===String.fromCharCode(13))search()">
        <button class="search-btn" onclick="search()" title="搜尋">&#x2315;</button>
      </div>
      <div class="meta">
        <span id="scopeTxt">查詢範圍：全部年份</span>
        <span id="cntBadge" class="meta-badge" style="display:none"></span>
        <span style="margin-left:auto">直接搜尋資料庫，無需 AI 配額</span>
      </div>
    </div>
    <div class="results" id="results">
      <div class="empty" id="homeState">
        <div style="font-size:14px;font-weight:500;color:#555;margin-bottom:8px">輸入關鍵字開始搜尋</div>
        <div class="chips">
          <div class="chip" onclick="fill(this.textContent)">召回</div>
          <div class="chip" onclick="fill(this.textContent)">保固</div>
          <div class="chip" onclick="fill(this.textContent)">APP無法登入</div>
          <div class="chip" onclick="fill(this.textContent)">退款</div>
          <div class="chip" onclick="fill(this.textContent)">帳號</div>
          <div class="chip" onclick="fill(this.textContent)">維修</div>
        </div>
        <div style="width:100%;max-width:640px;margin-top:20px;text-align:left">
          <div style="font-size:11px;color:#aaa;letter-spacing:.5px;margin-bottom:10px;padding-left:2px">📂 全部問題分類</div>
          <div id="catBrowse" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px"></div>
        </div>
      </div>
    </div>
  </main>
</div>
<script>
var yr='',catFilter='';
function setYr(el,y){
  yr=y;
  document.querySelectorAll('.yr-btn').forEach(function(b){b.classList.remove('active')});
  el.classList.add('active');
  document.getElementById('scopeTxt').textContent='查詢範圍：'+(y||'全部年份');
  if(document.getElementById('kw').value.trim())search();
}
function fill(t){document.getElementById('kw').value=t;search()}
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
  if(!kw)return;
  document.getElementById('results').innerHTML='<div class="loading">搜尋中...</div>';
  document.getElementById('cntBadge').style.display='none';
  fetch('/qa/api/search',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({keyword:kw,year:yr,category:catFilter})})
  .then(function(r){return r.json()}).then(function(d){renderResults(d,kw)})
  .catch(function(){document.getElementById('results').innerHTML='<div class="err">查詢失敗，請稍後再試</div>'});
}
function renderResults(d,kw){
  var badge=document.getElementById('cntBadge');
  if(!d.results||d.results.length===0){
    badge.style.display='none';
    document.getElementById('results').innerHTML='<div class="empty"><div>找不到「'+esc(kw)+'」的相關資料</div><div style="font-size:12px;margin-top:4px">請換個關鍵字試試</div></div>';
    return;
  }
  badge.textContent='找到 '+d.total+' 筆';badge.style.display='';
  var html='<div class="count-row">共 '+d.total+' 筆符合「'+esc(kw)+'」的 Q&A</div>';
  d.results.forEach(function(r){
    var cats=(r.category||'').split(/[、,，]/).filter(function(c){return c.trim()});
    var catHtml=cats.slice(0,3).map(function(c){return '<span class="tag tag-cat">'+esc(c.trim())+'</span>'}).join('');
    html+='<div class="card">'
      +'<div class="q-row"><div class="q-icon">Q</div><div class="q-txt">'+hilite(esc(r.q_text||''),kw)+'</div></div>'
      +'<div class="card-tags">'+catHtml+'<span class="tag tag-yr">'+esc(r.year||'')+'</span></div>'
      +'<div class="a-lbl">回答</div>'
      +'<div class="a-txt">'+hilite(esc(r.a_text||''),kw)+'</div>'
      +'</div>';
  });
  document.getElementById('results').innerHTML=html;
}
fetch('/qa/api/categories_summary').then(function(r){return r.json()}).then(function(cats){
  var html='';
  cats.forEach(function(c){
    html+='<div class="cat-item" onclick="setCat(this,\\''+esc(c.cat)+'\\')">\'
      +'<div class="cat-dot" style="background:#1565c0"></div>'+esc(c.cat)
      +'<span class="cat-cnt">'+c.cnt+'</span></div>';
  });
  document.getElementById('catList').innerHTML=html||'<div style="font-size:11px;color:#ccc;padding:4px 8px">尚無分類</div>';
  /* 首頁分類瀏覽卡片 */
  var browse=document.getElementById('catBrowse');
  if(browse){
    var bHtml='';
    cats.forEach(function(c){
      bHtml+='<div class="cat-card" onclick="fill(\\''+esc(c.cat)+'\\')">'
        +'<span>'+esc(c.cat)+'</span>'
        +'<span class="cat-card-cnt">'+c.cnt+'</span>'
        +'</div>';
    });
    browse.innerHTML=bHtml||'<div style="color:#ccc;font-size:12px">尚無分類資料</div>';
  }
}).catch(function(){});
function setCat(el,c){
  document.querySelectorAll('.cat-item').forEach(function(e){e.classList.remove('active')});
  if(catFilter===c){catFilter=''}else{catFilter=c;el.classList.add('active')}
  if(document.getElementById('kw').value.trim())search();
}
</script></body></html>'''

# ──────────────────────────────────────────────
# Q&A API
# ──────────────────────────────────────────────
@app.route("/qa/api/categories_summary")
@require_qa
def qa_categories_summary():
    try:
        rows = supabase.table("qa_items").select("category").execute().data
        from collections import Counter
        counter = Counter()
        for r in rows:
            for c in re.split(r"[、,，]", r.get("category") or ""):
                c = c.strip()
                if c:
                    counter[c] += 1
        result = [{"cat": k, "cnt": v} for k, v in counter.most_common(10)]
        return jsonify(result)
    except Exception as e:
        return jsonify([])

@app.route("/qa/api/batches")
@require_qa
def qa_batches():
    result = supabase.table("qa_results").select("id,year,batch_num,title,analyzed_at,total_msgs,categories,user_category,category_confirmed").order("id").execute()
    return jsonify(result.data)

@app.route("/qa/api/search", methods=["POST"])
@require_qa
def qa_search():
    data = request.get_json()
    keyword = (data.get("keyword") or "").strip()
    year = data.get("year", "")
    category = data.get("category", "")
    if not keyword:
        return jsonify({"results": [], "total": 0})
    try:
        or_filter = "q_text.ilike.%" + keyword + "%,a_text.ilike.%" + keyword + "%"
        query = supabase.table("qa_items").select("*").or_(or_filter)
        if year:
            query = query.eq("year", year)
        if category:
            query = query.ilike("category", "%" + category + "%")
        rows = query.order("id").execute().data
        return jsonify({"results": rows[:30], "total": len(rows)})
    except Exception as e:
        print("搜尋失敗：", e, flush=True)
        return jsonify({"results": [], "total": 0, "error": str(e)})

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

/* 預設載入 */
loadWords();
</script></body></html>'''

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
            t = r.get("type","phrase")
            if t == "phrase":   phrases.add(r["word"])
            elif t == "sender": senders.add(r["word"])
            elif t == "keyword": keywords.append(r["word"])
        return phrases, senders, keywords
    except:
        return set(), set(), []

def should_skip(msg, db_phrases=None, db_senders=None, db_keywords=None):
    text   = (msg.get("text")   or "").strip()
    sender = (msg.get("sender") or "").strip()
    if not text: return True
    if sender in HARD_BOT_SENDERS: return True
    if db_senders and sender in db_senders: return True
    if any(text.startswith(p) for p in HARD_BOT_PREFIXES): return True
    if text.startswith("整理QA"): return True
    if any(kw in text for kw in HARD_SYSTEM): return True
    if db_keywords and any(kw in text for kw in db_keywords): return True
    if not EMOJI_RE.sub("", text).strip(): return True
    if text in HARD_PHRASES: return True
    if db_phrases and text in db_phrases: return True
    if text in ("[圖片]","[貼圖]","[Sticker]") and not msg.get("file_url"): return True
    return False

# ──────────────────────────────────────────────
# Gemini 分析
# ──────────────────────────────────────────────
def analyze_messages(title, messages):
    db_phrases, db_senders, db_keywords = get_db_filters()
    filtered = [m for m in messages if not should_skip(m, db_phrases, db_senders, db_keywords)]
    print("過濾前：", len(messages), "→ 過濾後：", len(filtered), flush=True)
    messages = filtered

    conversation = ""
    for msg in messages:
        line = "[" + msg.get("created_at","") + "] " + msg.get("sender","未知") + "：" + msg.get("text","")
        if msg.get("file_url"):
            line += " 📎" + msg["file_url"]
        conversation += line + "\n"

    prompt = (
        "以下是LINE群組的客服對話記錄（" + title + "），請完成兩件事：\n\n"
        "【第一部分】整理成Q&A格式\n"
        "規則：\n"
        "1. 自動判斷哪些訊息是問題、哪些是回答\n"
        "2. 相同或相似的問題合併成一個Q\n"
        "3. 問題內容後面用括號標明時間與提問者，格式：（YYYY/MM/DD HH:MM 姓名）\n"
        "4. 回答內容後面用括號標明時間與回答者，格式：（YYYY/MM/DD HH:MM 姓名）\n"
        "5. 若有多人回答，用分號「；」連接在同一個A裡，每段回答後各自加括號\n"
        "6. 如果有附圖或附檔，在該Q或A下方另起一行標示「附檔：[說明] [連結]」\n"
        "7. 沒有明確問答關係的訊息，獨立列在【一般訊息】區塊\n"
        "8. 請用繁體中文輸出\n\n"
        "【第二部分】問題分類建議\n"
        "根據這批對話內容，在最後輸出分類標籤：\n"
        "【分類標籤】維修、保固、操作（依實際內容，可自行新增類別）\n\n"
        "對話記錄：\n" + conversation[:30000] + "\n\n"
        "輸出格式：\n"
        "【" + title + " Q&A整理】\n\n"
        "Q1：[問題]（YYYY/MM/DD HH:MM 姓名）\n"
        "A：[回答]（YYYY/MM/DD HH:MM 姓名）\n\n"
        "---\n\n【一般訊息】\n[時間] 發話者：內容\n\n---\n\n"
        "【分類標籤】類別1、類別2\n"
    )

    # 503 自動重試（最多 5 次，間隔 15/30/60/120 秒）
    delays = [15, 30, 60, 120, 120]
    for attempt, delay in enumerate(delays, 1):
        try:
            response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            break
        except Exception as e:
            err_str = str(e)
            if "503" in err_str or "UNAVAILABLE" in err_str:
                if attempt <= len(delays) - 1:
                    print(f"Gemini 503，第 {attempt} 次重試，等待 {delay} 秒...", flush=True)
                    time.sleep(delay)
                    continue
            raise  # 非 503 或已達上限，直接往上拋出
    usage = response.usage_metadata
    token_info = {
        "input":  getattr(usage, "prompt_token_count", 0),
        "output": getattr(usage, "candidates_token_count", 0),
        "total":  getattr(usage, "total_token_count", 0)
    }
    txt = response.text or ""
    categories = ""
    if "【分類標籤】" in txt:
        try:
            categories = txt.split("【分類標籤】")[-1].strip().split("\n")[0].strip()
        except:
            pass
    return txt, token_info, categories

# ──────────────────────────────────────────────
# 背景執行：自動跑完整年所有批次
# ──────────────────────────────────────────────
def process_year_background(year, group_id):
    SIZE = 50
    # 從上次失敗的批次繼續（查已存入的最大批次）
    try:
        done = supabase.table("qa_results").select("batch_num")\
            .eq("year", year).order("batch_num", desc=True).limit(1).execute()
        last_done = done.data[0]["batch_num"] if done.data else 0
    except:
        last_done = 0
    offset = last_done * SIZE
    batch_num = last_done + 1
    if last_done > 0:
        print("從第", batch_num, "批繼續（已完成前", last_done, "批）", flush=True)
        line_bot_api.push_message(group_id, TextSendMessage(
            text="📋 " + year + " 年從第 " + str(batch_num) + " 批繼續（已完成前 " + str(last_done) + " 批）"
        ))
    print("=== 背景開始：", year, "年 ===", flush=True)
    while True:
        try:
            msgs = supabase.table("messages").select("*")\
                .like("created_at", year + "%").order("id")\
                .range(offset, offset + SIZE - 1).execute().data
            if not msgs:
                line_bot_api.push_message(group_id, TextSendMessage(
                    text="🎉 " + year + " 年全部整理完成！共 " + str(batch_num-1) + " 批\n📊 " + WEB_URL))
                break
            label = year + "年第" + str(batch_num) + "批"
            qa_text, token_info, categories = analyze_messages(label, msgs)
            save_token_log(label, token_info)
            result_id = None
            try:
                r = supabase.table("qa_results").insert({
                    "year": year, "batch_num": batch_num, "title": label,
                    "content": qa_text,
                    "analyzed_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
                    "start_row": offset+1, "end_row": offset+len(msgs),
                    "total_msgs": len(msgs), "categories": categories
                }).execute()
                if r.data:
                    result_id = r.data[0]["id"]
            except Exception as e:
                print("qa_results 儲存失敗：", e, flush=True)
            parse_and_save_qa_items(qa_text, year, batch_num, result_id, categories)
            offset += len(msgs)

            # ── 檢查今日 token 用量 ──
            today_tokens = get_today_tokens()
            print("今日累積 tokens：", today_tokens, flush=True)
            if today_tokens >= 800000:
                line_bot_api.push_message(group_id, TextSendMessage(
                    text="⚠️ Token 用量警告！\n"
                    "今日已使用 " + str(today_tokens) + " tokens\n"
                    "已達免費上限 80%，自動暫停分析。\n"
                    "已完成前 " + str(batch_num) + " 批（" + str(offset) + " 筆）\n\n"
                    "📊 查看用量：\nhttps://hyreadline-webhook.onrender.com/admin"
                ))
                print("Token 超過 80% 上限，暫停處理", flush=True)
                break

            if len(msgs) < SIZE:
                line_bot_api.push_message(group_id, TextSendMessage(
                    text="🎉 " + year + " 年全部整理完成！共 " + str(batch_num) + " 批，" + str(offset) + " 筆\n📊 " + WEB_URL))
                break
            batch_num += 1
        except Exception as e:
            print("背景錯誤：", e, flush=True)
            line_bot_api.push_message(group_id, TextSendMessage(
                text="⚠️ 第 " + str(batch_num) + " 批失敗：" + str(e) + "\n已完成前 " + str(batch_num-1) + " 批"))
            break

# ──────────────────────────────────────────────
# Webhook
# ──────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    sig = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, sig)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    text   = event.message.text.strip()
    sender = get_sender_name(event)

    # 整理QA 年份（自動全年分批，背景執行）
    if text.startswith("整理QA ") and len(text) == 9:
        year = text.split(" ")[1]
        if year.isdigit() and len(year) == 4:
            group_id = event.source.group_id
            try:
                total = supabase.table("messages").select("id", count="exact")\
                    .like("created_at", year + "%").execute().count or 0
            except:
                total = 0
            batch_count = (total // 50) + (1 if total % 50 else 0)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(
                text="⏳ 開始分析 " + year + " 年資料\n共 " + str(total) + " 筆，約需 " +
                     str(batch_count) + " 批\n自動處理中，完成後通知您，請勿重複下指令"))
            threading.Thread(target=process_year_background, args=(year, group_id), daemon=True).start()
            return

    # 整理QA（新增訊息）
    if text == "整理QA":
        line_bot_api.reply_message(event.reply_token,
            TextSendMessage(text="⏳ 正在分析新增對話，需要約3~5分鐘，請稍候..."))
        try:
            last_date = get_setting("last_analyzed_date") or ""
            msgs = supabase.table("messages").select("*")\
                .gt("created_at", last_date).order("id").limit(50).execute().data
            if not msgs:
                line_bot_api.push_message(event.source.group_id,
                    TextSendMessage(text="目前沒有新的對話需要整理！"))
            else:
                label = "新增對話（" + (last_date or "最早") + " 之後）"
                qa_text, token_info, categories = analyze_messages(label, msgs)
                save_token_log(label, token_info)
                try:
                    r2 = supabase.table("qa_results").insert({
                        "year": "日常", "batch_num": 0, "title": label,
                        "content": qa_text,
                        "analyzed_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
                        "start_row": 0, "end_row": len(msgs),
                        "total_msgs": len(msgs), "categories": categories
                    }).execute()
                    rid2 = r2.data[0]["id"] if r2.data else None
                except Exception as e:
                    print("qa_results 儲存失敗：", e, flush=True)
                    rid2 = None
                parse_and_save_qa_items(qa_text, "日常", 0, rid2, categories)
                set_setting("last_analyzed_date", datetime.now().strftime("%Y/%m/%d %H:%M"))
                line_bot_api.push_message(event.source.group_id, TextSendMessage(
                    text="✅ 新增對話整理完成！共 " + str(len(msgs)) + " 則\n分類：" +
                         (categories or "未分類") + "\n📊 " + WEB_URL))
        except Exception as e:
            print("錯誤：", e, flush=True)
            line_bot_api.push_message(event.source.group_id,
                TextSendMessage(text="整理失敗：" + str(e)))
        return

    save_message(text, sender)

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    sender = get_sender_name(event)
    content = b"".join(line_bot_api.get_message_content(event.message.id).iter_content())
    url = upload_file(content, "images/" + event.message.id + ".jpg", "image/jpeg")
    save_message("[圖片]", sender, file_url=url, file_type="image")

@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    sender = get_sender_name(event)
    content = b"".join(line_bot_api.get_message_content(event.message.id).iter_content())
    url = upload_file(content, "files/" + event.message.id + "_" + event.message.file_name, "application/octet-stream")
    save_message("[檔案：" + event.message.file_name + "]", sender, file_url=url, file_type="file")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
