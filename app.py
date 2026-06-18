from flask import Flask, request, abort, jsonify, session, redirect, render_template
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
from datetime import timedelta
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
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
            session.permanent = True
            session["admin_logged_in"] = True
            session["admin_username"] = username
            try:
                uid = result.data[0]["id"]
                old_cnt = result.data[0].get("visit_count") or 0
                now_str = (datetime.now() + timedelta(hours=8)).strftime("%Y/%m/%d %H:%M")
                supabase.table("admin_users").update({"last_visit": now_str, "visit_count": old_cnt + 1}).eq("id", uid).execute()
            except Exception:
                pass
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
            session.permanent = True
            session["qa_logged_in"] = True
            session["qa_username"] = username
            try:
                uid = result.data[0]["id"]
                old_cnt = result.data[0].get("visit_count") or 0
                now_str = (datetime.now() + timedelta(hours=8)).strftime("%Y/%m/%d %H:%M")
                supabase.table("admin_users").update({"last_visit": now_str, "visit_count": old_cnt + 1}).eq("id", uid).execute()
            except Exception:
                pass
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
    return render_template('qa.html', admin_btn=admin_btn, user_label=user_label, edit_tag_btn=edit_tag_btn)

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
    return render_template('admin.html')

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


# ── 批次操作：history helpers ──
import json as _json_mod

def _load_batch_history():
    try:
        row = supabase.table('settings').select('value').eq('key', 'batch_ops_history').execute()
        if row.data:
            return _json_mod.loads(row.data[0]['value'])
    except Exception:
        pass
    return []

def _save_batch_history(history):
    val = _json_mod.dumps(history, ensure_ascii=False)
    existing = supabase.table('settings').select('value').eq('key', 'batch_ops_history').execute()
    if existing.data:
        supabase.table('settings').update({'value': val}).eq('key', 'batch_ops_history').execute()
    else:
        supabase.table('settings').insert({'key': 'batch_ops_history', 'value': val}).execute()

def _run_batch_ops_bg(tag_ops, group_ops, job_id):
    results = []
    success = 0; fail = 0; status = 'error'
    try:
        # 1. 群組改名
        for op in group_ops:
            old_g = (op.get('group') or '').strip()
            new_g = (op.get('rename_to') or '').strip()
            if not old_g or not new_g or old_g == new_g:
                continue
            try:
                supabase.table('tag_groups').update({'group_name': new_g}).eq('group_name', old_g).execute()
                results.append({'type':'group','group':old_g,'action':'renamed','rename_to':new_g})
            except Exception as e:
                results.append({'type':'group','group':old_g,'action':'error','error':str(e)})

        # 2. 標籤操作
        for op in tag_ops:
            tag       = (op.get('tag') or '').strip()
            rename_to = (op.get('rename_to') or '').strip()
            delete    = bool(op.get('delete'))
            new_group = (op.get('new_group') or '').strip()
            if not tag:
                continue
            try:
                if delete:
                    updated = 0; offset = 0
                    while True:
                        rows = supabase.table('qa_items').select('id,tags').contains('tags',[tag]).range(offset,offset+199).execute().data or []
                        for row in rows:
                            supabase.table('qa_items').update({'tags':[t for t in (row['tags'] or []) if t!=tag]}).eq('id',row['id']).execute()
                            updated += 1
                        if len(rows)<200: break
                        offset += 200
                    supabase.table('tag_groups').delete().eq('tag_name',tag).execute()
                    results.append({'type':'tag','tag':tag,'action':'deleted','updated':updated})
                    continue

                effective = tag
                if rename_to and rename_to != tag:
                    updated = 0; offset = 0
                    while True:
                        rows = supabase.table('qa_items').select('id,tags').contains('tags',[tag]).range(offset,offset+199).execute().data or []
                        for row in rows:
                            supabase.table('qa_items').update({'tags':[rename_to if t==tag else t for t in (row['tags'] or [])]}).eq('id',row['id']).execute()
                            updated += 1
                        if len(rows)<200: break
                        offset += 200
                    exists = supabase.table('tag_groups').select('tag_name').eq('tag_name',rename_to).execute().data
                    if exists:
                        supabase.table('tag_groups').delete().eq('tag_name',tag).execute()
                        action = 'merged'
                    else:
                        supabase.table('tag_groups').update({'tag_name':rename_to}).eq('tag_name',tag).execute()
                        action = 'renamed'
                    results.append({'type':'tag','tag':tag,'action':action,'rename_to':rename_to,'updated':updated})
                    effective = rename_to

                if new_group:
                    supabase.table('tag_groups').update({'group_name':new_group}).eq('tag_name',effective).execute()
                    if not rename_to or rename_to == tag:
                        results.append({'type':'tag','tag':tag,'action':'moved_group','new_group':new_group})

            except Exception as e:
                results.append({'type':'tag','tag':tag,'action':'error','error':str(e)})

        success = len([r for r in results if r.get('action') != 'error'])
        fail    = len([r for r in results if r.get('action') == 'error'])
        status  = 'done' if fail == 0 else ('partial' if success > 0 else 'error')

    except Exception as e:
        fail = 1
        results.append({'action':'error','error':str(e)})
        status = 'error'

    completed_at = (datetime.now() + timedelta(hours=8)).strftime('%Y/%m/%d %H:%M')
    history = _load_batch_history()
    for entry in history:
        if entry.get('job_id') == job_id:
            entry['status'] = status
            entry['success'] = success
            entry['fail'] = fail
            entry['completed_at'] = completed_at
            break
    _save_batch_history(history[:10])


