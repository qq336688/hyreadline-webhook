from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (MessageEvent, TextMessage, TextSendMessage,
                             ImageMessage, FileMessage)
import os, io, resend, google.generativeai as genai
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

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.0-flash")

def get_sender_name(event):
    try:
        profile = line_bot_api.get_group_member_profile(
            event.source.group_id,
            event.source.user_id
        )
        return profile.display_name
    except:
        return "未知用戶"

def save_message(text, sender, file_url="", file_type="none"):
    supabase.table("messages").insert({
        "text": text,
        "sender": sender,
        "type": "message",
        "file_url": file_url,
        "file_type": file_type,
        "created_at": datetime.now().isoformat()
    }).execute()

def upload_file(content, filename, content_type):
    try:
        supabase.storage.from_("line-files").upload(
            filename, content,
            {"content-type": content_type}
        )
        url = supabase.storage.from_("line-files").get_public_url(filename)
        return url
    except:
        return ""

def analyze_with_gemini(messages):
    conversation = ""
    for msg in messages:
        time = msg.get("created_at", "")[:16].replace("T", " ")
        sender = msg.get("sender", "未知")
        text = msg.get("text", "")
        file_url = msg.get("file_url", "")
        
        line = f"[{time}] {sender}：{text}"
        if file_url:
            line += f" 📎{file_url}"
        conversation += line + "\n"

    prompt = f"""以下是一個LINE群組的對話記錄，請幫我整理成Q&A格式。

規則：
1. 自動判斷哪些訊息是問題、哪些是回答
2. 相同或相似的問題合併成一個Q
3. 每個Q後面標明提問者（可能多人）和時間
4. 每個A後面標明回答者和時間
5. 如果問題或回答有附圖/附檔，附上連結
6. 沒有明確問答關係的訊息可以忽略

對話記錄：
{conversation}

請用以下格式輸出：
Q1：[問題內容]
時間：[時間]
提問者：[姓名]
（如有附件）📎 [連結]

A：[回答內容]
時間：[時間]
回答者：[姓名]
（如有附件）📎 [連結]

---
"""
    response = model.generate_content(prompt)
    return response.text

def send_email_with_docx(qa_content):
    doc = Document()
    doc.add_heading('LINE 群組 Q&A 整理報告', 0)
    doc.add_paragraph(f"整理時間：{datetime.now().strftime('%Y/%m/%d %H:%M')}")
    doc.add_paragraph("")
    
    for line in qa_content.split("\n"):
        doc.add_paragraph(line)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    encoded = base64.b64encode(buffer.read()).decode()

    resend.Emails.send({
        "from": "onboarding@resend.dev",
        "to": TO_EMAIL,
        "subject": f"LINE 群組 Q&A 整理報告 {datetime.now().strftime('%Y/%m/%d')}",
        "html": "<p>您好，附件為整理後的 Q&A 文件，請查收。</p>",
        "attachments": [{
            "filename": f"QA整理_{datetime.now().strftime('%Y%m%d')}.docx",
            "content": encoded
        }]
    })

@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    text = event.message.text.strip()
    sender = get_sender_name(event)

    if text == "整理QA":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="⏳ 正在分析對話，請稍候約30秒...")
        )
        result = supabase.table("messages").select("*").order("id").execute()
        messages = result.data
        if not messages:
            line_bot_api.push_message(
                event.source.group_id,
                TextSendMessage(text="目前還沒有收集到任何訊息！")
            )
        else:
            try:
                qa_content = analyze_with_gemini(messages)
                send_email_with_docx(qa_content)
                line_bot_api.push_message(
                    event.source.group_id,
                    TextSendMessage(text="✅ Q&A 整理完成！已寄送 Word 檔到您的信箱，請查收。")
                )
            except Exception as e:
                line_bot_api.push_message(
                    event.source.group_id,
                    TextSendMessage(text=f"整理失敗：{str(e)}")
                )
    else:
        save_message(text, sender)

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    sender = get_sender_name(event)
    message_content = line_bot_api.get_message_content(event.message.id)
    content = b"".join(chunk for chunk in message_content.iter_content())
    filename = f"images/{event.message.id}.jpg"
    url = upload_file(content, filename, "image/jpeg")
    save_message(f"[圖片]", sender, file_url=url, file_type="image")

@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    sender = get_sender_name(event)
    message_content = line_bot_api.get_message_content(event.message.id)
    content = b"".join(chunk for chunk in message_content.iter_content())
    filename = f"files/{event.message.id}_{event.message.file_name}"
    url = upload_file(content, filename, "application/octet-stream")
    save_message(f"[檔案：{event.message.file_name}]", sender, file_url=url, file_type="file")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
