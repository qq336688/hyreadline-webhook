# ============================================================
#  HyRead LINE Q&A 歷史資料分析 — Google Colab 版
#  每批 8,000 筆，Gemini 2.5 Flash JSON 模式，支援斷點續傳
#  v2：逐題產出 tags 微觀標籤
#  使用方式：整段複製貼入 Colab 新筆記本，按 ▶ 執行
# ============================================================

# ── 第一步：安裝套件（每次開新 Colab Session 都要跑）──────────
!pip install supabase google-genai -q

# ── 第二步：填入你的金鑰（只需改這三行）─────────────────────────
SUPABASE_URL     = "https://ecflimunzbraxxjwtkyz.supabase.co"   # ← Supabase 專案 URL
SUPABASE_KEY     = "YOUR_SUPABASE_SERVICE_ROLE_KEY"              # ← Supabase service_role 金鑰（非 anon key）
GEMINI_API_KEY   = "YOUR_GEMINI_API_KEY"                         # ← Google AI Studio API Key

# ── 進階設定（通常不需要改）──────────────────────────────────────
BATCH_SIZE       = 50      # 每批送給 Gemini 的訊息筆數（2026年後訊息過長，500會出錯，全量重跑固定用50）
SUPABASE_CHUNK   = 1000    # 每次從 Supabase 抓取的筆數（PostgREST 上限）
CHECKPOINT_KEY   = "colab_offset"   # 斷點儲存在 settings 資料表的 key 名稱

# =============================================================
#  以下程式碼不需要修改
# =============================================================

import re
import json
from datetime import datetime
from supabase import create_client
from google import genai
from google.genai import types

# ── 初始化客戶端 ─────────────────────────────────────────────
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
gemini   = genai.Client(api_key=GEMINI_API_KEY)

print("✅ 客戶端初始化完成")


# =============================================================
#  工具函式
# =============================================================

def get_checkpoint() -> int:
    """從 settings 資料表讀取上次的斷點 offset"""
    try:
        r = supabase.table("settings").select("value").eq("key", CHECKPOINT_KEY).execute()
        if r.data:
            return int(r.data[0]["value"])
    except Exception as e:
        print(f"  讀取斷點失敗（視為從頭開始）：{e}")
    return 0


def save_checkpoint(offset: int):
    """將目前 offset 寫回 settings 資料表"""
    try:
        existing = supabase.table("settings").select("value").eq("key", CHECKPOINT_KEY).execute()
        if existing.data:
            supabase.table("settings").update({"value": str(offset)}).eq("key", CHECKPOINT_KEY).execute()
        else:
            supabase.table("settings").insert({"key": CHECKPOINT_KEY, "value": str(offset)}).execute()
    except Exception as e:
        print(f"  ⚠️  斷點儲存失敗：{e}")


def fetch_messages(offset: int, count: int) -> list:
    """
    從 Supabase messages 資料表抓取 count 筆訊息。
    因 PostgREST 每次上限 1,000 筆，分多次抓取再合併。
    """
    all_rows = []
    chunk_offset = offset
    remaining   = count

    while remaining > 0:
        fetch_count = min(remaining, SUPABASE_CHUNK)
        end_idx     = chunk_offset + fetch_count - 1
        try:
            r = (supabase.table("messages")
                         .select("id, text, sender, created_at")
                         .order("created_at")
                         .range(chunk_offset, end_idx)
                         .execute())
            batch = r.data or []
            all_rows.extend(batch)
            if len(batch) < fetch_count:
                break   # 已到資料庫底部
            chunk_offset += fetch_count
            remaining    -= fetch_count
        except Exception as e:
            print(f"  ⚠️  Supabase 讀取失敗（offset={chunk_offset}）：{e}")
            break

    return all_rows