@app.route('/admin/api/tags/batch_ops', methods=['POST'])
@require_admin
def admin_batch_tag_ops():
    body = request.get_json()
    tag_ops   = body.get('tag_ops', [])
    group_ops = body.get('group_ops', [])
    total = len(tag_ops) + len(group_ops)
    job_id = datetime.now().strftime('%Y%m%d%H%M%S')
    started_at = (datetime.now() + timedelta(hours=8)).strftime('%Y/%m/%d %H:%M')
    history = _load_batch_history()
    history.insert(0, {
        'job_id': job_id,
        'started_at': started_at,
        'completed_at': None,
        'status': 'running',
        'total': total,
        'success': 0,
        'fail': 0
    })
    _save_batch_history(history[:10])
    threading.Thread(target=_run_batch_ops_bg, args=(tag_ops, group_ops, job_id), daemon=True).start()
    return jsonify({'ok': True, 'queued': True, 'job_id': job_id})


@app.route('/admin/api/tags/batch_ops_history', methods=['GET'])
@require_admin
def admin_batch_ops_history():
    return jsonify({'ok': True, 'history': _load_batch_history()})




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
    result = supabase.table("admin_users").select("id,username,display_name,role,can_query,can_admin,created_at,is_active,perm_filter,perm_category,perm_stats,perm_token,perm_users,perm_tags,perm_groups,last_visit,visit_count").order("id").execute()
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


# ──────────────────────────────────────────────
# LINE Webhook
# ──────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"


@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    text   = (event.message.text or "").strip()
    sender = get_sender_name(event)
    if sender in HARD_BOT_SENDERS:
        return
    if any(text.startswith(p) for p in HARD_BOT_PREFIXES):
        return
    if text.startswith("整理QA"):
        parts = text.split()
        year  = parts[1] if len(parts) > 1 else None
        group_id = event.source.group_id if hasattr(event.source, "group_id") else None
        threading.Thread(target=run_analysis, args=(year, group_id), daemon=True).start()
        line_bot_api.reply_message(event.reply_token,
            TextSendMessage(text="⏳ 開始整理" + ("全部新增" if not year else year + "年") + "資料，完成後通知你！"))
        return
    if text in HARD_PHRASES:
        return
    if not EMOJI_RE.sub("", text).strip():
        return
    if any(kw in text for kw in HARD_SYSTEM):
        return
    save_message(text, sender)


