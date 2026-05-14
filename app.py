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

# ──────────────────────────────────────────────
# Keep-alive 端點（供 UptimeRobot 每 14 分鐘 ping）
# ──────────────────────────────────────────────
@app.route("/ping", methods=["GET"])
def ping():
    return "pong", 200

# ──────────────────────────────────────────────
# 基本工具函式
# ──────────────────────────────────────────────
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

def save_token_log(title, token_info):
    try:
        supabase.table("token_logs").insert({
            "analyzed_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
            "title": title,
            "input_tokens": token_info.get("input", 0),
            "output_tokens": token_info.get("output", 0),
            "total_tokens": token_info.get("total", 0)
        }).execute()
        print("Token log 寫入成功")
    except Exception as e:
        print("Token log 寫入失敗：", e)

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
        time_val = msg.get("created_at", "")
        sender = msg.get("sender", "未知")
        text = msg.get("text", "")
        file_url = msg.get("file_url", "")
        line_str = "[" + time_val + "] " + sender + "：" + text
        if file_url:
            line_str += " 📎" + file_url
        conversation += line_str + "\n"

    prompt = (
        "以下是LINE群組的客服對話記錄（" + title + "），請整理成Q&A格式。\n\n"
        "規則：\n"
        "1. 自動判斷哪些訊息是問題、哪些是回答\n"
        "2. 相同或相似的問題合併成一個Q\n"
        "3. 問題內容後面用括號標明時間與提問者，格式：（YYYY/MM/DD HH:MM 姓名）\n"
        "4. 回答內容後面用括號標明時間與回答者，格式：（YYYY/MM/DD HH:MM 姓名）\n"
        "5. 若有多人回答，用分號「；」連接在同一個A裡，每段回答後各自加括號\n"
        "6. 如果有附圖或附檔，在該Q或A下方另起一行標示「附檔：[說明] [連結]」\n"
        "7. 沒有明確問答關係的訊息，獨立列在【一般訊息】區塊，不要忽略，讓使用者自行判斷\n"
        "8. 請用繁體中文輸出\n\n"
        "對話記錄：\n"
        + conversation[:30000] +
        "\n\n請用以下格式輸出：\n\n"
        "【" + title + " Q&A整理】\n\n"
        "Q1：[問題內容]（YYYY/MM/DD HH:MM 提問者姓名）\n"
        "A：[回答內容]（YYYY/MM/DD HH:MM 回答者姓名）；[補充回答]（YYYY/MM/DD HH:MM 姓名）\n"
        "附檔：[說明] [連結]\n\n"
        "---\n\n"
        "【一般訊息】\n"
        "[時間] 發話者：訊息內容\n\n"
        "---\n"
    )

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

def build_token_html(total_tokens):
    if not total_tokens:
        return ""
    status = "在免費範圍內" if total_tokens["total"] < 1000000 else "接近上限"
    input_t = str(total_tokens["input"])
    output_t = str(total_tokens["output"])
    total_t = str(total_tokens["total"])
    rows = (
        "<tr><td>輸入 Tokens</td><td>" + input_t + "</td></tr>"
        "<tr><td>輸出 Tokens</td><td>" + output_t + "</td></tr>"
        "<tr><td><b>總計 Tokens</b></td><td><b>" + total_t + "</b></td></tr>"
        "<tr><td>免費額度上限</td><td>1,000,000 tokens/分鐘</td></tr>"
        "<tr><td>狀態</td><td>" + status + "</td></tr>"
    )
    return (
        "<hr><h3>本次 Token 使用量</h3>"
        '<table border="1" cellpadding="5" style="border-collapse:collapse">'
        + rows +
        "</table>"
    )

