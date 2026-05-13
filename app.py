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
  <tr><td>輸入 Tokens</td><td>{total_tokens['input']:,}</td></tr>
  <tr><td>輸出 Tokens</td><td>{total_tokens['output']:,}</td></tr>
  <tr><td><b>總計 Tokens</b></td><td><b>{total_tokens['total']:,}</b></td></tr>
  <tr><td>免費額度上限</td><td>1,000,000 tokens/分鐘</td></tr>
  <tr><td>狀態</td><td>{status}</td></tr>
</table>
"""

    resend.Emails.send({
        "from": "onboarding@resend.dev",
        "to": TO_EMAIL,
        "subject": f"LINE 群組 Q&A 整理報告 {datetime.now().strftime('%Y/%m/%d')} [{subject_note}]",
        "html": f"<p>您好，附件為整理後的 Q&A 文件（{subject_note}），請確認格式與內容是否正確。</p>{token_html}",
        "attachments": [{
            "filename": f"QA整理_{subject_note}_{datetime.now().strftime('%Y%m%d')}.docx",
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

    # 整理QA 2019 ~ 2026 按年份分析
    if text.startswith("整理QA ") and len(text) == 9:
        year = text.split(" ")[1]
        if year.isdigit() and len(year) == 4:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"⏳ 正在分析 {year} 年對話，需要約3~5分鐘，完成後會寄信通知您確認...")
            )
            try:
                result = supabase.table("messages").select("*")\
                    .like("created_at", f"{year}%")\
                    .order("id")\
                    .limit(1000)\
                    .execute()
                msgs = result.data
                if not msgs:
                    line_bot_api.push_message(
                        event.source.group_id,
                        TextSendMessage(text=f"{year} 年沒有找到任何訊息！")
                    )
                else:
                    qa_text, token_info = analyze_messages(f"{year}年", msgs)
                    send_email_with_docx(
                        [(f"{year}年", qa_text)],
                        f"{year}年資料",
                        token_info
                    )
                    line_bot_api.push_message(
                        event.source.group_id,
                        TextSendMessage(text=f"✅ {year} 年整理完成！共分析 {len(msgs)} 則訊息，已寄送報告到您的信箱，請確認格式與內容！")
                    )
            except Exception as e:
                line_bot_api.push_message(
                    event.source.group_id,
                    TextSendMessage(text=f"整理失敗：{str(e)}")
                )
            return

    # 整理QA 只分析新訊息
    if text == "整理QA":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="⏳ 正在分析新增對話，完成後會寄信通知您確認...")
        )
        try:
            last_date = get_setting("last_analyzed_date") or ""
            result = supabase.table("messages").select("*")\
                .gt("created_at", last_date)\
                .order("id")\
                .limit(1000)\
                .execute()
            msgs = result.data

            if not msgs:
                line_bot_api.push_message(
                    event.source.group_id,
                    TextSendMessage(text="目前沒有新的對話需要整理！")
                )
            else:
                qa_text, token_info = analyze_messages("新增對話", msgs)
                send_email_with_docx(
                    [("新增對話", qa_text)],
                    f"新增對話（{last_date}之後）",
                    token_info
                )
                set_setting("last_analyzed_date", datetime.now().strftime("%Y/%m/%d %H:%M"))
                line_bot_api.push_message(
                    event.source.group_id,
                    TextSendMessage(text=f"✅ 新增對話整理完成！共 {len(msgs)} 則訊息，已寄送報告到您的信箱，請確認！")
                )
        except Exception as e:
            line_bot_api.push_message(
                event.source.group_id,
                TextSendMessage(text=f"整理失敗：{str(e)}")
            )
        return

    save_message(text, sender)

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    sender = get_sender_name(event)
    content = b"".join(line_bot_api.get_message_content(event.message.id).iter_content())
    url = upload_file(content, f"images/{event.message.id}.jpg", "image/jpeg")
    save_message("[圖片]", sender, file_url=url, file_type="image")

@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    sender = get_sender_name(event)
    content = b"".join(line_bot_api.get_message_content(event.message.id).iter_content())
    url = upload_file(content, f"files/{event.message.id}_{event.message.file_name}", "application/octet-stream")
    save_message(f"[檔案：{event.message.file_name}]", sender, file_url=url, file_type="file")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