@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    sender = get_sender_name(event)
    if sender in HARD_BOT_SENDERS:
        return
    try:
        content = line_bot_api.get_message_content(event.message.id)
        data    = b"".join(content.iter_content())
        filename = "images/" + event.message.id + ".jpg"
        url = upload_file(data, filename, "image/jpeg")
    except Exception as e:
        print("圖片上傳失敗：", e, flush=True)
        url = ""
    save_message("[圖片]", sender, file_url=url, file_type="image")


@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    sender = get_sender_name(event)
    if sender in HARD_BOT_SENDERS:
        return
    fname = getattr(event.message, "file_name", None) or event.message.id
    try:
        content = line_bot_api.get_message_content(event.message.id)
        data    = b"".join(content.iter_content())
        filename = "files/" + str(event.message.id) + "_" + str(fname)
        url = upload_file(data, filename, "application/octet-stream")
    except Exception as e:
        print("檔案上傳失敗：", e, flush=True)
        url = ""
    save_message("[檔案] " + str(fname), sender, file_url=url, file_type="file")


# ──────────────────────────────────────────────
# 整理QA 背景分析
# ──────────────────────────────────────────────

def run_analysis(year, group_id):
    try:
        tag_rows  = supabase.table("tag_groups").select("tag_name").execute().data
        tag_vocab = list({r["tag_name"] for r in tag_rows if r.get("tag_name")})
        tag_hint  = "、".join(tag_vocab[:1500]) if tag_vocab else ""

        if year:
            rows = fetch_messages_by_year(year)
        else:
            rows = fetch_new_messages(limit=50)

        if not rows:
            _notify(group_id, "⚠️ 沒有找到需要整理的新訊息。")
            return

        db_phrases, db_senders, db_keywords = get_db_filters()
        filtered = [r for r in rows if not should_skip(r, db_phrases, db_senders, db_keywords)]

        if not filtered:
            _notify(group_id, "⚠️ 過濾後沒有可分析的訊息。")
            return

        BATCH = 50
        total_batches = (len(filtered) + BATCH - 1) // BATCH
        saved = 0

        for i in range(0, len(filtered), BATCH):
            batch      = filtered[i:i + BATCH]
            batch_num  = (i // BATCH) + 1
            title_year = year or datetime.now().strftime("%Y")

            existing = supabase.table("qa_results")                .select("id").eq("year", title_year).eq("batch_num", batch_num).execute()
            if existing.data:
                continue

            prompt = _build_prompt(batch, tag_hint)
            try:
                from google.genai import types as gtypes
                import json as _json
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=gtypes.GenerateContentConfig(
                        response_mime_type="application/json",
                        thinking_config=gtypes.ThinkingConfig(thinking_budget=0)
                    )
                )
                raw = response.text.strip()
                raw = re.sub(r"^```json\s*", "", raw)
                raw = re.sub(r"```\s*$", "", raw)
                data2 = _json.loads(raw)
            except Exception as e:
                print("Gemini 失敗（批次%d）：%s" % (batch_num, e), flush=True)
                continue

            categories = data2.get("suggested_categories", "")
            content    = _build_qa_text(data2)
            title      = "%s年 第%d批" % (title_year, batch_num)
            result = supabase.table("qa_results").insert({
                "year": title_year, "batch_num": batch_num, "title": title,
                "content": content,
                "analyzed_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
                "start_row": i, "end_row": i + len(batch) - 1,
                "total_msgs": len(batch), "categories": categories
            }).execute()
            batch_id = result.data[0]["id"]

            items = []
            for qa in data2.get("qa_list", []):
                items.append({
                    "batch_id": batch_id, "year": title_year,
                    "batch_num": batch_num,
                    "q_text": qa.get("q_text", ""),
                    "a_text": qa.get("a_text", ""),
                    "category": qa.get("category", categories),
                    "tags": qa.get("tags", []),
                    "created_at": datetime.now().strftime("%Y/%m/%d %H:%M")
                })
            if items:
                supabase.table("qa_items").insert(items).execute()

            try:
                usage = response.usage_metadata
                save_token_log(title, {
                    "input":  usage.prompt_token_count,
                    "output": usage.candidates_token_count,
                    "total":  usage.total_token_count
                })
            except Exception:
                pass

            saved += len(items)

            if get_today_tokens() > 800000:
                _notify(group_id, "⚠️ 今日 Token 超過 80 萬，自動暫停。請明日繼續。")
                return

        _notify(group_id, "✅ 整理完成！共新增 %d 筆 Q&A（%d 批次）。" % (saved, total_batches))

    except Exception as e:
        print("run_analysis 失敗：", e, flush=True)
        _notify(group_id, "❌ 整理失敗：" + str(e)[:80])