def filter_messages(rows: list) -> list:
    """過濾無效訊息：字數 < 3、或含媒體標籤"""
    SKIP_TAGS    = {"[貼圖]", "[照片]", "[檔案]", "[影片]"}
    SKIP_SENDERS = {"HyRead客服"}
    SKIP_TEXTS   = {"好", "ok", "OK", "收到", "謝謝", "感謝", "了解", "好的", "嗯", "👍",
                    "整理QA", "整理 QA"}

    result = []
    for row in rows:
        text   = (row.get("text") or "").strip()
        sender = (row.get("sender") or "").strip()

        if sender in SKIP_SENDERS:
            continue
        if not text or len(text) < 3:
            continue
        if any(tag in text for tag in SKIP_TAGS):
            continue
        if text in SKIP_TEXTS:
            continue
        if re.match(r"^整理QA", text):
            continue
        result.append(row)

    return result


def infer_year(rows: list) -> str:
    """從一批訊息的 created_at 推斷主要年份"""
    years = []
    for r in rows:
        dt = r.get("created_at", "")
        m  = re.match(r"(\d{4})", str(dt))
        if m:
            years.append(m.group(1))
    if not years:
        return "未知"
    return max(set(years), key=years.count)


# ── 既有標籤詞彙表（優先使用）────────────────────────────────
TAG_VOCAB = [
    "無法更新","APP異常","APP閃退","KIOSK (kiosk)","Kiosk藍屏","Kiosk無法開機",
    "BIOS (bios)故障","Kiosk白屏","Android 8","Android 11","Android 6","Android 16",
    "Android 12","Android 10","Android 13","Android 14","Android 9","Android 15",
    "Google框架","Google Play","Android ID","Gboard輸入法","Google Drive帳戶數量",
    "Google Drive","GSF ID","保固判斷(認定)","受潮不保固","延長保固","NCC資訊",
    "保固卡","客人許願功能","pc reader","Hyread Share","HyRead HK","客服AI系統",
    "HyRead3","HyRead One","香港公共圖書館","國資圖","帳號問題","團體帳號",
    "兒童帳號","刪除書店帳號","新北市立圖書館","臺北市立圖書館","Note","Gaze X",
    "One S","Mini+","X Plus","Note Plus","Mini","Mini C","Pocket","Note Plus C",
    "One SC","Mini CC","7.8","Pro X","Pro Note C(PNC)","Pro Note","Note Plus CC",
    "Pro XC","ONE S刪除TXT","XC圖片庫","零件報價","受潮(浸水)報價","背殼報價",
    "折價券","點數退費","載具","MAC位址(地址)","生物辨識","API介接","DRM",
    "無法購書","帳號轉移","MA01錯誤","Forbidden錯誤","愛讀付費看","LINE Pay Money",
    "書單搬移","replied forbidden","點數轉贈(轉換)","零信任登入","付款失敗","嗨讀",
    "點數延期","書單封存","授權下架","書店帳號新增","18禁","海外寄送","海外送修",
    "香港販售","海外保固","海外連線","海外充電規範","電池MSDS","Evernote",
    "第三方APP","翻頁器","博客來","Facebook(fb)登入失敗","meebook","Talkback",
    "Viewsonic繪圖板","Dropbox","筆記消失","筆記問題","書檔問題","筆記閃退",
    "筆記異常","筆記同步","筆記備份","筆記恢復","筆記延遲","XC筆記本","開啟筆記本",
    "退貨","PChome","七日(七天、7天","黑貓","IP","熊老闆(熊老板)","合併寄送",
    "MOMO","退費(退貨)","PChome電子書","充電問題","主板故障","舊換新","維修折扣",
    "電壓問題","二次送修","按壓異音","喇叭破音(雜音、異音、無聲、音爆)","快充故障",
    "受潮","泡水","電池膨脹","電池故障","電池校準","電源鍵","更換電池","電池回收",
    "按鍵不靈","螢幕黏合","維修升級","卡槽問題","螢幕漸漸變黑","舊機回收",
    "破屏(破裂、破裂)","螢幕線條(出線、白線、黑線、橫線、直線、十字紋)",
    "亮點、暗點、黑點、白點、塵點","mini+掉漆","亮度不均(光源)","螢幕閃爍",
    "螢幕霧感","螢幕脫框","mini系列縫隙","螢幕氣泡","螢幕黑圈圈","螢幕黑痕",
    "螢幕燒壞(烙印)","螢幕痕跡","螢幕亂跳","前光不均","螢幕泛黃","螢幕油痕",
    "殼套影響開機","觸控筆","螢幕貼","傳輸線 (充電線)","筆芯(彎曲、斷裂、內縮)",
    "周邊配件外殼(鬆脫、脫膠、脆化、裂痕、瑕疵)","支架","筆套","背殼損壞",
    "商業發票","側翻殼不密合","保護殼安裝","背殼翹起","筆延遲","忘記密碼",
    "圖書館版","按鍵不靈敏","靜思版","隱藏網路","Wi-Fi(wifi、WIFI)","個人藏書",
    "SD卡","螢幕殘影","螢幕密碼","充電規格","TTS","home鍵","AI辨識 (AI轉文字)",
    "開放式","封閉式","CPU","PDF","螢幕投放(投影)","懸浮球","OTG","手勢功能",
    "刷新設定","螢幕蜜碼","字典檔","休眠圖","A2模式","PPI資訊","按鍵自定義",
    "GPS功能","EinkBro","筆記錄音","瑞芯","Recovery mode(Recovery模式)","A6升A8",
    "字體放大","傳輸速度","手寫功能","VoiceOver","防水功能","語言設定","容量支援",
    "飛航模式","Gcin","MTP識別","Kaleido","AI搜書","隱藏功能列","書櫃分類功能",
    "GPL規範","256灰階","禁手功能","EPUB","epub","當機","耗電(掉電)異常","休眠問題",
    "循環開機","藍牙配對","收納套","線上瀏覽","無法連接電腦傳輸","翻頁問題",
    "手寫偏移","磁吸問題","恢復原廠設定","下載字體","日曆背景圖",
    "個人藏書筆記儲存路徑","手寫筆記儲存路徑",
]
TAG_VOCAB_STR = "、".join(TAG_VOCAB)


