from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ.get("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("CHANNEL_SECRET"))

messages = []

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
            qa_list = []
            for i, msg in enumerate(messages, 1):
                qa_list.append(f"Q{i}：{msg}")
            reply = "📋 整理後的 Q&A：\n\n" + "\n\n".join(qa_list)
            messages.clear()
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply)
        )
    else:
        messages.append(text)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
