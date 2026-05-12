from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (MessageEvent, TextMessage, TextSendMessage,
                             ImageMessage, FileMessage)
import os, io, resend
from docx import Document
from supabase import create_client

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ.get("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("CHANNEL_SECRET"))

resend.api_key = os.environ.get("RESEND_API_KEY")
TO_EMAIL = "qq8298@gmail.com"

supabase = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_KEY")
)

def get_sender_name(event):
    try:
        profile = line_bot_api.get_group_member_profile(
            event.source.group_id,
            event.source.user_id
        )
        return profile.display_name
    except:
        return "未知用戶"

def save_message(text, sender, msg_type, file_url=""):
    supabase.table("messages").insert({
        "text": text,
        "sender": sender,
        "type": msg_type,
        "file_url": file_url,
        "file_type": "none"
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

def send_email_with_docx(qa_list):
    doc = Document()
    doc.add_heading('LINE 群組 Q&A 整理報告', 0)
    
    q_num = 0
    i = 0
    while i < len(qa_list):
        msg = qa_list[i]
        if msg["type"] == "問題":
            q_num += 1
            p = doc.add_paragraph()
            p.add_run(f"Q{q_num}（{msg['sender']}）：{msg['text']}").bold = True
            if msg.get("file_url"):
                doc.add_paragraph(f"📎 {msg['file_url']}")
            j = i + 1
            while j < len(qa_list) and qa_list[j]["type"] == "回答":
                a = qa_list[j]
                p2 = doc.add_paragraph()
                p2.add_run(f"A（{a['sender']}）：{a['text']}")
                if a.get("file_url"):
                    doc.add_paragraph(f"📎 {a['file_url']}")
                j += 1
            doc.add_paragraph("")
            i = j
        else:
            i += 1

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    import base64
    encoded = base64.b64encode(buffer.read()).decode()

    resend.Emails.send({
        "from": "onboarding@resend.dev",
        "to": TO_EMAIL,
        "subject": "LINE 群組 Q&A 整理報告",
        "html": "<p>您好，附件為整理後的 Q&A 文件，請查收。</p>",
        "attachments": [{
            "filename": "QA整理.docx",
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
        result = supabase.table("messages").select("*").order("id").execute()
        messages = result.data
        if not messages:
            reply = "目前還沒有收集到任何訊息！"
        else:
            try:
                send_email_with_docx(messages)
                supabase.table("messages").delete().neq("id", 0).execute()
                reply = "✅ Q&A 整理完成！已寄送 Word 檔到您的信箱，請查收。"
            except Exception as e:
                reply = f"整理失敗：{str(e)}"
    elif text.endswith("#問題"):
        content = text.replace("#問題", "").strip()
        save_message(content, sender, "問題")
        reply = None
    elif text.endswith("#回答"):
        content = text.replace("#回答", "").strip()
        save_message(content, sender, "回答")
        reply = None
    else:
        reply = None

    if reply:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    sender = get_sender_name(event)
    message_content = line_bot_api.get_message_content(event.message.id)
    content = b"".join(chunk for chunk in message_content.iter_content())
    filename = f"images/{event.message.id}.jpg"
    url = upload_file(content, filename, "image/jpeg")
    save_message("", sender, "其他", file_url=url)

@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    sender = get_sender_name(event)
    message_content = line_bot_api.get_message_content(event.message.id)
    content = b"".join(chunk for chunk in message_content.iter_content())
    filename = f"files/{event.message.id}_{event.message.file_name}"
    url = upload_file(content, filename, "application/octet-stream")
    save_message("", sender, "其他", file_url=url)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