def build_prompt(rows: list) -> str:
    """
    將訊息列表轉成給 Gemini 的 Prompt。
    v2：每題 Q&A 必須額外產出 2~3 個微觀 tags。
    v3：加入既有標籤詞彙表，優先選用。
    """
    lines = []
    for r in rows:
        t = (r.get("text") or "").strip()
        s = (r.get("sender") or "").strip()
        d = (r.get("created_at") or "").strip()
        lines.append(f"[{d}] {s}：{t}")

    conversation = "\n".join(lines)

    prompt = f"""你是一個專業的客服 Q&A 整理助手。以下是 HyRead 電子書客服 LINE 群組的對話紀錄（共 {len(rows)} 則）。

請將這些對話整理成結構化 JSON，格式如下：

{{
  "qa_list": [
    {{
      "q_text": "Q1：問題內容，保留原文具體細節（YYYY/MM/DD HH:MM 提問者姓名）",
      "a_text": "A：回答內容，保留原文具體細節（YYYY/MM/DD HH:MM 回答者姓名）",
      "category": "主分類名稱",
      "tags": ["標籤1", "標籤2", "標籤3"]
    }}
  ],
  "general_messages": [
    "YYYY/MM/DD HH:MM 發話者：訊息內容"
  ],
  "suggested_categories": "分類A, 分類B, 分類C"
}}

整理規則：
1. 有明確問答關係的對話 → 放入 qa_list，每組 Q&A 各只保留一條
2. 相同問題合併為一個 Q，A 保留最完整的回答
3. 沒有問答關係的訊息 → 放入 general_messages（不要忽略）
4. 每個 q_text 以「Q序號：」開頭，每個 a_text 以「A：」開頭
5. suggested_categories 列出本批次主要問題分類（繁體中文，逗號分隔）

【內容保留規則（非常重要，禁止過度摘要）】
- q_text / a_text 是「整理」不是「摘要」：只精簡掉語助詞、客套話、重複的問候語，具體資訊一律照抄原文用字，不要改寫成籠統句子
- 以下類型內容必須逐字保留原文寫法，不可用抽象詞取代：
  - 案號、工單號、訂單編號、序號（如 #N07247、訂單12345）
  - 金額與費用數字（如「3600元」「折抵500元」，不可簡化成「需支付費用」）
  - 產品型號、機種名稱（如 Note Plus C、Gaze X、Pro Note）
  - 網址連結、附件檔名（如檢測報告連結）
  - 具體日期、期限、保固天數
  - 錯誤代碼、版本號
- 範例（錯誤 vs 正確）：
  - 原文：「維修更換費用為3600元，維修費用可折抵檢測費500元」
  - ❌ 錯誤（過度摘要）：「A：需支付維修費用」
  - ✅ 正確：「A：維修更換費用為3600元，可折抵檢測費500元」
- 若同一問題有多筆訊息（如竹涵的檢測報告說明＋附件連結＋後續追問），a_text 要把關鍵資訊（案號、金額、連結）都合併保留，不可只挑一句代表全部

【tags 標籤規則（最重要）】
- 針對「該題本身的問題內容」產出 2~3 個微觀標籤，放入 tags 陣列
- 【優先】從以下既有標籤清單中選取符合的標籤：
  {TAG_VOCAB_STR}
- 只有當既有標籤完全無法描述該問題時，才自行新增新標籤
- 標籤必須具體，反映問題的核心面向，例如：
    ["螢幕線條(出線、白線、黑線、橫線、直線、十字紋)", "Note Plus"]
    ["保固判斷(認定)", "受潮不保固", "Pro X"]
    ["APP異常", "無法更新"]
    ["帳號問題", "借閱點數", "到期"]
- 禁止使用模糊詞（如：問題、詢問、其他）

6. 輸出必須是合法 JSON，不要加任何 markdown code block

對話紀錄如下：
{conversation}
"""
    return prompt


