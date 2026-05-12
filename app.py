from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os, io, resend
from docx import Document

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ.get("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("CHANNEL_SECRET"))

resend.api_key = os.environ.get("RESEND_API_KEY")
TO_EMAIL = "qq8298@gmail.com"

messages = []

def send_email_with_docx(qa_list):
    doc = Document()
    doc.add_heading('LINE 群組 Q&A 整理報告', 0)
    for item in qa_list:
        doc.add_paragraph(item)
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    content = buffer.read()

    import base64
    encoded = base64.b64encode(content).decode()

    resend.Emails.send({
        "from": "onboarding@resend.dev",
        "to": TO_EMAIL,
        "subject": "LINE 群組 Q&A 整理報告",
        "html": "<p>您好，附件為整理後的 Q&A 文件，請查收。</p><p>HyRead客服Bot</p>",
        "attachments": [
            {
                "filename": "QA整理.docx",
                "content": encoded
            }
        ]
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
def handle_message(event):
    text = event.message.text.strip()
    if text == "整理QA":
        if len(messages) == 0:
            reply = "目前還沒有收集到任何訊息！"
        else:
            qa_list = [f"Q{i}：{msg}" for i, msg in enumerate(messages, 1)]
            try:
                send_email_with_docx(qa_list)
                reply = "✅ Q&A 整理完成！已寄送 Word 檔到您的信箱，請查收。"
                messages.clear()
            except Exception as e:
                reply = f"整理完成但寄信失敗：{str(e)}"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    else:
        messages.append(text)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
