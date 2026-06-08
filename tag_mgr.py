"""
tag_mgr.py — 標籤名稱管理 Blueprint
在 app.py 中加入以下兩行即可啟用：
  from tag_mgr import tag_mgr_bp
  app.register_blueprint(tag_mgr_bp)
"""
from flask import Blueprint, request, jsonify, session
from functools import wraps
import os
from supabase import create_client

_supabase = None

def get_sb():
    global _supabase
    if _supabase is None:
        _supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))
    return _supabase

tag_mgr_bp = Blueprint("tag_mgr", __name__)

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return jsonify({"error": "未登入"}), 401
        return f(*args, **kwargs)
    return decorated


@tag_mgr_bp.route("/admin/api/tag_names")
@require_admin
def admin_get_tag_names():
    """列出所有 tag_names，附帶各標籤在 qa_items 的筆數"""
    try:
        from collections import Counter
        sb = get_sb()
        names = sb.table("tag_names").select("id,name,created_at").order("name").execute().data or []
        rows  = sb.table("qa_items").select("tags").execute().data or []
        counter = Counter()
        for r in rows:
            for t in (r.get("tags") or []):
                t = t.strip()
                if t:
                    counter[t] += 1
        for n in names:
            n["cnt"] = counter.get(n["name"], 0)
        return jsonify(names)
    except Exception as e:
        return jsonify([])


@tag_mgr_bp.route("/admin/api/tag_names/sync", methods=["POST"])
@require_admin
def admin_sync_tag_names():
    """從 qa_items.tags 同步所有唯一標籤到 tag_names"""
    try:
        from collections import Counter
        sb = get_sb()
        rows = sb.table("qa_items").select("tags").execute().data or []
        counter = Counter()
        for r in rows:
            for t in (r.get("tags") or []):
                t = t.strip()
                if t:
                    counter[t] += 1
        existing = {n["name"] for n in (sb.table("tag_names").select("name").execute().data or [])}
        added = 0
        for tag in counter.keys():
            if tag not in existing:
                sb.table("tag_names").insert({"name": tag}).execute()
                added += 1
        return jsonify({"ok": True, "added": added})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@tag_mgr_bp.route("/admin/api/tag_names/<int:tag_id>/rename", methods=["POST"])
@require_admin
def admin_rename_tag(tag_id):
    """改名：同步更新 tag_names 和所有 qa_items"""
    try:
        sb = get_sb()
        data = request.get_json()
        new_name = (data.get("new_name") or "").strip()
        if not new_name:
            return jsonify({"ok": False, "error": "新名稱不可為空"}), 400
        row = sb.table("tag_names").select("name").eq("id", tag_id).execute().data
        if not row:
            return jsonify({"ok": False, "error": "找不到此標籤"}), 404
        old_name = row[0]["name"]
        if old_name == new_name:
            return jsonify({"ok": True, "updated_items": 0})
        # 更新 tag_names
        sb.table("tag_names").update({"name": new_name}).eq("id", tag_id).execute()
        # 更新所有 qa_items
        items = sb.table("qa_items").select("id,tags").contains("tags", [old_name]).execute().data or []
        updated = 0
        for item in items:
            new_tags = [new_name if t == old_name else t for t in (item.get("tags") or [])]
            sb.table("qa_items").update({"tags": new_tags}).eq("id", item["id"]).execute()
            updated += 1
        print(f"tag rename: {old_name} -> {new_name}, {updated} items updated", flush=True)
        return jsonify({"ok": True, "updated_items": updated})
    except Exception as e:
        print("rename_tag error:", e, flush=True)
        return jsonify({"ok": False, "error": str(e)}), 500
