# HyRead LINE Q&A Bot 專案

> 最後更新：2026/08/19（抽查確認案號/金額保留正常；補跑8/6~8/19累積463筆新訊息，offset 90595→91058；修正「上次分析時間」顯示慢8小時的UTC bug並已部署上線，待下次新資料寫入時驗證顯示是否正確；備份表 qa_results_backup_0803／qa_items_backup_0803 Stacy決定先保留不刪；修正「整理QA」batch_num bug並新增 `/cron/daily_analysis` 每日自動觸發端點，設定完成後不用再手動跑Colab補資料，待Stacy設定Render環境變數CRON_SECRET＋外部排程服務並完成部署）

---

## 操作手冊

| 檔案 | 位置 | 說明 |
|------|------|------|
| HyRead_QA系統操作手冊.docx | LINE BOT/ 專案資料夾 | 合併版，含客服查詢介面（第一部分）與後台管理（第二部分），v1.0，2026/06 |

### 手冊章節架構

**第一部分：客服查詢介面**
- 二、登入查詢介面（/qa 網址、帳密、登出）
- 三、查詢介面功能說明（頁面佈局、年份篩選、關鍵字搜尋、標籤篩選、瀏覽結果、編輯標籤）

**第二部分：後台管理介面**
- 四、登入後台管理介面（/admin 網址、can_admin 需求）
- 五、後台頁籤功能說明（過濾詞句、分類管理、分析總覽、Token 用量、帳號管理、標籤群組管理）
- 六、LINE Bot 整理 QA 指令（整理QA / 整理QA 20XX）
- 七、常見問題 Q&A
- 八、技術聯絡資訊

> 最後更新：2026/06/12（批次標籤更新背景執行、歷程記錄、webhook 修復、qa.html 標籤刪除 bug 修正）

---

## 服務架構

| 服務 | 用途 | 位址 |
|------|------|------|
| GitHub | 程式碼 | qq336688/hyreadline-webhook |
| Render | 伺服器（Starter 方案，$7/月，0.5 CPU / 512MB RAM） | https://hyreadline-webhook.onrender.com |
| LINE Bot | HyRead客服 | @090tounv |
| Supabase | 資料庫 | ecflimunzbraxxjwtkyz.supabase.co |
| Gemini API | AI 分析 | gemini-2.5-flash（付費 Tier 1，Prepay，project: line project，Key結尾`...k4Bw`）|
| UptimeRobot | 監控服務存活（Starter 方案不會休眠，此設定為舊免費方案時期留存，現已非必要，可保留作為可用性監控） | 每14分鐘 ping /ping |

---

## Gemini API 帳單操作

**帳單頁面**：https://aistudio.google.com/app/billing（專案：line project）

| 操作 | 步驟 |
|------|------|
| 下載帳單（報帳用） | Transactions 區塊 → **View transactions** → 每筆交易右側 ↓ 下載圖示 |
| 修改帳單名稱／地址 | 頁面下方 Settings 區塊 → **Manage settings** |
| 修改付款方式地址 | How you pay 區塊 → **Manage payment methods** |

**付款記錄**：
- 2026/06/07：儲值 NT$500
- 2026/08/03：儲值 NT$500（供「全部89,331筆歷史資料重新分析」使用，重跑途中額度用盡又追加儲值多次，具體金額請以 AI Studio Billing 頁面實際記錄為準）

**Gemini 2.5 Flash 付費定價參考**（來源：https://ai.google.dev/gemini-api/docs/pricing，2026/08 查詢）：輸入 $0.30 / 1M tokens，輸出（含 thinking tokens）$2.50 / 1M tokens。全量重跑實測：每批 50 筆訊息平均花費約 NT$2.2，可用於估算儲值金額（例：剩餘 1,000 批 ≈ NT$2,200）。

**⚠️ 2026/07/02 發現並修正**：Render 環境變數 `GEMINI_API_KEY` 長期誤用**舊帳號「My First Project」**（免費試用、從未設定付款方式）的 Key，跟 2026/06/08 升級的付費 line project 是兩個不同 Google 帳號/Key，導致 LINE Bot「整理QA」指令一直呼叫失敗（429 prepayment credits depleted），Colab 腳本則因手動填入 Key 而正常。已將 Render 的 `GEMINI_API_KEY` 換成 line project 的 Key（結尾 `...k4Bw`），兩邊統一使用同一帳戶。**若之後又遇到 429 錯誤，先確認 Render 環境變數的 Key 結尾是否還是 `...k4Bw`，不要直接假設是餘額問題。**

---

## Render 環境變數

`CHANNEL_ACCESS_TOKEN` / `CHANNEL_SECRET` / `GEMINI_API_KEY` / `SUPABASE_URL` / `SUPABASE_KEY` / `FLASK_SECRET_KEY`

---

## 專案檔案結構

```
hyreadline-webhook/
├── app.py               # Flask 主程式（~1843 行，路由 + API）
├── templates/
│   ├── admin.html       # 管理介面完整 HTML/JS（70KB）
│   └── qa.html          # 查詢介面完整 HTML/JS（42KB，含 Jinja2 變數）
├── Procfile
├── requirements.txt
└── tag_mgr.py
```

### Flask templates 說明
- `admin_page()` → `return render_template('admin.html')`（無動態變數）
- `qa_page()` → `return render_template('qa.html', admin_btn=..., user_label=..., edit_tag_btn=...)`
- qa.html 使用 Jinja2 變數：`{{ admin_btn|safe }}`、`{{ user_label|safe }}`、`{{ edit_tag_btn|safe }}`

---

## Supabase 資料表

| 資料表 | 用途 |
|--------|------|
| messages | LINE 群組原始訊息（**89,331 筆**，2019~2026，2026/06/08 全量清洗完成） |
| settings | 系統設定（last_analyzed_date、colab_offset、**batch_ops_history** 等） |
| qa_results | 每批 Gemini 分析的完整 Q&A 文字 |
| qa_items | 拆分後的獨立 Q&A 條目（供查詢頁面搜尋），含 tags text[] 欄位、hidden boolean 欄位（2026/07/02 新增，隱藏後不會出現在 /qa 查詢結果） |
| token_logs | 每批 Gemini token 使用記錄 |
| filter_words | 使用者自訂過濾詞句 |
| admin_users | 帳號密碼 + 7項後台權限欄位 + last_visit（最近到訪時間）+ visit_count（到訪次數）（同時適用管理介面與查詢介面登入） |
| tag_groups | 標籤群組對應（tag_name → group_name；`__def__:NAME` 列代表空群組定義） |

### qa_items 欄位說明

| 欄位 | 型別 | 說明 |
|------|------|------|
| id | int | 主鍵 |
| batch_id | int | 對應 qa_results.id |
| year | text | 年份（2019~2026） |
| batch_num | int | 批次編號 |
| q_text | text | 問題原文 |
| a_text | text | 回答原文 |
| category | text | 批次層級分類（Gemini 建議，較粗） |
| tags | text[] | 逐題微觀標籤（2~3個，如 ["維修","螢幕損壞","GazeX"]）|
| source_text | text | 原始訊息文字（供關鍵字回溯搜尋，max 10000 字）|
| created_at | text | 建立時間 |
| hidden | boolean | 是否隱藏（預設 false）。true 時 /qa/api/search 一律排除，不會出現在客服查詢頁面；資料仍保留，可在後台「QA 管理」頁籤取消隱藏 |

