from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (MessageEvent, TextMessage, TextSendMessage,
                             ImageMessage, FileMessage)
import os, io, resend
from google import genai
from docx import Document
from supabase import create_client
import base64
from datetime import datetime

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ.get("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("CHANNEL_SECRET"))

resend.api_key = os.environ.get("RESEND_API_KEY")
TO_EMAIL = "qq8298@gmail.com"

supabase = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_KEY")
)

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

def get_sender_name(event):
    try:
        profile = line_bot_api.get_group_member_profile(
            event.source.group_id,
            event.source.user_id
        )
        return profile.display_name
    except:
        return "未知用戶"

def get_setting(key):
    result = supabase.table("settings").select("value").eq("key", key).execute()
    if result.data:
        return result.data[0]["value"]
    return None

def set_setting(key, value):
    supabase.table("settings").update({"value": value}).eq("key", key).execute()

def save_message(text, sender, file_url="", file_type="none"):
    supabase.table("messages").insert({
        "text": text,
        "sender": sender,
        "type": "message",
        "file_url": file_url,
        "file_type": file_type,
        "created_at": datetime.now().strftime("%Y/%m/%d %H:%M")
    }).execute()

def upload_file(content, filename, content_type):
    try:
        supabase.storage.from_("line-files").upload(
            filename, content, {"content-type": content_type}
        )
        return supabase.storage.from_("line-files").get_public_url(filename)
    except:
        return ""

def analyze_messages(title, messages):
    conversation = ""
    for msg in messages:
        time = msg.get("created_at", "")
        sender = msg.get("sender", "未知")
        text = msg.get("text", "")
        file_url = msg.get("file_url", "")
        line = f"[{time}] {sender}：{text}"
        if file_url:
            line += f" 📎{file_url}"
        conversation += line + "\n"

    prompt = f"""以下是LINE群組的客服對話記錄（{title}），請整理成Q&A格式。

規則：
1. 自動判斷哪些訊息是問題、哪些是回答
2. 相同或相似的問題合併成一個Q
3. 每個Q後面標明提問者（可能多人）和時間
4. 每個A後面標明回答者（可能多人）和時間
5. 如果有附圖或附檔，附上連結
6. 沒有明確問答關係的訊息，獨立列在【一般訊息】區塊，不要忽略，讓使用者自行判斷
7. 請用繁體中文輸出

對話記錄：
{conversation[:40000]}

請用以下格式輸出：

【{title} Q&A整理】

Q1：[問題內容]
時間：[時間] 提問者：[姓名]

A：[回答內容]
時間：[時間] 回答者：[姓名]

---

【一般訊息】
[時間] 發話者：訊息內容

---
"""
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    usage = response.usage_metadata
    token_info = {
        "input": getattr(usage, "prompt_token_count", 0),
        "output": getattr(usage, "candidates_token_count", 0),
        "total": getattr(usage, "total_token_count", 0)
    }
    return response.text, token_info

def send_email_with_docx(all_qa_content, subject_note="", total_tokens=None):
    doc = Document()
    doc.add_heading('LINE 群組 Q&A 整理報告', 0)
    doc.add_paragraph(f"整理時間：{datetime.now().strftime('%Y/%m/%d %H:%M')}")
    if subject_note:
        doc.add_paragraph(f"整理範圍：{subject_note}")
    doc.add_paragraph("")

    for title, content in all_qa_content:
        doc.add_heading(title, level=1)
        for line in content.split("\n"):
            doc.add_paragraph(line)
        doc.add_paragraph("")

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    encoded = base64.b64encode(buffer.read()).decode()

    token_html = ""
    if total_tokens:
        status = "✅ 在免費範圍內" if total_tokens['total'] < 1000000 else "⚠️ 接近上限"
        token_html = f"""
<hr>
<h3>📊 本次 Token 使用量</h3>
<table border="1" cellpadding="5" style="border-collapse:collapse">