def fetch_new_messages(limit=50):
    last = get_setting("last_analyzed_date") or "2000/01/01 00:00"
    rows = []
    offset = 0
    while True:
        r = (supabase.table("messages")
             .select("id,text,sender,created_at")
             .gt("created_at", last)
             .order("created_at")
             .range(offset, offset + 999)
             .execute())
        rows.extend(r.data)
        if len(r.data) < 1000:
            break
        offset += 1000
    if rows:
        set_setting("last_analyzed_date", rows[-1]["created_at"])
    return rows[:limit]


def fetch_messages_by_year(year):
    rows = []
    offset = 0
    while True:
        r = (supabase.table("messages")
             .select("id,text,sender,created_at")
             .like("created_at", year + "/%")
             .order("created_at")
             .range(offset, offset + 999)
             .execute())
        rows.extend(r.data)
        if len(r.data) < 1000:
            break
        offset += 1000
    return rows


def _build_prompt(rows, tag_hint=""):
    lines = ["[%s] %s：%s" % (r.get("created_at",""), r.get("sender",""), r.get("text","")) for r in rows]
    conversation = "\n".join(lines)
    tag_section = "\n優先從以下已知標籤選用（清單外才可新增）：" + tag_hint + "\n" if tag_hint else ""
    return """你是一個專業的客服 Q&A 整理助手。以下是 HyRead 電子書客服 LINE 群組的對話紀錄（共 """ + str(len(rows)) + """ 則）。

請將這些對話整理成結構化 JSON，格式如下：

{
  "qa_list": [
    {
      "q_text": "Q1：問題摘要（YYYY/MM/DD HH:MM 提問者姓名）",
      "a_text": "A：回答摘要（YYYY/MM/DD HH:MM 回答者姓名）",
      "category": "主分類名稱",
      "tags": ["標籤1", "標籤2", "標籤3"]
    }
  ],
  "general_messages": ["YYYY/MM/DD HH:MM 發話者：訊息內容"],
  "suggested_categories": "分類A, 分類B"
}

整理規則：
1. 有明確問答關係 → 放入 qa_list；沒有 → 放入 general_messages
2. 相同問題合併，A 保留最完整回答
3. q_text 以「Q序號：」開頭，a_text 以「A：」開頭
""" + tag_section + """
tags 規則：每題 2~3 個微觀標籤，第一個優先選：維修/保固/召回/操作/APP/帳號/物流/客服流程；後續描述症狀或型號；禁止使用模糊詞。

輸出必須是合法 JSON，不加任何 markdown code block。

對話紀錄：
""" + conversation


def _build_qa_text(data):
    lines = []
    for i, item in enumerate(data.get("qa_list", []), start=1):
        q = item.get("q_text", "").strip()
        a = item.get("a_text", "").strip()
        if not re.match(r"^Q\d+[：:]", q):
            q = "Q%d：%s" % (i, q)
        if not re.match(r"^A[：:]", a):
            a = "A：" + a
        lines += [q, a, "", "---", ""]
    msgs = data.get("general_messages", [])
    if msgs:
        lines += ["【一般訊息】"] + msgs
    return "\n".join(lines)


def _notify(group_id, text):
    try:
        if group_id:
            line_bot_api.push_message(group_id, TextSendMessage(text=text))
    except Exception as e:
        print("通知失敗：", e, flush=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