def send_email_with_docx(all_qa_content, subject_note="", total_tokens=None):
    doc = Document()
    doc.add_heading("LINE 群組 Q&A 整理報告", 0)
    doc.add_paragraph("整理時間：" + datetime.now().strftime("%Y/%m/%d %H:%M"))
    if subject_note:
        doc.add_paragraph("整理範圍：" + subject_note)
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

    token_html = build_token_html(total_tokens)
    html_body = "<p>您好，附件為整理後的 Q&A 文件（" + subject_note + "），請確認格式與內容是否正確。</p>" + token_html

    resend.Emails.send({
        "from": "onboarding@resend.dev",
        "to": TO_EMAIL,
        "subject": "LINE 群組 Q&A 整理報告 " + datetime.now().strftime("%Y/%m/%d") + " [" + subject_note + "]",
        "html": html_body,
        "attachments": [{
            "filename": "QA整理_" + subject_note + "_" + datetime.now().strftime("%Y%m%d") + ".docx",
            "content": encoded
        }]
    })

# ──────────────────────────────────────────────
# Webhook 主入口
# ──────────────────────────────────────────────
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

    # 整理QA 年份（例如：整理QA 2019）
    if text.startswith("整理QA ") and len(text) == 9:
        year = text.split(" ")[1]
        if year.isdigit() and len(year) == 4:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="⏳ 正在分析 " + year + " 年對話，需要約3~5分鐘，完成後會寄信通知您確認...")
            )
            try:
                print("=== 開始處理 整理QA", year, "===")
                print("開始查詢 Supabase...")
                result = supabase.table("messages").select("*")\
                    .like("created_at", year + "%")\
                    .order("id")\
                    .limit(50)\
                    .execute()
                msgs = result.data
                print("查詢完成，筆數：", len(msgs), flush=True)

                if not msgs:
                    line_bot_api.push_message(
                        event.source.group_id,
                        TextSendMessage(text=year + " 年沒有找到任何訊息！")
                    )
                else:
                    print("開始呼叫 Gemini API...")
                    qa_text, token_info = analyze_messages(year + "年", msgs)
                    print("Gemini 完成！Token 使用：", token_info)

                    print("寫入 token_logs...")
                    save_token_log(year + "年", token_info)

                    print("開始寄信...")
                    send_email_with_docx(
                        [(year + "年", qa_text)],
                        year + "年資料（前200筆）",
                        token_info
                    )
                    print("寄信完成！")

                    line_bot_api.push_message(
                        event.source.group_id,
                        TextSendMessage(text="✅ " + year + " 年整理完成！共分析 " + str(len(msgs)) + " 則訊息，已寄送報告到您的信箱，請確認格式與內容！")
                    )
            except Exception as e:
                print("發生錯誤：", str(e))
                line_bot_api.push_message(
                    event.source.group_id,
                    TextSendMessage(text="整理失敗：" + str(e))
                )
            return

    # 整理QA（只分析新增訊息）
    if text == "整理QA":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="⏳ 正在分析新增對話，完成後會寄信通知您確認...")
        )
        try:
            print("=== 開始處理 整理QA（新增）===")
            last_date = get_setting("last_analyzed_date") or ""
            print("上次整理時間：", last_date)

            result = supabase.table("messages").select("*")\
                .gt("created_at", last_date)\
                .order("id")\
                .limit(50)\
                .execute()
            msgs = result.data
            print("查詢完成，筆數：", len(msgs), flush=True)

            if not msgs:
                line_bot_api.push_message(
                    event.source.group_id,
                    TextSendMessage(text="目前沒有新的對話需要整理！")
                )
            else:
                print("開始呼叫 Gemini API...")
                qa_text, token_info = analyze_messages("新增對話", msgs)
                print("Gemini 完成！Token 使用：", token_info)

                print("寫入 token_logs...")
                save_token_log("新增對話", token_info)

                print("開始寄信...")
                send_email_with_docx(
                    [("新增對話", qa_text)],
                    "新增對話（" + last_date + "之後）",
                    token_info
                )
                print("寄信完成！")

                set_setting("last_analyzed_date", datetime.now().strftime("%Y/%m/%d %H:%M"))
                line_bot_api.push_message(
                    event.source.group_id,
                    TextSendMessage(text="✅ 新增對話整理完成！共 " + str(len(msgs)) + " 則訊息，已寄送報告到您的信箱，請確認！")
                )
        except Exception as e:
            print("發生錯誤：", str(e))
            line_bot_api.push_message(
                event.source.group_id,
                TextSendMessage(text="整理失敗：" + str(e))
            )
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
