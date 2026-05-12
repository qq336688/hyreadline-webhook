from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os, smtplib, io
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from docx import Document

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ.get("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("CHANNEL_SECRET"))

GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PASSWORD = os.environ.get("GMAIL_PASSWORD")
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

    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = TO_EMAIL
    msg['Subject'] = 'LINE 群組 Q&A 整理報告'
    msg.attach(MIMEText('您好，\n\n附件為整理後的 Q&A 文件，請查收。\n\nHyRead客服Bot', 'plain', 'utf-8'))

    part = MIMEBase('application', 'octet-stream')
    part.set_payload(buffer.read())
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', 'attachment', filename='QA整理.docx')
    msg.attach(part)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.send_message(msg)

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