def call_gemini(prompt: str) -> dict:
    """呼叫 Gemini 2.5 Flash，要求回傳 JSON"""
    response = gemini.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    raw = response.text.strip()

    # 防禦：有時模型還是會包 ```json … ```
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"```\s*$", "",  raw)

    return json.loads(raw)


def build_qa_text(data: dict) -> str:
    """將 Gemini JSON 結果轉回與 app.py 相容的文字格式（存入 qa_results.content）"""
    lines = []
    for i, item in enumerate(data.get("qa_list", []), start=1):
        q = item.get("q_text", "").strip()
        a = item.get("a_text", "").strip()
        if not re.match(r"^Q\d+[：:]", q):
            q = f"Q{i}：{q}"
        if not re.match(r"^A[：:]", a):
            a = f"A：{a}"
        lines.append(q)
        lines.append(a)
        lines.append("")
        lines.append("---")
        lines.append("")

    general = data.get("general_messages", [])
    if general:
        lines.append("【一般訊息】")
        lines.extend(general)

    return "\n".join(lines)


def save_to_supabase(batch_num: int, year: str, qa_text: str,
                     data: dict, start_row: int, end_row: int, total_msgs: int,
                     raw_rows: list = None):
    """將結果存入 qa_results 並拆分至 qa_items（含逐題 tags）"""
    categories = data.get("suggested_categories", "")
    now_str    = datetime.now().strftime("%Y/%m/%d %H:%M")
    title      = f"Colab批次 {batch_num}（{year}年，{total_msgs}筆）"

    # ── 存 qa_results ──────────────────────────────────────
    result_id = None
    try:
        r = supabase.table("qa_results").insert({
            "year":        year,
            "batch_num":   batch_num,
            "title":       title,
            "content":     qa_text,
            "analyzed_at": now_str,
            "start_row":   start_row,
            "end_row":     end_row,
            "total_msgs":  total_msgs,
            "categories":  categories,
        }).execute()
        result_id = r.data[0]["id"] if r.data else None
        print(f"  ✅ qa_results 儲存成功（id={result_id}）")
    except Exception as e:
        print(f"  ⚠️  qa_results 儲存失敗：{e}")
        return

    # ── 存 qa_items（v2：含逐題 tags）───────────────────────
    if not result_id:
        return
    items = []
    for item in data.get("qa_list", []):
        q    = item.get("q_text", "").strip()
        a    = item.get("a_text", "").strip()
        tags = item.get("tags", [])
        # 防禦：確保 tags 是 list of str
        if not isinstance(tags, list):
            tags = []
        tags = [str(t).strip() for t in tags if str(t).strip()]

        if not q:
            continue
        # 原始訊息文字（供關鍵字回溯搜尋）
        src = ""
        if raw_rows:
            src = "\n".join(
                f"[{r.get('created_at','')}] {r.get('sender','')}：{r.get('text','')}"
                for r in raw_rows
            )[:8000]  # 限制長度避免過大

        items.append({
            "batch_id":    result_id,
            "year":        year,
            "batch_num":   batch_num,
            "q_text":      q,
            "a_text":      a,
            "category":    item.get("category", categories),
            "tags":        tags,
            "source_text": src,
            "created_at":  now_str,
        })

    if items:
        try:
            supabase.table("qa_items").insert(items).execute()
            print(f"  ✅ qa_items 儲存：{len(items)} 筆（含 tags）")
        except Exception as e:
            print(f"  ⚠️  qa_items 儲存失敗：{e}")