> `tags` 欄位已於 2026/06/04 新增，GIN 索引已建立。
> `hidden` 欄位需於 Supabase SQL Editor 手動執行以下 SQL 才會生效（2026/07/02 新增功能，尚未執行過此 SQL 前 /admin/api/qa_manage/search 與 /qa/api/search 的 hidden 篩選會報錯）：
> ```sql
> ALTER TABLE qa_items ADD COLUMN IF NOT EXISTS hidden boolean NOT NULL DEFAULT false;
> CREATE INDEX IF NOT EXISTS idx_qa_items_hidden ON qa_items(hidden);
> ```

---

## LINE 指令

| 指令 | 說明 |
|------|------|
| `整理QA 2019` | 自動分批跑完整年，背景執行，完成後通知 |
| `整理QA 20XX` | 同上，依年份替換數字 |
| `整理QA` | 只整理上次之後的新增訊息（50筆） |

> ✅ **`整理QA`（不加年份）batch_num bug 已於 2026/08/19 修正**（見下方「重要限制與解法」），現在可以正常每次抓上次之後的新訊息分析，不會再被誤判重複跳過。累積待處理訊息一次很多（例如超過50筆／隔了好幾天沒整理）時，一次仍只會處理50筆，隔天會繼續處理剩下的，不會遺失；若想一次全部補完也還是可以用 Colab 腳本（見「Colab 腳本說明」）。

---

## 每日自動整理QA（2026/08/19新增，取代手動Colab補跑）

不想每天手動觸發的話，可以設定外部排程服務自動每天呼叫一次新增的端點，讓群組新訊息自動分析，不需要人工介入。

### 設定步驟

1. **Render 環境變數新增兩個**（Render Dashboard → Environment）：
   - `CRON_SECRET`：自己設一組隨機字串（例如用密碼產生器生成），作為觸發端點的驗證密鑰，避免被外部亂打造成不必要的 Gemini 花費
   - `DEFAULT_GROUP_ID`（可選）：填入 Gaze維修客服 LINE 群組的 group_id，設定後每次自動整理完成會像手動打「整理QA」一樣推播完成通知到群組；不填的話就是靜默執行，只能從 `/qa` 頁面或 Render logs 確認有沒有跑