# =============================================================
#  主程式
# =============================================================

def run():
    # 1. 讀取斷點
    start_offset = get_checkpoint()
    print(f"\n{'='*55}")
    print(f"  🚀 開始分析  |  起始 offset = {start_offset}")
    print(f"{'='*55}\n")

    current_offset = start_offset
    batch_num      = (start_offset // BATCH_SIZE) + 1

    while True:
        print(f"── 批次 {batch_num}：抓取 offset {current_offset} ~ {current_offset + BATCH_SIZE - 1} ──")

        # 2. 抓取訊息
        raw_rows = fetch_messages(current_offset, BATCH_SIZE)
        if not raw_rows:
            print("✅ 已處理完所有訊息，任務結束！")
            break

        print(f"  抓取：{len(raw_rows)} 筆")

        # 3. 過濾無效訊息
        filtered = filter_messages(raw_rows)
        print(f"  過濾後：{len(filtered)} 筆（過濾掉 {len(raw_rows) - len(filtered)} 筆）")

        if not filtered:
            print("  此批次全部被過濾，跳過 Gemini 分析")
            current_offset += len(raw_rows)
            save_checkpoint(current_offset)
            batch_num += 1
            continue

        # 4. 推斷年份
        year = infer_year(filtered)
        print(f"  主要年份：{year}")

        # 5. 呼叫 Gemini
        print("  ⏳ 呼叫 Gemini 2.5 Flash 分析中...")
        try:
            prompt   = build_prompt(filtered)
            data     = call_gemini(prompt)
            qa_count = len(data.get("qa_list", []))
            gm_count = len(data.get("general_messages", []))
            print(f"  Gemini 回傳：{qa_count} 組 Q&A，{gm_count} 則一般訊息")
        except Exception as e:
            print(f"  ❌ Gemini 呼叫失敗：{e}")
            print("     此批次跳過，斷點維持在目前位置，可重新執行續跑。")
            break

        # 6. 轉換格式並存入 Supabase
        qa_text    = build_qa_text(data)
        end_offset = current_offset + len(raw_rows) - 1
        save_to_supabase(
            batch_num  = batch_num,
            year       = year,
            qa_text    = qa_text,
            data       = data,
            start_row  = current_offset,
            end_row    = end_offset,
            total_msgs = len(filtered),
            raw_rows   = raw_rows,
        )

        # 7. 更新斷點
        current_offset += len(raw_rows)
        save_checkpoint(current_offset)
        print(f"  💾 斷點更新至 offset={current_offset}")
        print()

        batch_num += 1

    print(f"\n{'='*55}")
    print(f"  執行結束  |  最終 offset = {current_offset}")
    print(f"{'='*55}")
    print("\n完成後請到管理介面 → 分析總覽 → 立即補跑解析，更新分類索引。")


# ── 執行 ──────────────────────────────────────────────────────
run()