2. **上傳新版 app.py 到 GitHub 並等 Render 部署完成**
3. **手動測試一次**：瀏覽器打開 `https://hyreadline-webhook.onrender.com/cron/daily_analysis?secret=你設定的CRON_SECRET值`，應該會回傳 `{"status":"started"}`，之後去 Render Logs 確認有沒有跑analysis（跟今天在Colab看到的批次訊息格式類似）
4. **設定外部排程服務每天定時觸發**：推薦用 [cron-job.org](https://cron-job.org)（免費），註冊後新增一個 Cronjob，網址填上面測試用的那個網址（含secret），排程時間選妳想要的每天執行時間（例如每天早上6點），存檔啟用即可

### 注意事項

- 每次自動執行最多處理 50 筆新訊息（跟手動「整理QA」相同上限），如果單日訊息量超過50筆，多出來的會留到下一次執行繼續處理，不會遺失
- `CRON_SECRET` 是必要的，沒設定或帶錯密鑰，這個端點會回傳 403 拒絕執行
- 設定完成後，理論上就不再需要手動開 Colab 補跑了；Colab 腳本保留作為「一次性大量補資料」或「這個自動排程萬一故障時」的備用手段

---

## 網頁介面

| 網址 | 說明 |
|------|------|
| `/qa` | Q&A 查詢頁面（需登入，直接查 Supabase） |
| `/qa/login` | 查詢介面登入頁 |
| `/qa/logout` | 查詢介面登出 |
| `/admin` | 管理介面（需登入） |
| `/admin/login` | 管理介面登入頁 |
| `/admin/setup` | 初始建立第一個管理者帳號 |
| `/ping` | Keep-alive 端點 |
| `/cron/daily_analysis?secret=xxx`（2026/08/19新增） | 每日自動整理QA觸發端點，需帶對應 `CRON_SECRET` 環境變數才會執行，設計給外部排程服務（如cron-job.org）每天定時打，取代手動Colab補跑。詳見下方「每日自動整理QA」章節 |

### 管理介面頁籤

- **過濾詞句** — 新增/刪除分析時要過濾的詞句（短句/發話者/關鍵字）
- **分類管理** — 檢視/修改每批 Gemini 建議的問題分類
- **分析總覽** — 歷年 QA 筆數（可更新）、各年度原始訊息量；補跑解析舊資料按鈕
- **Token 用量** — 今日/歷史累積用量、每日長條圖、近期批次記錄
- **帳號管理** — 新增/停用/刪除帳號、修改密碼；7項後台功能細項權限（過濾/分類/總覽/Token/帳號/標籤/群組）
- **標籤群組管理** — 拖曳式標籤分群；改名/合併/刪除群組；tag chip ✕ 刪除；🧹 清除幽靈標籤
  - 子頁籤「🗂️ 標籤群組」：拖曳排序、📤 批次更新（CSV 上傳改名/刪除/群組改名）
  - 子頁籤「📋 批次更新記錄」：每次執行結果（背景執行，顯示 ✅/⚠️/❌ 狀態、成功失敗筆數、時間戳）；保留最近 10 筆，存於 settings.batch_ops_history
- **QA 管理**（2026/07/02 新增）— 搜尋所有 QA（關鍵字/年份/顯示狀態篩選，含已隱藏），逐筆切換「隱藏」/「取消隱藏」；隱藏只設定 qa_items.hidden=true，不刪除資料，隱藏後的 QA 不會出現在 /qa 查詢頁面的搜尋結果中；權限沿用「標籤管理」(perm_tags)，未開啟該權限的帳號看不到此頁籤

### 查詢介面功能（/qa）

- 登入保護（使用 admin_users 同一張表）
- 頂部橫條歷史資料年份快捷列（2019~2026 + 日常新增）
- 左側「標籤篩選」：依群組分頁籤顯示（頁籤列灰底），chip 可多選，底部「清除篩選」
  - 標籤頁籤與首頁頁籤背景色一致（`#e0e0e0`），標籤 chip 依群組分色
  - `/qa/api/tags_with_groups`：分頁抓 qa_items + 分頁抓 tag_groups，正確對應群組
- 搜尋框下方年份勾選列（全選/單選）
- 搜尋為兩段式：先比對 q_text+a_text，無結果才擴大至 source_text
- 編輯標籤模式（✏️ 編輯標籤按鈕，需 perm_tags 權限）：新增/刪除/改名標籤，全部同步寫回 qa_items + tag_groups
  - 新增 → 自動加入 tag_groups（group_name='未分群'，若已存在則跳過）
  - 刪除 → 若全域無其他 QA 使用，自動從 tag_groups 移除
  - 改名（✏️）→ 全域更新所有 QA + tag_groups；若目標名稱已存在則提示合併確認
  - **Bug fix（2026/06/12）**：renderResults 重新渲染時優先用 cardTags[itemId]，防止「結束編輯」時已刪標籤被舊資料覆蓋還原
- 新增標籤 popover 翻轉邏輯（空間不足時向上開）；切換頁籤不關閉（e.stopPropagation）
- 分頁列：上一頁 / 頁碼（最多7個）/ 下一頁
- 每張 QA 卡片右上角顯示淡灰色 ID（如 ID1234）

---

## Q&A 格式

```
Q1：[問題]（YYYY/MM/DD HH:MM 提問者姓名）
A：[回答]（YYYY/MM/DD HH:MM 回答者姓名）；[補充]（時間 姓名）
附檔：[說明] [連結]

---

【一般訊息】
[時間] 發話者：訊息內容
```

---

## 重要限制與解法

| 問題 | 解法 |
|------|------|
| Render 記憶體 512MB | 每批 limit 50 筆 |
| Gemini Prepay 點數耗盡 | 餘額歸零後立即 429，需至 AI Studio Billing 頁面補值 |
| **Gemini 503/429 導致整批分析中斷（已修正 2026/08/04）** | `colab_qa_analysis.py` 原本 `except...break`，遇到 503（伺服器過載）或 429（額度用盡）就整個中斷 while 迴圈，斷點停在原地，需手動重新執行整格才能繼續。已改為 `call_gemini()` 內建指數等待重試（15/30/60/120/240秒，最多5次），主迴圈重試仍失敗才跳過該批、記錄進 `failed_batches`、`continue` 到下一批，不再整個中斷；每批次間固定 `time.sleep(2)` 降低連續觸發過載機率。**風險**：429 額度用盡時重試也無效，會導致後續一大段批次被「跳過」而非真正分析，需搭配下方補洞工具處理 |
| **重跑全部資料中途額度用盡，導致大段批次被跳過** | 用 `colab_backfill_gaps.py`（2026/08/04新增）：先執行 `find_gaps()` 掃描 0~目前斷點間真正沒存到 qa_results 的批次區間（免費，只查 Supabase，不呼叫 Gemini），確認清單無誤、確認額度已恢復後，執行 `backfill_gaps(gaps)` 才會真正呼叫 Gemini 補分析，不會動到主斷點 colab_offset |
| Render 閒置休眠 | UptimeRobot 每14分鐘 ping |
| **每次新建 Supabase 資料表** | 必須執行 RLS 設定（見下方）|
| Gunicorn 逾時 SIGKILL | Procfile 設 `--timeout 300` |
| 批次中斷可續跑 | 記錄已完成批次數，重送指令自動從斷點繼續 |
| Token 超量自動停止 | 每批後查今日累積用量，超過 80萬自動暫停並通知 |
| genai.Client 設 http_options timeout | 會導致 INVALID_ARGUMENT，已移除 |
| Gemini 429 RESOURCE_EXHAUSTED | 補標籤腳本自動等待 60 秒重試 |
| **Chrome 自動填入密碼** | 帳號編輯 modal 密碼欄已加 autocomplete="new-password"；若帳號密碼被覆蓋，需到帳號管理重設密碼 |
| **批次匯入帳號預設 can_admin=False** | 批次帳號只能登入 /qa，需在帳號管理個別開啟後台權限 |
| **批次標籤操作 SIGKILL** | admin_batch_tag_ops 改為背景執行（threading.Thread），立即回傳 job_id，結果存 settings.batch_ops_history |
| **Render 伺服器時間 UTC** | 所有顯示給使用者的時間戳需 +8 小時（`datetime.now() + timedelta(hours=8)`） |
| **後台「分析總覽」→「最後分析紀錄」卡片與 /qa 頁面「系統更新時間」顯示比實際慢8小時（2026/08/05發現，2026/08/19已修正並部署）** | 根因：來源 `analyzed_at`，`colab_qa_analysis.py` 第335行、app.py 第1415/1489/1701行的 `datetime.now().strftime(...)` 都沒加 `timedelta(hours=8)`。**2026/08/19 已修正**：兩個檔案對應位置都改成 `(datetime.now() + timedelta(hours=8)).strftime(...)`（colab_qa_analysis.py 同時在 import 加了 `timedelta`）；app.py 已拖曳上傳 GitHub，Render 已確認部署成功（Dashboard logs 出現「Your service is live」，2026/08/19 12:36）；colab_qa_analysis.py 新版也已同步貼回 Google Drive「2026/8/4重跑全部資料.ipynb」筆記本。**此修正只影響之後新寫入的時間戳，資料庫裡已存在的舊 analyzed_at 不會回頭校正**，所以畫面上還會繼續顯示修正前寫入的舊時間，直到下一次真的有新資料寫入 qa_results 才會顯示正確時間。**⚠️ 下次接手待辦：等下一次補跑QA（Colab或整理QA）產生新資料後，比對畫面顯示時間是否與台灣時間一致，藉此驗證這次修正是否真的生效，驗證前不要視為已完全解決** |
| **settings 表沒有 id 欄位** | 查詢 existence 用 `select('value')` 而非 `select('id')` |
| **fetch_new_messages cursor bug（已修正 2026/07/02）** | 原本抓到新訊息後不論是否全部處理完，`last_analyzed_date` 一律跳到「全部新抓到訊息中最新一筆」的時間；若新訊息超過 limit(50)，超出的部分會被永久跳過、不會再被分析。已修正為只前進到「這次實際回傳/處理的那批」的最後一筆時間 |
| **「整理QA」batch_num 每次從1開始（2026/08/19已修正）** | 原本 `run_analysis` 對於不指定年份的呼叫，`batch_num` 每次都從1重新計算，只要當年度曾成功寫入過一筆 `(year=當年, batch_num=1)`，之後每次「整理QA」都會在 existing 檢查時被判定「已存在」而直接跳過、永遠 0 筆，且不會前進 cursor。**已修正**：無year模式改為先查該年度目前最大 `batch_num`，接續往後編號（不再從1起算），且訊息本身是cursor-based保證不重複，不需要再查重；year模式（`整理QA 20XX`）維持原本以i計算的可續傳邏輯不動，未受影響。一次性大量補資料仍建議用 Colab 腳本，日常新增現在可以放心用 LINE「整理QA」或下方的每日自動排程 |
| **Gemini 呼叫失敗只印 Render log，不通知使用者** | `run_analysis` 內批次失敗只有 `except...continue`，LINE 通知仍顯示「整理完成」但筆數為0；需到 Render Dashboard → Logs 查實際錯誤原因 |
| **Render GEMINI_API_KEY 對應到錯誤 Google 帳號** | 見上方「Gemini API 帳單操作」章節，2026/07/02 已修正為 line project 對應的 Key |
| **tag_groups 含 `__def__:NAME` 空群組定義列** | `run_analysis` 組 tag_hint 時原本沒排除，會把這些假標籤送進 Gemini prompt；已於 2026/07/02 修正，查詢時加上 `not startswith('__def__:')` |
| **「立即補跑解析」按鈕會清空 tags/source_text（高風險，已隱藏）** | `reparse_qa_items` 會刪除全部 qa_items 並用不含 tags/source_text 的舊邏輯重建；現在 `run_analysis`/Colab 都已直接寫入 tags，不需要也不應該再用這個按鈕。2026/07/02 已在 admin.html 加 `display:none` 隱藏 |
| **標籤全域改名撞 tag_groups 唯一鍵（已修正 2026/07/03）** | `qa_rename_tag`／`admin_rename_tag_global` 原本在迴圈更新 `qa_items.tags` 前先查一次「新名稱是否已存在」，但迴圈中途 `qa_items_tags_sync` trigger 會自動把新名稱插入 tag_groups，導致迴圈跑完後用迴圈前的舊判斷做最後一步（UPDATE 改名）時撞到唯一鍵報錯（`duplicate key ... tag_groups_tag_name_key`），且會跳過原本該有的「是否合併」確認流程直接報錯。已修正為迴圈跑完後重新查一次 `exists_after` 再決定刪除或改名 |
| **QA內容被Gemini過度摘要，案號/金額等細節消失（已修正 2026/08/04）** | Gemini prompt 只要求「問題摘要」「回答摘要」，導致案號、金額、產品型號、連結等具體資訊被改寫成籠統句子（例：「維修更換費用為3600元，可折抵檢測費500元」被摘要成「需支付維修費用」），造成用案號等關鍵字在 /qa 搜尋不到（q_text/a_text裡根本沒有這幾個字，只殘留在 source_text）。已於 `colab_qa_analysis.py`（build_prompt）與 `app.py`（_build_prompt）都加入「內容保留規則」，明確列出：案號/工單號/訂單編號、金額費用數字、產品型號、網址連結、具體日期期限、錯誤代碼版本號，六類必須逐字保留原文，並附錯誤vs正確範例對照。**注意：此修正只影響「之後」新整理的QA，舊資料要套用需重新用Gemini分析（見下方現況進度）** |

---

## 標籤資料架構說明

- **`qa_items.tags`**：每筆 QA 實際持有的標籤陣列（真正的資料來源）
- **`tag_groups`**：標籤分組對應表（tag_name → group_name），從 qa_items.tags 衍生，供管理介面分群顯示
- 流程：colab_qa_analysis 生成標籤 → colab_retag_all 覆蓋重打 → colab_init_tag_groups 建立分組
- 後台改名/合併操作會同步更新 qa_items.tags + tag_groups 兩張表
- **潛在問題**：整理QA 產出的新標籤只寫入 qa_items，不自動同步到 tag_groups；可用 Supabase SQL 補插缺漏標籤（見下方 SQL）
- **查補缺漏標籤**：
  ```sql
  INSERT INTO tag_groups (tag_name, group_name)
  SELECT DISTINCT unnest(tags), '未分群'
  FROM qa_items WHERE tags IS NOT NULL AND NOT tags = '{}'
  ON CONFLICT (tag_name) DO NOTHING;
  ```

---

## ⚠️ 新建 Supabase 資料表必做

每次建立新資料表後，**必須**執行以下 SQL 啟用 RLS，否則 Supabase 會發出安全性警告：

```sql
ALTER TABLE 新表名 ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allow_all_authenticated" ON 新表名 FOR ALL USING (true);
```

---

## 訊息過濾規則（分析前自動過濾）

- Bot 自身回覆（HyRead客服）
- 整理QA 指令訊息
- 系統通知（加入群組、離開群組等）
- 純表情符號
- 無意義短句（好、OK、收到、謝謝…）
- 自訂過濾詞（可在 /admin 管理介面新增）

---

## Colab 腳本說明

| 檔案 | 用途 |
|------|------|
| `colab_qa_analysis.py` | 主分析腳本：從 messages 清洗 → Gemini 分析 → 寫入 qa_results + qa_items（含逐題 tags） |
| `colab_backfill_tags.py` | 補標籤腳本：對 qa_items 中 tags IS NULL 或 tags='{}' 的舊資料補打標籤，完全獨立，不需上傳 GitHub（已完成，756 筆） |
| `colab_retag_all.py` | 全量重打標籤腳本 v1：規則式比對（型號/配件/系統/關鍵詞）+ Gemini 補症狀描述，覆蓋所有 qa_items tags（2026/06/08 完成，4838 筆） |
| `6/8Line.ipynb`（Google Drive） | 2026/06/08 新建的 Colab 筆記本，用付費 Gemini API Key 繼續清洗剩餘訊息（**已完成，最終 offset=89282，共 1787 批次**） |
| `colab_backfill_source_text.py` | 回填腳本 v3：對每個 qa_results 批次，從 messages 抓原始訊息存入 qa_items.source_text；主方法=解析 q_text 日期，備用=year+batch_num 估算位置；不呼叫 Gemini，零 API 費用 |
| `colab_backfill_gaps.py`（2026/08/04新增） | 補洞腳本，處理 503/429 造成批次被跳過的情況。**兩階段設計**：① `find_gaps()` 掃描 0~目前斷點間，比對 qa_results 找出真正缺資料的批次區間（會自動排除本來整批被過濾掉、不需要存的批次），完全免費、不呼叫 Gemini；② 確認缺口清單、確認額度已恢復後，手動執行 `backfill_gaps(gaps)` 才真正呼叫付費 Gemini 補分析並存回資料庫，不影響主斷點 colab_offset。需在同一 Colab session、主程式 cell 已執行過（即使被中斷）的前提下，於下方新增儲存格執行 |
| 「補跑最新資料」腳本（2026/07/02，Google Drive，命名如 `7/2跑 6/18 09:00~7/2 14:24.ipynb`） | 基於 colab_qa_analysis.py 改版：BATCH_SIZE=50、標籤清單改為**即時查詢 tag_groups**（排除`__def__:`）而非寫死清單，其餘沿用 colab_offset 斷點續傳。**日常「整理QA」累積較多待處理訊息時的標準做法**，直接重新執行即可自動從斷點繼續，不受 app.py 那套 batch_num 限制影響 |

### Colab 腳本執行參數

- `colab_qa_analysis.py`：BATCH_SIZE = 50（2026/08/04起固定為50，原本500；2026年後訊息過長用500會出錯，全量重跑一律用50較穩定），斷點存於 Supabase settings.colab_offset；2026/08/04已加入「內容保留規則」禁止過度摘要
- `colab_backfill_tags.py`：每批 30 題，thinking_budget=0，depleted 時立即停止，429 時自動等待 60 秒重試，中斷後重跑自動續跑（已完成）
- `colab_retag_all.py`：BATCH_SIZE=30，START_FROM_ID 設定續跑，失敗自動跳過繼續（最多重試 4 次），thinking_budget=0；規則比對不花 API，Gemini 只補症狀描述
- `6/8Line.ipynb`：BATCH_SIZE = 50（2026年資料含超長訊息，不可設 500），thinking_budget=0（關閉思考模式省費用），餘額不足時立即停止不重試；**已完成，最終 offset=89282，共 1787 批次，2026/06/08**
- `colab_backfill_source_text.py`：需先執行 SQL ；主方法解析 q_text 日期區間，備用方法用 year+batch_num 估算；batch window=200 則訊息；source_text 上限 10000 字

### tags 標籤規則（2026/06/08 新版，colab_retag_all.py）

**規則式比對（不花 API）：**
- 裝置型號：Note Plus CC / Note Plus C / Note Plus / Pro Note C / Pro Note / Pro XC / Pro X / Mini+ 6 / Mini+ / Mini CC / Mini C / Mini / One SC / One S / X Plus / X / Pocket / 7.8吋 / Note
- 配件類型：保護殼、保護套、螢幕貼、觸控筆、磁吸筆、筆芯、傳輸線、充電器、支架、磁吸筆套、SIM卡夾、帆布袋、玩偶吊飾、矽膠杯蓋
- 系統版本：Android 6/8/11/14 等（regex 自動抓數字）、iOS
- 固定關鍵詞：開放式、封閉式、APP、閱讀器、書櫃、個人藏書、載具、線上瀏覽、忘記密碼、破屏、線條、出線

**Gemini 補充：** 規則未涵蓋的症狀描述（1~2 個，如：螢幕無反應、借閱失敗、寄修流程）

---

## 現況進度

- ✅ 所有服務建立完成
- ✅ 歷史對話 89,331 筆已匯入 Supabase（最終 offset=89282，共 1787 批次）
- ✅ 自動分批背景處理（每批50筆）
- ✅ 斷點續傳（中斷後重送指令自動續跑）
- ✅ Token 用量監控與自動暫停
- ✅ 查詢網頁（登入保護、直接搜尋 Supabase）
- ✅ 管理介面（登入保護、6個頁籤）
- ✅ Supabase RLS 安全設定（messages、settings，2026/05/21）
- ✅ 查詢介面改版：左側年份瀏覽、搜尋框下方年份勾選（2026/06/02）
- ✅ 查詢介面分頁功能（每頁50筆）（2026/06/04）
- ✅ qa_items 新增 tags text[] 欄位 + GIN 索引（2026/06/04）
- ✅ colab_qa_analysis.py 升級：逐題產出 tags（2026/06/04）
- ✅ Gemini API 升級為付費 Tier 1（Prepay，project: line project，2026/06/08）
- ✅ Colab 全量清洗完成（2026/06/08，最終 offset=89282，共 1787 批次，89,331 筆訊息）
- ✅ colab_retag_all.py 全量重打標籤完成（2026/06/08，4838 筆，規則比對 + Gemini 症狀描述）
- ✅ tag_groups 表建立 + 群組管理 API（2026/06/09）
- ✅ 查詢介面改版：頂部年份橫條、左欄標籤依群組分色、兩段式搜尋（2026/06/09）
- ✅ colab_init_tag_groups.py 執行完成（2026/06/09，共寫入 4591 筆 tag_groups）
- ✅ colab_backfill_source_text.py v5 執行完成（2026/06/09，共更新 4838 筆，100% 回填完成）
- ✅ 帳號管理 7 項細項權限（perm_filter/category/stats/token/users/tags/groups）（2026/06/10）
- ✅ 分析總覽：新增「歷年 QA 筆數」card，含更新按鈕與長條圖（2026/06/10）
- ✅ 標籤群組管理：拖曳排序、tag chip ✕ 刪除、幽靈清除（2026/06/10~12）
- ✅ 查詢介面：編輯標籤 popover 搜尋框、popover 切換頁籤不關閉（2026/06/11~12）
- ✅ 管理介面 topbar 顯示登入者名稱（2026/06/12）
- ✅ 修正 showDeleteConfirmModal SyntaxError（\' → \\' in triple-quoted string）（2026/06/12）
- ✅ **架構重構：HTML/JS 分離為 Flask templates**（2026/06/12）
  - admin_page() → render_template('admin.html')
  - qa_page() → render_template('qa.html', ...)
  - app.py 從 3003 行縮減至 1309 行
  - 永久解決 Python triple-quoted string 跳脫衝突問題
- ✅ **Webhook 修復 + FileMessage 支援**（2026/06/12）
  - /webhook 路由在架構重構時遺失，已補回
  - 新增 handle_file 處理 LINE 傳送的附件（存 file_url + file_type）
  - 補匯 2026/06/04~06/11 遺失訊息 259 筆（SQL 匯入）
- ✅ **批次標籤更新功能**（2026/06/12）
  - 標籤群組管理新增「📤 批次更新」：匯出 CSV → Excel 填寫 → 上傳執行
  - 支援標籤改名、合併、刪除、群組改名
  - 背景執行（threading.Thread），不會 SIGKILL
  - 「📋 批次更新記錄」子頁籤顯示歷次執行結果
- ✅ **qa.html 標籤刪除 bug 修正**（2026/06/12）
  - 點「結束編輯」時 renderResults 重新渲染會用舊資料覆蓋已刪標籤
  - 修正：優先用 cardTags[itemId] 而非 _lastSearchResult
- ✅ **admin.html 群組名稱換行顯示**（2026/06/17）
  - 群組名稱過長被截斷（text-overflow:ellipsis），改為 overflow-wrap:break-word 自動換行
- ✅ **admin.html 群組拖曳失效 bug 修正**（2026/06/17）
  - 拖過標籤 chip 後 dragState 未清除，導致群組拖曳被 if(dragState.tag)return 永久擋住
  - 修正：chip dragend 加上 dragState={}
- ✅ **qa.html 歷史資料年份按鈕失效 bug 修正**（2026/06/17）
  - browseYearBar 傳 null 給 browseYear，el.classList.add 報錯導致 _doSearch 無法執行
  - 修正：加 if(el) 判斷
- ✅ **qa.html 分頁列顯示頁碼從 7 個擴展為最多 20 個**（2026/06/17）
- ✅ **帳號管理新增最近到訪時間與到訪次數統計**（2026/06/18）
  - admin_users 新增 last_visit（text）、visit_count（integer）欄位
  - admin_login / qa_login 登入成功時自動更新這兩個欄位
  - 帳號管理表格新增「最近到訪」「到訪次數」兩欄顯示
- ✅ **批次更新標籤新增 G 欄「移至群組」**（2026/06/18）
  - 原 F 欄「群組更名」影響整個群組下所有標籤
  - 新 G 欄「移至群組」只移動單一標籤到指定群組（對應後端已有的 tag_ops.new_group）
  - 欄位說明加入 A～G 欄位字母標示
  - 整理QA 的 tag_vocab 上限從 80 提升至 1500（清洗後標籤約 1500 個）
- ✅ **qa.html 移除「日常新增」年份按鈕**（2026/06/18）
- ✅ **Supabase trigger：qa_items 新標籤自動同步 tag_groups**（2026/06/18）
  - 建立 sync_tags_to_groups() function + qa_items_tags_sync trigger
  - 每次寫入 qa_items.tags，新標籤自動加入 tag_groups（group_name='未分群'）
- ✅ **colab_qa_analysis.py 加入 TAG_VOCAB 標籤詞彙表**（2026/06/18）
  - 244 個既有標籤列為優先選用清單，Gemini 優先從中選標籤，不符合才新增
- ✅ **分析總覽新增「最後分析紀錄」card**（2026/06/18）
  - 顯示 QA 總筆數、上次新增 QA 筆數、上次處理訊息數、上次分析時間
  - 新增 /admin/api/last_run_info API
- ✅ **查詢介面「直接搜尋資料庫」改為「系統更新時間」**（2026/06/18）
  - qa_page() 新增 last_updated 變數（抓 qa_results 最新 analyzed_at）
- ✅ **管理介面隱藏「分類管理」頁籤**（2026/06/18）
  - 批次分類與標籤系統無關，避免混淆，改為 display:none 隱藏
- ✅ **補跑解析說明文字更新**（2026/06/18）
  - 說明 Colab 跑 QA 不需要補跑解析，只有 LINE Bot 整理QA 後才需要
- ✅ **app.py：修正 `fetch_new_messages` cursor bug**（2026/07/02）
  - 原本抓到新訊息就把 `last_analyzed_date` 跳到全部新訊息中最新一筆，超過50筆的部分會被永久跳過
  - 修正為只前進到「這次實際處理那批」的最後一筆時間
- ✅ **app.py：`run_analysis` 排除 `__def__:` 假標籤**（2026/07/02）
  - tag_hint 查詢 tag_groups 時加上排除空群組定義列的條件，避免混入 Gemini 提示詞
- ✅ **admin.html：隱藏「立即補跑解析」按鈕**（2026/07/02）
  - 該功能會清空 qa_items 並用不含 tags/source_text 的舊邏輯重建，現行流程已不需要，改 `display:none` 隱藏避免誤按
- ✅ **qa.html：移除無效的「日常」年份勾選框**（2026/07/02）
  - qa_items.year 從未有「日常」這個值，勾選框對查詢結果無實際作用，已移除
- ⚠️ **發現並修正：Render `GEMINI_API_KEY` 誤用免費舊帳號**（2026/07/02）
  - 長期指向「My First Project」（從未設定付款方式），跟06/08升級的付費 line project 是不同帳號
  - 已更新 Render 環境變數為 line project 的 Key（結尾`...k4Bw`）
- ⚠️ **發現：「整理QA」batch_num 固定從1開始的設計缺陷（未修正）**
  - 當年度第一次成功執行後，之後每次都會判定「批次已存在」而跳過、永遠0筆，且不會前進 cursor
  - 暫時對策：大量/多日累積的補資料一律改用 Colab 腳本執行，不使用 LINE「整理QA」；日常僅新增少量（如當天幾則）時風險較低
- ✅ **Colab 補跑 2026/06/18 09:37 ~ 2026/07/02 資料**（2026/07/02）
  - 用改版 colab_qa_analysis.py（BATCH_SIZE=50、標籤即時查詢 tag_groups）從 offset=89282 續跑至 89900，新增 20 筆 QA（批次1795~1798）
  - 完成後手動同步 `settings.last_analyzed_date` = messages 最新時間（2026/07/02 05:35），避免後續「整理QA」與 Colab 進度重疊或衝突
- ✅ **新增後台「QA 管理」隱藏功能**（2026/07/02）
  - 需求：客服在 /qa 查詢時發現內部行政訊息被誤判進 QA（如「請問今天是否有安排會議」），需要能把不適合的 QA 從前台隱藏
  - qa_items 新增 `hidden` boolean 欄位（預設 false，需先在 Supabase 執行 SQL，見上方「qa_items 欄位說明」）
  - app.py 新增 `/admin/api/qa_manage/search`（關鍵字/年份/顯示狀態篩選 + 分頁）與 `/admin/api/qa_manage/toggle`（切換單筆 hidden）
  - `/qa/api/search` 的 build_query 加上 `hidden=false` 過濾，前台查詢一律排除已隱藏 QA
  - admin.html 新增「🙈 QA 管理」頁籤，權限沿用 perm_tags；隱藏為軟刪除（只改欄位，不刪資料），可隨時取消隱藏
  - 順手修正 admin.html 既有 bug：`/admin/api/me` 權限隱藏頁籤邏輯中 `document.querySelector('.tab[data-tab=+map[k]+]')` 字串串接錯誤（缺引號），導致此邏輯从未真正生效，已修正為正確的字串樣板
- ✅ **QA 管理搜尋改為兩段式（修正「開會」等常見詞搜到不相關結果）**（2026/07/02）
  - 問題：`/admin/api/qa_manage/search` 原本一次比對 q_text+a_text+source_text 三欄位；source_text 是該筆QA前後約200則原始訊息（最多10000字），常見詞很容易命中 source_text 卻跟畫面顯示的問答內容無關，導致搜「開會」跑出一堆看起來不相關的QA
  - 修正為跟前台 `/qa` 查詢一致的兩段式邏輯：先只比對 q_text+a_text，完全零筆才擴大到 source_text；回傳新增 `source_text_fallback` 欄位，admin.html 命中 source_text 時會在結果訊息多顯示提示文字
  - ⚠️ **意外發現：本機 app.py 檔案曾損毀**：驗證時發現本機 `LINE BOT/app.py` 在 `_build_qa_text` 函式處被截斷，`run_analysis`／`fetch_new_messages`／`webhook`／`app.run()` 等後半段程式碼全部消失（推測是先前某次工具編輯遺留的截斷問題，非本次改動造成）。已請使用者從 GitHub 重新下載完整版 app.py，在完整版上重新套用兩段式搜尋修正後覆蓋回本機，原損毀檔案備份為 `app.py.corrupted_backup`。**提醒：本機檔案不一定跟 GitHub/Render 上線版本同步，之後編輯 app.py 前建議先確認檔案完整性（含 `if __name__` 與 `app.run(`）**
- ✅ **修正標籤全域改名撞 tag_groups 唯一鍵**（2026/07/03）
  - 起因：後台「標籤群組管理」把某標籤全域改名為「mini CC螢幕霧感」時，跳出 `duplicate key value violates unique constraint "tag_groups_tag_name_key"` 錯誤
  - 根因：`qa_rename_tag`（/qa/api/rename_tag）與 `admin_rename_tag_global`（/admin/api/tags/rename_global）都在迴圈更新 qa_items.tags 前先查一次 tag_groups 是否已有新名稱；但迴圈中途 06/18 新增的 `qa_items_tags_sync` trigger 會自動把新名稱插入 tag_groups，導致迴圈跑完後用「迴圈前」的舊判斷執行最後一步的 UPDATE，撞到唯一鍵，且完全跳過原本該有的「是否合併」確認視窗
  - 修正：兩個函式都改成迴圈跑完後重新查一次 `exists_after`，再決定要刪除舊名稱（合併）還是把舊名稱改成新名稱
  - ⚠️ **意外發現：本機 app.py 二度損毀**：修復前檢查發現本機 app.py（含備份檔 `app.py.corrupted_backup`）都停在第 1816 行、卡在 `_build_prompt()` 多行字串中間，代表 07/02 那次「復原」並未真的把完整檔案存回本機。嘗試用 `web_fetch` 直接抓 GitHub raw 版本核對，但該工具對這個檔案大小（~80KB）有固定截斷上限，兩次抓取都卡在同一位置，無法取得完整內容。最後請使用者直接把本機完整的 app.py 當附件上傳，驗證 `ast.parse` 通過且結尾有 `if __name__`／`app.run(` 後，才在上面套用改名 bug 修正並覆蓋回本機（詳見下方「檔案編輯規則」）
- ✅ **修正 QA 內容被 Gemini 過度摘要問題**（2026/08/04）
  - 起因：客服反映在 LINE 群組看到的完整訊息（如維修報價含案號 #N07247、金額細節），在 /qa 查詢卻找不到；查 Supabase 確認原始訊息確實在 messages 表，也確實被整理進 qa_items（Q11），但 Gemini 把內容改寫摘要過，案號、金額被替換成籠統句子（如「維修更換費用為3600元，可折抵檢測費500元」被摘要成「需支付維修費用」）
  - 修正：`colab_qa_analysis.py`（build_prompt）與 `app.py`（_build_prompt）都加入「內容保留規則」，明確要求案號/工單號/訂單編號、金額費用數字、產品型號、網址連結、具體日期期限、錯誤代碼版本號六類逐字保留，並附錯誤vs正確範例對照
  - 順手將 `colab_qa_analysis.py` 的 BATCH_SIZE 從 500 固定改為 50（2026年後長訊息用500會出錯）
  - **此修正只影響「之後」新整理的QA，舊資料需重新分析才會套用**（見下方重新分析進度）
- ⚠️ **app.py 第三次出現「編輯未真正存檔」問題，症狀與前兩次截斷不同**（2026/08/04）
  - 這次不是截斷損毀：Edit 工具回報修改成功、Read 工具重新讀取也確認內容已更新，但使用者在 Windows 檔案總管看到的 app.py 修改日期仍停留在舊時間戳（前一天），代表工具回報的「成功」跟磁碟實際狀態不一致
  - 對同一段內容重新執行一次 Edit 後，檔案總管的修改日期才跳到當下時間，確認真正寫入成功
  - **教訓：之後編輯 app.py，光靠 Read 工具讀回內容確認不夠可靠（可能是快取），務必額外請使用者到檔案總管核對「修改日期」是否變成當下時間，才能確定真的存檔成功**；bash 對這個資料夾的掛載也曾發現是舊快照（看到的內容/時間戳跟實際不同步），同樣不能用來驗證，一律以使用者檔案總管畫面為準
- 🔄 **啟動「全部89,331筆歷史資料用新prompt重新分析」**（2026/08/04，進行中，尚未完成）
  - 目的：讓舊資料也套用上述內容保留規則，找回被過度摘要掉的案號/金額等細節
  - 執行前備份：`CREATE TABLE qa_results_backup_0803 AS SELECT * FROM qa_results` / `qa_items_backup_0803` 同樣方式，已驗證備份筆數與原表一致（402/402、4913/4913）
  - 執行前記錄目前被隱藏的4筆QA：id 40, 935, 4480, 4585（皆為「開會」相關內部訊息誤判進QA），供重跑完成後手動重新隱藏
  - 已執行：`TRUNCATE TABLE qa_items;` `TRUNCATE TABLE qa_results;` `UPDATE settings SET value='0' WHERE key='colab_offset';`
  - Gemini帳戶（line project，Key結尾`...k4Bw`）餘額加值至 NT$698（原NT$198+儲值500），估計此次重跑花費 NT$100~300
  - 執行方式：Colab 筆記本「2026/8/4重跑全部資料.ipynb」，貼入最新版 `colab_qa_analysis.py`（BATCH_SIZE=50），過程中偶爾遇到503（Gemini伺服器暫時過載）屬正常現象，重新執行同一儲存格會自動從斷點續跑，不影響已扣款項
  - **執行中發現：503 過載會讓整個迴圈直接中斷（2026/08/04）**：原始版本遇到 503/429 是 `except...break`，整個 while 迴圈直接停止，斷點不動但要手動重新執行整格才能繼續，導致「跑沒幾分鐘就停掉」。已修正 `colab_qa_analysis.py`：`call_gemini()` 內建指數等待重試（15/30/60/120/240秒，最多5次），主迴圈重試仍失敗才跳過該批並記錄、`continue` 到下一批，不再整個中斷；每批次間固定暫停2秒降低連續過載機率
  - **執行中發現：Gemini 帳戶額度多次用盡，造成一大段批次被跳過（2026/08/04）**：429「Your prepayment credits are depleted」，重試也無效，會讓後面所有批次都被判定失敗、offset 一路跳過到底，等於整段資料沒被分析卻顯示「執行結束」。已於當次追加儲值恢復，並新增補洞腳本 `colab_backfill_gaps.py`（見上方「Colab 腳本說明」）——已成功用於補回 offset 20100~21049、45500~46149 這兩段共 16 個被跳過的批次，補跑後全部成功
  - 目前進度：斷點 offset ≈ 46350（總計 89,331 筆，約過半），持續往後跑中；Gemini 帳戶（line project）為儲值制，額度用盡需至 AI Studio Billing 頁面加值才能恢復（定價與單批成本估算見上方「Gemini API 帳單操作」章節）
  - **2026/08/05 即時查詢確認最新進度**：直接查 Supabase 得到 `colab_offset = 88250`、`messages` 總筆數 = **90,595**（比 08/04 記錄的 89,331 多了 1,264 筆，因為這幾天群組持續有新對話進來）、`messages` 最新一筆時間為 2026/08/05 08:43。
    - 按筆數算進度 88,250 / 90,595 ≈ 97.4%，剩餘 2,345 筆未跑
    - 但用 `SELECT created_at FROM messages ORDER BY id ASC LIMIT 1 OFFSET 88249;` 查斷點那一筆訊息的實際時間，結果是 **2026/05/19 09:15** —— 代表重跑進度目前只推進到 2026/05/19，**還沒有跑到當天（8/5）的對話**，因為近期訊息量比早年密集，剩下 2.4% 的筆數其實橫跨 05/19～08/05 這兩個半月
    - 之後要確認是否追上「今天」，可重跑同一組 SQL（`colab_offset` 值 + `ORDER BY id ASC LIMIT 1 OFFSET <colab_offset-1>` 查對應時間），不用等 Colab 完全跑完才知道進度
  - **2026/08/05 全部重跑 + 補洞已完成**：主程式跑到最終 offset=90595、全程無批次失敗；接著執行 `colab_backfill_gaps.py`，`find_gaps()` 掃出 14 個缺口批次（offset 57050~82849 之間，額度用盡期間跳過的），執行 `backfill_gaps(gaps)` 後「✅ 全部缺口補跑成功！」。這次「全部89,331→90,595筆歷史資料重新分析」正式完成。
  - **完成後待辦進度**：
    1. ✅ 已執行 `UPDATE settings SET value = (SELECT MAX(created_at) FROM messages) WHERE key = 'last_analyzed_date';`
    2. ✅ 已回後台「QA 管理」重新隱藏開會相關內部訊息。**注意**：原記錄的 id 40/935/4480/4585 是舊表（重跑前）的編號，`TRUNCATE` 後新表 id 全部重新編號對不上，後台搜尋框查的是內容不是ID，所以改用 `SELECT id,q_text,a_text FROM qa_items_backup_0803 WHERE id IN (40,935,4480,4585);` 查出舊內容關鍵字，再拿關鍵字去後台搜尋比對後手動隱藏
    3. ✅ **2026/08/19 抽查確認**：關鍵字「維修費」搜尋 /qa，Q1（#7102）、Q2（#7101）案號與金額（原廠報價6000元、折後5400元）皆完整保留在 q_text/a_text，內容保留規則確認生效
    4. ⏸️ **Stacy 2026/08/19 決定**：先不刪 `qa_results_backup_0803`／`qa_items_backup_0803` 備份表，留著當保險，沒有急迫性。之後要刪的話：`DROP TABLE IF EXISTS qa_results_backup_0803; DROP TABLE IF EXISTS qa_items_backup_0803;`
    5. 🔄 **修正「上次分析時間」顯示慢8小時的問題，2026/08/19已動手**（見上方「重要限制與解法」表格條目）——程式碼已修正並部署上線（Render確認「Your service is live」），Colab筆記本也已同步新版，但**尚未驗證修正是否真的生效**：因為此修正只影響之後新寫入的資料，畫面上顯示的舊時間戳要等下一次真的有新資料寫入 qa_results 才會反映修正結果。下次接手記得：等下一次補跑後，比對畫面顯示時間跟實際台灣時間是否一致，才能真正關閉這個項目
  - **2026/08/05 意外發現並修正：標籤群組出現「案號誤植為標籤」的垃圾標籤**：後台「標籤群組管理」顯示「未分群」高達4,026筆（tag_groups共4,280筆），懷疑是 Gemini 把訊息裡的案號/工單號（如 #101、#1334）誤當成該題的 tags 產生，而非真正分類標籤。實際查證：未分群4,026筆中，符合 `^#[0-9]+$`（純#+數字）格式的只有84筆（約2%，其餘3,942筆是這次重跑產生的大量具體新標籤，只是還沒人工歸類，非垃圾資料，不影響查詢功能）。受影響 QA 筆數89筆（佔全部6,489筆QA的1.4%）。**已清理完成**：
    ```sql
    UPDATE qa_items SET tags = ARRAY(SELECT t FROM unnest(tags) t WHERE t !~ '^#[0-9]+$')
    WHERE EXISTS (SELECT 1 FROM unnest(tags) t WHERE t ~ '^#[0-9]+$');
    DELETE FROM tag_groups WHERE tag_name ~ '^#[0-9]+$';
    ```
    執行後驗證：垃圾標籤數與受影響QA筆數都已歸零。**如果之後又發生同樣情況**：優先檢查 `colab_qa_analysis.py` 的 tags 生成規則有沒有把「案號逐字保留」的規則跟「tags 標籤規則」搞混（案號應該留在 q_text/a_text 裡，不該進 tags 陣列），目前 prompt 沒有明確禁止把案號當標籤，可考慮之後在 tags 規則加一條「禁止使用案號/工單號/純數字編號作為標籤」。
- ✅ **2026/08/19 補跑 8/6~8/19 累積新訊息**：大重跑同步斷點後（`colab_offset=90595`），沒有人手動觸發後續分析，累積13天新訊息未整理。診斷方式：比對 `settings.last_analyzed_date`（2026/08/06 06:25）與 `SELECT MAX(created_at) FROM messages`（2026/08/19 03:23）確認落差。**改用 Colab 筆記本「2026/8/4重跑全部資料.ipynb」主程式cell單獨執行**（不用「全部執行」，該筆記本混有8/4~8/5 gap-filling用的舊儲存格，全部執行會連舊cell一起跑出 `NameError: get_checkpoint not defined`；也不用LINE「整理QA」，2026年度已跑過會被batch_num判定重複跳過0筆）。**執行結果：offset 90595 → 91058，共補上 463 筆新訊息（批次1812~1822，11個批次），全程無批次失敗**。完成後手動執行 `UPDATE settings SET value = (SELECT MAX(created_at) FROM messages) WHERE key = 'last_analyzed_date';` 同步顯示時間。Gemini帳戶（line project）餘額當時為NT$347，這次花費遠低於此，餘額足夠。
- ✅ **2026/08/19 修正「上次分析時間」顯示慢8小時的UTC bug並部署上線**：詳見上方「重要限制與解法」表格條目。app.py三處＋colab_qa_analysis.py一處都加上 `+timedelta(hours=8)`，已上傳GitHub、Render確認部署成功、Colab筆記本也已同步新版。**驗證待下次新資料寫入時進行**（此修正不會回頭校正已存在的舊時間戳）。

---

## 各年資料整理流程

1. LINE Bot 發 `整理QA 20XX`
2. 等背景跑完收到通知（每天最多跑 20 批 / 1,000 筆，超過隔天早上 8 點後繼續）
3. 管理介面「分析總覽」→「立即補跑解析」
4. 確認「已重新解析 X 批次」= 已整理批次數
5. 繼續下一年

---

## ⚠️ 檔案編輯規則

### app.py（~1843 行，路由 + API 邏輯）

> ⚠️ **曾發生三次本機檔案異常，症狀不完全相同**：
> - **2026/07/02**：本機 app.py 被截斷損毀，`_build_qa_text` 之後、`run_analysis`／`fetch_new_messages`／`webhook`／`app.run()` 整段消失，且截斷後 Python 執行仍可能不報錯，難以察覺。當時靠使用者從 GitHub 重新下載完整版才復原，本機檔案曾備份為 `app.py.corrupted_backup`。
> - **2026/07/03（二度發生）**：修復隔天再次檢查，發現本機 app.py（連同 `app.py.corrupted_backup`）都停在第 1816 行、卡在 `_build_prompt()` 函式的多行字串中間，代表上次「復原」流程沒有真的把完整檔案寫回本機。這次改用 GitHub raw 網址直接抓取比對，但受限於本環境 `web_fetch` 工具對大檔案有固定截斷上限（兩次抓取都在同一位置卡住，字元數/行數完全一致），無法取得完整內容，最後改請使用者直接把本機完整的 app.py 當附件上傳，讀取確認 `ast.parse` 通過、結尾有 `if __name__`／`app.run(` 後才繼續編輯。
> - **2026/08/04（三度發生，症狀不同——不是截斷，是編輯沒真的寫入）**：這次 Edit 工具回報「修改成功」、Read 工具重新讀取也顯示內容已更新，但使用者在 Windows 檔案總管看到的 app.py 修改日期仍停留在前一天，代表工具回報的成功跟磁碟實際狀態不一致；同時發現 bash 對這個資料夾的掛載也是舊快照（顯示的內容/修改時間跟實際不同步，甚至一度顯示跟已知截斷版本一樣的檔案大小），不能拿來驗證。對同一段內容重新執行一次 Edit 後，檔案總管修改日期才跳到當下，確認真正寫入成功。
> **提醒**：`web_fetch` 對這個約 80KB 大小的 app.py 會固定截斷，之後若要用 GitHub 版本核對/復原，**不要依賴 web_fetch，直接請使用者上傳檔案或用瀏覽器下載後貼上**。**Read 工具讀回內容顯示「已更新」不代表真的存檔成功**（可能是快取），編輯完 app.py 後除了下方語法檢查，務必額外請使用者到檔案總管核對「修改日期」是否變成當下時間，這是目前唯一可靠的驗證方式。每次編輯前也要重新做下方完整性檢查，即使上次才剛確認過。

**每次編輯 app.py 前，先確認檔案沒有已經損毀：**

```bash
python3 -c "import ast; ast.parse(open('app.py',encoding='utf-8').read()); print('syntax OK')"
grep -c "if __name__\|app.run(" app.py   # 應該 >=1，沒有代表檔案已被截斷，不要在壞檔案上繼續改
```

app.py 目前已移除所有 HTML，只剩 API 路由，可直接用 Read + Edit 工具修改小範圍內容。
**超過 100 行或有多行字串／跳脫符號的修改，一律禁止用 `python3 -c "..."` 單行指令替換**（指令過長會被 shell 截斷，且截斷後仍回傳 OK，是造成上述損毀事件的可疑原因），改用暫存 .py 檔：

```bash
# 標準流程（用暫存檔，不要用 python3 -c 單行指令）
cat > /tmp/fix.py << 'EOF'
data = open('app.py','r',encoding='utf-8').read()
old = """...原始內容..."""
new = """...新內容..."""
assert old in data, 'not found'
data = data.replace(old, new, 1)
open('app.py','w',encoding='utf-8').write(data)
print('OK, lines:', data.count('\n'))
EOF
python3 /tmp/fix.py
python3 -c "import ast; ast.parse(open('app.py','r',encoding='utf-8').read()); print('syntax OK')"
grep -c "if __name__\|app.run(" app.py   # 修改後再確認一次結尾還在
grep -n "函式名稱或路由" app.py
```

若用 Edit 工具直接修改時遇到 `EPERM: rename ... .tmp... -> app.py`（Windows 檔案鎖定），不要一直重試，改用上面的暫存 .py 檔方式寫到新檔案（如 `app_fixed.py`），驗證通過後再覆蓋回 app.py。

### templates/admin.html 與 templates/qa.html（前端 HTML/JS）

這兩個是標準 HTML 檔案，**不在 Python 字串內**，JS 可直接用標準語法：
- `\n`、`\'`、`﻿` 等跳脫序列直接寫，無需雙反斜線
- 修改後用 `node --check` 驗證 JS 語法

> ⚠️ **曾發生**：bash Python 替換 admin.html 後檔案被截斷（結尾變成 `/`），導致 `showTab is not defined`，整個後台介面失效。

**每次修改 HTML 模板後，必須執行以下三項驗證，缺一不可：**

```bash
# 1. 確認行數沒有變少（記住修改前的行數）
wc -l templates/admin.html

# 2. 確認結尾是 </script>
tail -3 templates/admin.html

# 3. 驗證 HTML 內的 JS 語法
python3 -c "
import re, subprocess, tempfile, os
text = open('templates/admin.html', encoding='utf-8').read()
for js in re.findall(r'<script[^>]*>(.*?)</script>', text, re.DOTALL):
    tmp = tempfile.NamedTemporaryFile(suffix='.js', mode='w', encoding='utf-8', delete=False)
    tmp.write(js); tmp.close()
    r = subprocess.run(['node','--check',tmp.name], capture_output=True, text=True)
    print('OK' if r.returncode==0 else r.stderr[:200])
    os.unlink(tmp.name)
"
```

---

## ⚠️ GitHub 上傳規則

- **app.py**：Add file → Upload files 拖曳上傳（不可用網頁編輯器，150KB 以上會截斷）
- **templates/ 修改**：先在 GitHub 瀏覽到 `templates/` 資料夾，再 Add file → Upload files；或直接訪問 `github.com/qq336688/hyreadline-webhook/upload/main/templates`
- 上傳後確認 commit 時間戳更新為「just now」
- Render 自動部署約需 3~5 分鐘，完成後看 Dashboard logs 出現「Your service is live」
