"""
HyRead 維修記錄管理系統 - Flask + Supabase 後端
版本：v1.0（對應雛型 v7）
"""

import os
import bcrypt
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, render_template, session
from supabase_client import create_client, SupabaseHTTP as Client
from dotenv import load_dotenv

load_dotenv()

# ── App 設定 ─────────────────────────────────────────────
app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-change-me')
app.permanent_session_lifetime = timedelta(hours=24)

# ── Supabase 客戶端 ───────────────────────────────────────
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_SECRET_KEY', '')
sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================================================
# 工具函式
# ============================================================
def now_str():
    return datetime.utcnow().isoformat()

def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def check_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False

def next_serial(key: str, prefix: str, digits: int) -> str:
    """從 system_config 取得下一個流水號並更新"""
    res = sb.table('system_config').select('value').eq('key', key).single().execute()
    current = res.data[0]['value']       # e.g. "N00001"
    num     = int(current[len(prefix):]) # 取數字部分
    new_val = f"{prefix}{str(num + 1).zfill(digits)}"
    sb.table('system_config').update({'value': new_val}).eq('key', key).execute()
    return current

# ============================================================
# 權限裝飾器
# ============================================================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': '請先登入'}), 401
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': '請先登入'}), 401
        if not session.get('is_admin'):
            return jsonify({'error': '權限不足'}), 403
        return f(*args, **kwargs)
    return decorated

def check_module(module_key):
    """檢查當前使用者是否有模組存取權"""
    perms = session.get('permissions', {})
    return perms.get(module_key, False)

# ============================================================
# 頁面路由
# ============================================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'version': '1.0'})

# ============================================================
# 登入 / 登出 / 目前使用者
# ============================================================
@app.route('/api/login', methods=['POST'])
def login():
    data     = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if not username or not password:
        return jsonify({'error': '請填寫帳號與密碼'}), 400

    # 先查使用者
    res = sb.table('users').select(
        'id, username, display_name, password_hash, is_active, group_id'
    ).eq('username', username).execute()

    if not res.data:
        return jsonify({'error': '帳號或密碼錯誤'}), 401

    user = res.data[0]

    if not user['is_active']:
        return jsonify({'error': '帳號已停用，請聯繫管理員'}), 403
    if not check_password(password, user['password_hash']):
        return jsonify({'error': '帳號或密碼錯誤'}), 401

    # 更新最後登入時間
    sb.table('users').update({'last_login': now_str()}).eq('id', user['id']).execute()

    # 另外查權限群組
    grp = {}
    is_admin = False
    perms = {}
    if user.get('group_id'):
        grp_res = sb.table('permission_groups').select('*').eq('id', user['group_id']).execute()
        if grp_res.data:
            grp = grp_res.data[0]
            perms = {k: v for k, v in grp.items() if k.startswith('mod_')}
            is_admin = (grp.get('name') == '系統管理員')

    session.permanent = True
    session['user_id']      = user['id']
    session['username']     = user['username']
    session['display_name'] = user['display_name'] or user['username']
    session['group_id']     = user['group_id']
    session['permissions']  = perms
    session['is_admin']     = is_admin

    return jsonify({
        'id':           user['id'],
        'username':     user['username'],
        'display_name': user['display_name'],
        'permissions':  perms,
        'is_admin':     is_admin,
    })

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/me')
@login_required
def me():
    return jsonify({
        'id':           session['user_id'],
        'username':     session['username'],
        'display_name': session['display_name'],
        'permissions':  session.get('permissions', {}),
        'is_admin':     session.get('is_admin', False),
    })

# ============================================================
# 維修記錄（主模組）
# ============================================================
# ── 欄位對應表（範本欄名 → Supabase 欄位）──────────────────────
REPAIR_IMPORT_COLS = {
    '舊維修編號':     'old_repair_no',
    '富動編號':       'product_number',       # 原「富動/配件編號」
    '阿偉編號':       'awei_number',
    '填表人':         'form_filler',
    '資料來源':       'data_source',
    '填單日期':       'fill_date',
    '維修類型':       'repair_type',
    '型號':           'model',
    'SN碼':           'serial_no',
    '客戶姓名':       'customer_name',
    '帳號':           'customer_account',
    '電話1':          'customer_phone1',
    '電話2':          'customer_phone2',
    '信箱':           'customer_email',
    '地址':           'customer_address',
    '展碁備註':       'ebook_note',
    '展碁通路':       'ebook_channel',
    '福利品':         'is_welfare',
    '發票號碼':       'invoice_no',
    '發票日期':       'invoice_date',
    '歷次維修編號':   'prev_repair_nos',
    '收件包裹':       'received_package',
    '收回日期':       'received_date',
    '原商品出貨日期': 'original_ship_date',
    '訂單資訊':       'order_info',
    '客戶問題備註':   'customer_issue',
    '換機換貨SN':     'exchange_sn',
    '付款單號1':      'payment_no1',
    '付款金額1':      'payment_amount1',
    '付款單號2':      'payment_no2',
    '付款金額2':      'payment_amount2',
    '付款單號備註':   'payment_note',
    '其他備註':       'other_notes',
    '保固與否':       'warranty',
    '故障大項':       'fault_category',
    '故障細項':       'fault_detail',
    '破屏/線條':      'screen_damage',
    '實測故障':       'actual_fault',
    '配件':           '__accessories__',      # 特殊處理：逗號分隔 → list
    '更換零件':       'replaced_parts',
    '更換零件記錄':   '__parts_checklist__',  # 特殊處理：逗號分隔名稱 → JSON
    '維修紀錄':       'repair_record',
    '檢測費':         'inspection_fee',
    '維修費':         'repair_fee',
    '維修員':         'technician',
    '維修日期':       'repair_date',
    '換下壞品':       'bad_part_removed',
    '維修備註':       'repair_notes',
    '帳單系統':       'billing_system',
    '付款總額':       'total_payment',
    '細項統計':       'detail_stats',
    '年度統計':       'annual_stats',
    '委外廠商':       'outsource_vendor',
    '委外請款月份':   'outsource_month',
    '委外金額':       'outsource_amount',
    '進度狀態':       'progress_status',
    '結案方式':       'close_method',
}

# 更換零件記錄：中文名稱 → parts_checklist 欄位名稱對照
PARTS_NAME_MAP = {
    '未更換零件': 'no_part_replace',   '換機': 'machine_exchange',
    '更換屏幕': 'replace_screen',      '更換主板': 'replace_mainboard',
    '更換電池': 'replace_battery',     '更換SD卡座': 'replace_sd_slot',
    '更換天線': 'replace_antenna',     '更換背殼': 'replace_back_cover',
    '更換副板': 'replace_sub_board',   '更換喇叭': 'replace_speaker',
    '更換主板小板排線接副板FPC': 'replace_fpc',
    '更換電源線': 'replace_power_cable','更換電源鍵': 'replace_power_button',
    '更換電源排線': 'replace_power_ribbon','更換螺絲': 'replace_screw',
    '更換SIM卡座': 'replace_sim_tray', '更換側邊FPC': 'replace_side_fpc',
}

@app.route('/api/repair/template')
@login_required
def repair_template():
    """下載維修記錄批次匯入範本"""
    import io
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font, Alignment
    from flask import send_file
    wb = Workbook()
    ws = wb.active
    ws.title = '維修記錄範本'
    required = {'填表人','資料來源','填單日期','維修類型','型號','SN碼','進度狀態'}
    headers = list(REPAIR_IMPORT_COLS.keys())
    yellow = PatternFill('solid', fgColor='FFFF00')
    green  = PatternFill('solid', fgColor='C6EFCE')
    bold   = Font(bold=True)
    ws.append(headers)
    for i, h in enumerate(headers, 1):
        cell = ws.cell(1, i)
        cell.font = bold
        cell.alignment = Alignment(horizontal='center', wrap_text=True)
        cell.fill = yellow if h in required else green
    # 說明列（順序對應 REPAIR_IMPORT_COLS）
    # 舊維修編號,富動編號,阿偉編號,填表人,資料來源,填單日期,維修類型,型號,SN碼,
    # 客戶姓名,帳號,電話1,電話2,信箱,地址,展碁備註,展碁通路,福利品,發票號碼,發票日期,
    # 歷次維修編號,收件包裹,收回日期,原商品出貨日期,訂單資訊,客戶問題備註,
    # 換機換貨SN,付款單號1,付款金額1,付款單號2,付款金額2,付款單號備註,其他備註,
    # 保固與否,故障大項,故障細項,破屏/線條,實測故障,配件,更換零件,更換零件記錄,維修紀錄,
    # 檢測費,維修費,維修員,維修日期,換下壞品,維修備註,帳單系統,付款總額,
    # 細項統計,年度統計,委外廠商,委外請款月份,委外金額,進度狀態,結案方式
    notes = [
        '原系統序號','','',
        '*必填','*必填','*必填 YYYY-MM-DD','*必填','*必填','*必填',
        '','','','','','',
        '','','是/否','','YYYY-MM-DD',
        '','','YYYY-MM-DD','文字（可填日期）','','',
        '','','數字','','數字','','',
        '保固內/保固外','','','有/無','',
        '逗號分隔多項','','逗號分隔中文名','',
        '數字','數字','','YYYY-MM-DD','','',
        '','數字',
        '見下方選項','','','YYYY-MM','數字',
        '見下方選項','見下方選項'
    ]
    ws.append(notes)
    ws.cell(2,1).font = Font(italic=True, color='808080')
    # 範例
    ws.append([
        '1001','','',
        'Stacy','電話','2026-05-17','保固維修','ebook 7','SN123456',
        '王小明','hyread001','0912345678','','user@email.com','台北市中正區',
        '','博客來','否','','',
        '','原廠紙箱','2026-05-18','2025-01-01','','螢幕破損',
        '','','','','','','',
        '保固內','螢幕','破屏','有','螢幕破裂',
        '配件A,配件B','','更換屏幕','更換螢幕完成',
        '0','0','阿偉','2026-05-19','','',
        '','0',
        '','','','','0',
        '已收貨，資料登錄中',''
    ])
    # 選項說明
    ws.append([])
    ws.append(['【進度狀態選項】'])
    for s in ['待收貨，客服建單中','已收貨，資料登錄中','維修，評估檢測中','已結案']:
        ws.append(['', s])
    ws.append(['【結案方式選項（進度狀態=已結案時必填）】'])
    for s in ['原機寄還','原機寄還(已親取)','換機(來回件)','換機(舊換新)',
              '換機(已親取)','換機','配件補寄','已入庫','放棄閱讀器(不寄回)','手動結案','其他']:
        ws.append(['', s])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name='維修記錄匯入範本.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/api/repair/batch-import', methods=['POST'])
@login_required
def batch_import_repair():
    """批次匯入維修記錄（對應範本欄位）"""
    if 'file' not in request.files:
        return jsonify({'error': '請上傳檔案'}), 400
    file = request.files['file']
    try:
        import openpyxl
        wb = openpyxl.load_workbook(file, data_only=True)
        ws = wb.active
        headers = [str(c.value or '').strip() for c in next(ws.iter_rows(min_row=1, max_row=1))]
        # 舊欄名相容對照（舊名 → 新名）
        LEGACY_HEADER_MAP = {'保固': '保固與否', '破屏線條': '破屏/線條'}
        # 找出哪些欄有對應
        col_idx = {}
        for i, h in enumerate(headers):
            h = LEGACY_HEADER_MAP.get(h, h)   # 舊名自動轉新名
            if h in REPAIR_IMPORT_COLS:
                col_idx[REPAIR_IMPORT_COLS[h]] = i
        if 'serial_no' not in col_idx and 'form_filler' not in col_idx:
            return jsonify({'error': '找不到必要欄位，請使用範本格式'}), 400

        # 取得已存在的舊維修編號（避免重複）
        existing_res = sb.table('repair_records').select('old_repair_no').execute()
        existing_old = {r['old_repair_no'] for r in (existing_res.data or []) if r.get('old_repair_no')}

        imported = skipped = 0
        errors = []
        pending = []  # 待 INSERT 的 (old_no, rec) 清單
        date_fields    = {'fill_date','invoice_date','received_date','repair_date'}  # original_ship_date 已改為文字型，不做日期轉換
        numeric_fields = {'inspection_fee','payment_amount1','payment_amount2',
                          'total_payment','outsource_amount'}  # repair_fee 已改文字型，不做數字轉換
        bool_fields    = {'is_welfare'}
        # 跳過說明列的關鍵字
        SKIP_HINTS = {'*必填','必填','YYYY','說明','請勿','欄位'}

        for row in ws.iter_rows(min_row=2, values_only=True):  # 第1行標題，第2行起為資料或說明列
            if all((v is None or str(v).strip() == '') for v in row):
                continue
            # 跳過說明列（第一個值含說明關鍵字）
            first_val = str(row[0] or '').strip()
            if any(h in first_val for h in SKIP_HINTS):
                continue

            rec = {}
            for field, idx in col_idx.items():
                val = row[idx] if idx < len(row) else None
                s   = str(val).strip() if val is not None else ''
                if not s:
                    continue
                # ── 特殊欄位：配件（逗號分隔 → list）──────────────
                if field == '__accessories__':
                    rec['accessories'] = [v.strip() for v in s.split(',') if v.strip()]
                    continue
                # ── 特殊欄位：更換零件記錄（逗號分隔名稱 → JSON）──
                if field == '__parts_checklist__':
                    names = [v.strip() for v in s.split(',') if v.strip()]
                    rec['parts_checklist'] = {PARTS_NAME_MAP[n]: True for n in names if n in PARTS_NAME_MAP}
                    continue
                if field in date_fields:
                    parsed = _parse_date(val)
                    if parsed:
                        rec[field] = parsed
                elif field in numeric_fields:
                    try:
                        rec[field] = float(s.replace(',', ''))
                    except ValueError:
                        pass  # 非數字就略過
                elif field in bool_fields:
                    rec[field] = s in ('是', 'Y', 'y', 'true', 'True', '1', 'yes')
                else:
                    rec[field] = s

            # 跳過重複
            old_no = rec.get('old_repair_no', '')
            if old_no and old_no in existing_old:
                skipped += 1
                continue

            rec['created_by']      = session['user_id']
            rec['updated_by']      = session['user_id']
            rec['created_by_name'] = session.get('display_name', session.get('username', ''))
            rec['updated_by_name'] = session.get('display_name', session.get('username', ''))
            rec.setdefault('progress_status', '待收貨，客服建單中')
            pending.append((old_no, rec))

        # ── 一次讀流水號，本地端連續編號，最後一次更新（避免 N×2 次 DB 呼叫超時）──
        sn_res = sb.table('system_config').select('value').eq('key', 'repair_next_no').execute()
        sn_str = (sn_res.data or [{}])[0].get('value', 'N00001')
        sn_num = int(sn_str[1:])   # 去掉 'N' 前綴取數字

        for old_no, rec in pending:
            rec['repair_no'] = f"N{str(sn_num).zfill(5)}"
            sn_num += 1

        # 更新流水號（一次）
        sb.table('system_config').update({'value': f"N{str(sn_num).zfill(5)}"}).eq('key', 'repair_next_no').execute()

        # ── 批次 INSERT（每批 80 筆）──────────────────────────────────
        # PGRST102 修復：同批次所有物件必須有相同的 keys，先收集全部欄位再補 None
        all_keys = set()
        for _, rec in pending:
            all_keys.update(rec.keys())

        def normalize_batch(buf):
            """補齊缺少的 key 為 None，確保同批次 keys 一致"""
            batch_keys = set()
            for r in buf:
                batch_keys.update(r.keys())
            for r in buf:
                for k in batch_keys:
                    r.setdefault(k, None)
            return buf

        BATCH_SIZE = 80
        batch_buf = []
        for old_no, rec in pending:
            batch_buf.append(rec)
            if len(batch_buf) >= BATCH_SIZE:
                try:
                    sb.table('repair_records').insert(normalize_batch(batch_buf)).execute()
                    imported += len(batch_buf)
                    for r in batch_buf:
                        ono = r.get('old_repair_no','')
                        if ono: existing_old.add(ono)
                except Exception as e:
                    errors.append(f"批次錯誤（{len(batch_buf)} 筆）：{str(e)[:80]}")
                batch_buf = []
        # 最後一批
        if batch_buf:
            try:
                sb.table('repair_records').insert(normalize_batch(batch_buf)).execute()
                imported += len(batch_buf)
            except Exception as e:
                errors.append(f"批次錯誤（{len(batch_buf)} 筆）：{str(e)[:80]}")

        return jsonify({'imported': imported, 'skipped': skipped, 'errors': errors[:10],
                        'col_count': len(col_idx), 'matched_cols': list(col_idx.keys())[:10]})
    except Exception as e:
        return jsonify({'error': f'處理失敗：{str(e)}'}), 500

@app.route('/api/repair/records')
@login_required
def list_repair_records():
    p        = request.args
    page     = max(1, int(p.get('page', 1)))
    per_page = min(200, max(10, int(p.get('per_page', 20))))
    offset   = (page - 1) * per_page

    q = sb.table('repair_records').select('*', count='exact')

    # 關鍵字搜尋
    search = p.get('q', '').strip()
    if search:
        q = q.or_(
            f"repair_no.ilike.%{search}%,"
            f"customer_name.ilike.%{search}%,"
            f"serial_no.ilike.%{search}%,"
            f"customer_phone1.ilike.%{search}%,"
            f"customer_phone2.ilike.%{search}%,"
            f"customer_email.ilike.%{search}%,"
            f"other_notes.ilike.%{search}%,"
            f"old_repair_no.ilike.%{search}%"
        )

    # 篩選條件
    for field in ['progress_status', 'repair_type', 'model', 'form_filler',
                  'data_source', 'warranty', 'fault_category', 'technician',
                  'outsource_vendor', 'close_method']:
        v = p.get(field, '').strip()
        if v:
            q = q.eq(field, v)

    # 日期區間
    if p.get('fill_date_from'):
        q = q.gte('fill_date', p['fill_date_from'])
    if p.get('fill_date_to'):
        q = q.lte('fill_date', p['fill_date_to'])
    if p.get('repair_date_from'):
        q = q.gte('repair_date', p['repair_date_from'])
    if p.get('repair_date_to'):
        q = q.lte('repair_date', p['repair_date_to'])

    # 排序與分頁
    sort_by  = p.get('sort', 'id')
    sort_asc = p.get('dir', 'desc').lower() == 'asc'
    q = q.order(sort_by, desc=not sort_asc).range(offset, offset + per_page - 1)

    res = q.execute()
    total = res.count or 0

    return jsonify({
        'total':    total,
        'page':     page,
        'per_page': per_page,
        'pages':    max(1, (total + per_page - 1) // per_page),
        'records':  res.data or [],
    })

@app.route('/api/repair/export')
@login_required
def export_repair_records():
    """匯出維修記錄為 Excel"""
    import io
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font, Alignment
    from flask import send_file

    p = request.args
    q = sb.table('repair_records').select('*')
    search = p.get('q', '').strip()
    if search:
        q = q.or_(f"repair_no.ilike.%{search}%,customer_name.ilike.%{search}%,serial_no.ilike.%{search}%")
    for field in ['progress_status', 'repair_type', 'model', 'form_filler', 'warranty']:
        v = p.get(field, '').strip()
        if v:
            q = q.eq(field, v)
    res = q.order('id', desc=True).limit(5000).execute()
    records = res.data or []

    wb = Workbook()
    ws = wb.active
    ws.title = '維修記錄'
    headers = [
        '新維修編號','舊維修編號','富動編號','阿偉編號','填表人','資料來源','填單日期','維修類型','型號','SN碼',
        '客戶姓名','帳號','電話1','電話2','信箱','地址',
        '展碁備註','展碁通路','福利品','發票號碼','發票日期',
        '訂單資訊','收件包裹','收回日期','客戶問題備註',
        '換機換貨SN','付款單號1','付款金額1','付款單號2','付款金額2','付款單號備註','其他備註',
        '配件',
        '保固與否','故障大項','故障細項','破屏/線條','實測故障','更換零件','更換零件記錄','維修紀錄',
        '檢測費','維修費','維修員','維修日期','維修備註',
        '帳單系統','付款總額','細項統計','年度統計','委外廠商','委外請款月份','委外金額',
        '進度狀態','結案方式'
    ]
    field_map = [
        'repair_no','old_repair_no','product_number','awei_number','form_filler','data_source','fill_date','repair_type','model','serial_no',
        'customer_name','customer_account','customer_phone1','customer_phone2','customer_email','customer_address',
        'ebook_note','ebook_channel','is_welfare','invoice_no','invoice_date',
        'order_info','received_package','received_date','customer_issue',
        'exchange_sn','payment_no1','payment_amount1','payment_no2','payment_amount2','payment_note','other_notes',
        'accessories',
        'warranty','fault_category','fault_detail','screen_damage','actual_fault','replaced_parts','parts_checklist','repair_record',
        'inspection_fee','repair_fee','technician','repair_date','repair_notes',
        'billing_system','total_payment','detail_stats','annual_stats','outsource_vendor','outsource_month','outsource_amount',
        'progress_status','close_method'
    ]
    # 標題列
    header_fill = PatternFill('solid', fgColor='1A5276')
    header_font = Font(bold=True, color='FFFFFF')
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
    # 更換零件記錄反查表（field key → 中文名稱）
    PARTS_KEY_TO_NAME = {v: k for k, v in PARTS_NAME_MAP.items()}
    # 資料列
    for r in records:
        row = []
        for f in field_map:
            v = r.get(f, '') or ''
            # 配件 list → 逗號字串
            if f == 'accessories' and isinstance(v, list):
                v = ','.join(v)
            # 更換零件記錄 dict → 逗號分隔中文名稱
            elif f == 'parts_checklist':
                if isinstance(v, dict):
                    v = ','.join(PARTS_KEY_TO_NAME.get(k, k) for k, val in v.items() if val)
                else:
                    v = ''
            row.append(str(v))
        ws.append(row)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name='維修記錄.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/api/repair/records/<int:rid>')
@login_required
def get_repair_record(rid):
    res = sb.table('repair_records').select('*').eq('id', rid).single().execute()
    if not res.data:
        return jsonify({'error': '找不到記錄'}), 404
    return jsonify(res.data)

# ── repair_records 允許欄位白名單（過濾前端送來的未知欄位，避免 Supabase 400）──
REPAIR_VALID_COLS = {
    # 識別 / 流水號
    'repair_no', 'old_repair_no',
    # 基本資訊
    'product_number', 'awei_number', 'form_filler', 'data_source', 'fill_date',
    'repair_type', 'model', 'serial_no', 'order_info',
    # 展碁 / 發票
    'ebook_note', 'ebook_channel', 'is_welfare', 'invoice_no', 'invoice_date',
    'original_ship_date', 'prev_repair_nos',
    # 客戶
    'customer_name', 'customer_account', 'customer_phone1', 'customer_phone2',
    'customer_email', 'customer_address',
    # 收件 / 客訴
    'received_package', 'received_date', 'customer_issue',
    # 故障
    'fault_category', 'fault_detail', 'screen_damage', 'actual_fault',
    'warranty',
    # 維修
    'replaced_parts', 'parts_checklist', 'repair_record', 'accessories',
    'inspection_fee', 'repair_fee', 'technician', 'repair_date',
    'bad_part_removed', 'repair_notes',
    # 付款 / 結案
    'exchange_sn', 'payment_no1', 'payment_amount1', 'payment_no2', 'payment_amount2',
    'payment_note', 'total_payment', 'billing_system',
    'return_time', 'close_method', 'close_notes', 'other_notes',
    # 統計
    'detail_stats', 'annual_stats',
    # 委外
    'outsource_vendor', 'outsource_month', 'outsource_amount',
    # 進度
    'progress_status',
    # 系統欄位
    'created_by', 'updated_by', 'created_by_name', 'updated_by_name',
}

def _filter_repair_data(data: dict) -> dict:
    """僅保留白名單欄位，防止 Supabase PGRST204/400 未知欄位錯誤"""
    return {k: v for k, v in data.items() if k in REPAIR_VALID_COLS}

@app.route('/api/repair/records', methods=['POST'])
@login_required
def create_repair_record():
    data = request.json or {}
    try:
        # 自動產生新維修編號
        repair_no = next_serial('repair_next_no', 'N', 5)
        data['repair_no']        = repair_no
        data['created_by']       = session['user_id']
        data['updated_by']       = session['user_id']
        data['created_by_name']  = session.get('display_name', session.get('username', ''))
        data['updated_by_name']  = session.get('display_name', session.get('username', ''))
        data.pop('id', None)
        clean = _filter_repair_data(data)
        res = sb.table('repair_records').insert(clean).execute()
        if res.data:
            return jsonify({'id': res.data[0]['id'], 'repair_no': repair_no, 'ok': True}), 201
        return jsonify({'error': '建立失敗（無回傳資料）'}), 500
    except Exception as e:
        return jsonify({'error': f'建立失敗：{str(e)[:300]}'}), 500

@app.route('/api/repair/records/<int:rid>', methods=['PUT'])
@login_required
def update_repair_record(rid):
    data = request.json or {}
    try:
        data['updated_by']       = session['user_id']
        data['updated_by_name']  = session.get('display_name', session.get('username', ''))
        data.pop('id', None)
        data.pop('repair_no', None)     # 不允許修改編號
        data.pop('created_by', None)
        data.pop('created_by_name', None)
        data.pop('created_at', None)
        clean = _filter_repair_data(data)
        sb.table('repair_records').update(clean).eq('id', rid).execute()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': f'更新失敗：{str(e)[:300]}'}), 500

@app.route('/api/repair/records/<int:rid>', methods=['DELETE'])
@admin_required
def delete_repair_record(rid):
    sb.table('repair_records').delete().eq('id', rid).execute()
    return jsonify({'ok': True})

@app.route('/api/repair/check-sn')
@login_required
def check_duplicate_sn():
    """即時檢查 SN 碼是否重複"""
    sn  = request.args.get('sn', '').strip()
    rid = request.args.get('exclude_id', None)
    if not sn:
        return jsonify({'duplicates': []})
    q = sb.table('repair_records').select('id, repair_no, customer_name, model').eq('serial_no', sn)
    if rid:
        q = q.neq('id', int(rid))
    res = q.execute()
    return jsonify({'duplicates': res.data or []})

# ============================================================
# 儀表板統計
# ============================================================
@app.route('/api/dashboard/stats')
@login_required
def dashboard_stats():
    # 總數
    total_res = sb.table('repair_records').select('id', count='exact').execute()
    total = total_res.count or 0

    # 各進度狀態數量
    status_res = sb.rpc('count_by_field', {'tbl': 'repair_records', 'col': 'progress_status'}).execute()

    # 年度分佈（取 fill_date 年份）
    year_res = sb.rpc('repair_by_year').execute()

    # 型號 Top 10
    model_res = sb.table('repair_records').select('model').execute()
    model_counts = {}
    for r in (model_res.data or []):
        m = r.get('model') or '未填'
        model_counts[m] = model_counts.get(m, 0) + 1
    model_top = sorted(model_counts.items(), key=lambda x: -x[1])[:10]

    # 月份趨勢（近 12 個月）
    month_res = sb.rpc('repair_by_month').execute()

    # 委外追蹤進行中
    tracking_res = sb.table('repair_tracking').select('id', count='exact').is_('repair_complete_cs', 'null').execute()
    tracking_count = tracking_res.count or 0

    # 換貨待確認（return_received = X）
    exchange_res = sb.table('exchange_orders').select('id', count='exact').eq('return_received', 'X').execute()
    exchange_pending = exchange_res.count or 0

    return jsonify({
        'total':           total,
        'tracking_active': tracking_count,
        'exchange_pending': exchange_pending,
        'by_model':        [{'label': k, 'cnt': v} for k, v in model_top],
        'by_year':         year_res.data or [],
        'by_month':        month_res.data or [],
    })

# ============================================================
# 維修追蹤模組
# ============================================================
@app.route('/api/tracking/records')
@login_required
def list_tracking():
    """進行中（交給客服日期為空）"""
    q = sb.table('repair_tracking').select('*').is_('repair_complete_cs', 'null')

    search = request.args.get('q', '').strip()
    if search:
        q = q.or_(
            f"repair_no.ilike.%{search}%,"
            f"model.ilike.%{search}%,"
            f"awei_no.ilike.%{search}%,"
            f"notes.ilike.%{search}%"
        )

    q = q.order('created_at', desc=True)
    res = q.execute()
    return jsonify(res.data or [])

@app.route('/api/tracking/history')
@login_required
def list_tracking_history():
    """歷史追蹤（交給客服日期有值），唯讀"""
    q = sb.table('repair_tracking').select('*').not_.is_('repair_complete_cs', 'null')
    q = q.order('repair_complete_cs', desc=True)
    res = q.execute()
    return jsonify(res.data or [])

TRK_DATE_COLS = {
    'inspection_fee_received',   # 唯一保留日期型的欄位
}

def _clean_tracking(data: dict) -> dict:
    """空字串欄位處理：
    - 日期欄位（inspection_fee_received）空字串轉 None
    - repair_complete_cs 空字串轉 None（歷史追蹤依此欄是否為 NULL 判斷進行中/歷史）
    """
    for col in TRK_DATE_COLS:
        if col in data and (data[col] == '' or data[col] is None):
            data[col] = None
    # 交給客服欄位：空字串轉 None，確保歷史追蹤篩選正確
    if 'repair_complete_cs' in data and (data['repair_complete_cs'] == '' or data['repair_complete_cs'] is None):
        data['repair_complete_cs'] = None
    return data

@app.route('/api/tracking/records', methods=['POST'])
@login_required
def create_tracking():
    data = request.json or {}
    # 自動產生阿偉編號
    awei_no = next_serial('awei_next_no', 'A', 4)
    data['awei_no']          = awei_no
    data['created_by']       = session['user_id']
    data['created_by_name']  = session.get('display_name', session.get('username', ''))
    data['updated_by_name']  = session.get('display_name', session.get('username', ''))

    # 自動帶入機型（依維修編號）
    repair_no = data.get('repair_no', '')
    if repair_no and not data.get('model'):
        rr = sb.table('repair_records').select('model').or_(
            f"repair_no.eq.{repair_no},old_repair_no.eq.{repair_no}"
        ).limit(1).execute()
        if rr.data:
            data['model'] = rr.data[0].get('model', '')

    data.pop('id', None)
    _clean_tracking(data)
    res = sb.table('repair_tracking').insert(data).execute()
    if res.data:
        return jsonify({'id': res.data[0]['id'], 'awei_no': awei_no, 'ok': True}), 201
    return jsonify({'error': '建立失敗'}), 500

@app.route('/api/tracking/records/<int:rid>', methods=['PUT'])
@login_required
def update_tracking(rid):
    data = request.json or {}
    data['updated_by_name'] = session.get('display_name', session.get('username', ''))
    data.pop('id', None)
    data.pop('awei_no', None)       # 不允許修改阿偉編號
    data.pop('created_by', None)
    data.pop('created_by_name', None)
    data.pop('created_at', None)
    _clean_tracking(data)
    sb.table('repair_tracking').update(data).eq('id', rid).execute()
    return jsonify({'ok': True})

@app.route('/api/tracking/template')
@login_required
def tracking_template():
    """下載維修追蹤匯入範本"""
    import io
    from openpyxl import Workbook
    from flask import send_file
    wb = Workbook()
    ws = wb.active
    ws.title = '維修追蹤範本'
    headers = ['維修編號','型號','阿偉編號','已收檢測費',
               '已給初檢','已寄委外','故障料件','實測故障',
               '已通知客服報價','已開付款網址','已報價客人','已收維修費',
               '已通知委外','交給客服','備註']
    ws.append(headers)
    ws.append(['N00001','ebook 7','A2001','2026-05-01',
               '2026-05-02','2026-05-03','螢幕','破屏',
               '','','','','','','測試資料'])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name='維修追蹤匯入範本.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/api/tracking/import', methods=['POST'])
@login_required
def import_tracking():
    """批次匯入維修追蹤 xlsx"""
    if 'file' not in request.files:
        return jsonify({'error': '請上傳檔案'}), 400
    file = request.files['file']
    try:
        rows, skipped, errors = _process_tracking_xlsx(file)
        return jsonify({'imported': rows, 'skipped': skipped, 'errors': errors})
    except Exception as e:
        return jsonify({'error': f'處理失敗：{str(e)}'}), 500

# ============================================================
# 客服換貨模組
# ============================================================
@app.route('/api/exchange/orders')
@login_required
def list_exchange():
    p        = request.args
    page     = max(1, int(p.get('page', 1)))
    per_page = min(200, max(10, int(p.get('per_page', 20))))
    offset   = (page - 1) * per_page

    q = sb.table('exchange_orders').select('*', count='exact')

    search = p.get('q', '').strip()
    if search:
        q = q.or_(
            f"exchange_no.ilike.%{search}%,"
            f"repair_no.ilike.%{search}%,"
            f"customer_contact.ilike.%{search}%,"
            f"order_info.ilike.%{search}%,"
            f"original_sn.ilike.%{search}%,"
            f"item.ilike.%{search}%,"
            f"cs_staff.ilike.%{search}%"
        )

    if p.get('return_received'):
        q = q.eq('return_received', p['return_received'])
    if p.get('fill_date_from'):
        q = q.gte('fill_date', p['fill_date_from'])
    if p.get('fill_date_to'):
        q = q.lte('fill_date', p['fill_date_to'])

    q = q.order('id', desc=True).range(offset, offset + per_page - 1)
    res = q.execute()
    total = res.count or 0

    return jsonify({
        'total': total, 'page': page, 'per_page': per_page,
        'pages': max(1, (total + per_page - 1) // per_page),
        'records': res.data or [],
    })

@app.route('/api/repair/lookup')
@login_required
def repair_lookup():
    """依維修編號查詢機型（供維修追蹤自動帶入）"""
    repair_no = request.args.get('repair_no', '').strip()
    if not repair_no:
        return jsonify({'error': '請輸入維修編號'}), 400
    res = sb.table('repair_records').select('repair_no, model').or_(
        f"repair_no.eq.{repair_no},old_repair_no.eq.{repair_no}"
    ).limit(1).execute()
    if not res.data:
        return jsonify({'error': '找不到維修編號'}), 404
    return jsonify(res.data[0])

@app.route('/api/exchange/lookup')
@login_required
def exchange_lookup():
    """依維修編號（新/舊皆可）帶入客戶資料"""
    repair_no = request.args.get('repair_no', '').strip()
    if not repair_no:
        return jsonify({'error': '請輸入維修編號'}), 400
    res = sb.table('repair_records').select(
        'repair_no, serial_no, customer_name, customer_issue, '
        'customer_phone1, customer_address, is_welfare, other_notes'
    ).or_(
        f"repair_no.eq.{repair_no},"
        f"old_repair_no.eq.{repair_no}"
    ).limit(1).execute()
    if not res.data:
        return jsonify({'error': '找不到維修編號'}), 404
    r = res.data[0]
    return jsonify({
        'repair_no':        r.get('repair_no', '') or '',
        'serial_no':        r.get('serial_no', '') or '',
        'customer_name':    r.get('customer_name', '') or '',
        'customer_issue':   r.get('customer_issue', '') or '',
        'customer_phone1':  r.get('customer_phone1', '') or '',
        'customer_address': r.get('customer_address', '') or '',
        'is_welfare':       bool(r.get('is_welfare', False)),
        'other_notes':      r.get('other_notes', '') or '',
    })

@app.route('/api/exchange/orders', methods=['POST'])
@login_required
def create_exchange():
    data = request.json or {}
    exchange_no = next_serial('exchange_next_no', 'C', 4)
    data['exchange_no']      = exchange_no
    data['created_by']       = session['user_id']
    data['updated_by']       = session['user_id']
    data['created_by_name']  = session.get('display_name', session.get('username', ''))
    data['updated_by_name']  = session.get('display_name', session.get('username', ''))
    data.pop('id', None)
    res = sb.table('exchange_orders').insert(data).execute()
    if res.data:
        return jsonify({'id': res.data[0]['id'], 'exchange_no': exchange_no, 'ok': True}), 201
    return jsonify({'error': '建立失敗'}), 500

@app.route('/api/exchange/orders/<int:oid>', methods=['PUT'])
@login_required
def update_exchange(oid):
    data = request.json or {}
    data['updated_by']       = session['user_id']
    data['updated_by_name']  = session.get('display_name', session.get('username', ''))
    data.pop('id', None)
    data.pop('exchange_no', None)   # 不允許修改編號
    data.pop('created_by', None)
    data.pop('created_by_name', None)
    data.pop('created_at', None)
    sb.table('exchange_orders').update(data).eq('id', oid).execute()
    return jsonify({'ok': True})

@app.route('/api/exchange/orders/<int:oid>', methods=['DELETE'])
@admin_required
def delete_exchange(oid):
    sb.table('exchange_orders').delete().eq('id', oid).execute()
    return jsonify({'ok': True})

@app.route('/api/exchange/template')
@login_required
def exchange_template():
    """下載客服換貨批次匯入範本"""
    import io
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font, Alignment
    from flask import send_file
    wb = Workbook()
    ws = wb.active
    ws.title = '客服換貨範本'
    headers = [
        '換貨編號(客服)', '填表日期(客服)', '客服人員', '維修編號(客服)',
        '品項(客服)', '訂單資訊(客服)', '訂購人-客戶問題描述', '訂購人-電話-收件地址',
        '福利品(客服)', '原SN', '出貨方式', '客服寄出備註',
        '是否拆封', '是否拆封備註', '預計出貨日期(客服)',
        '出貨人員(客服)', '出貨系統處理', '出貨收回', '收回狀態', '出貨備註(家羽)'
    ]
    required = {'換貨編號(客服)'}
    yellow = PatternFill('solid', fgColor='FFFF00')
    green  = PatternFill('solid', fgColor='C6EFCE')
    bold   = Font(bold=True)
    ws.append(headers)
    for i, h in enumerate(headers, 1):
        cell = ws.cell(1, i)
        cell.font = bold
        cell.alignment = Alignment(horizontal='center', wrap_text=True)
        cell.fill = yellow if h in required else green
    # 說明列
    notes = [
        '*必填，如 C1001', 'YYYY-MM-DD', '客服人員姓名', '對應維修編號',
        '產品品項', '訂單資訊', '客戶問題描述', '訂購人/電話/地址',
        '是/否', 'SN碼', '出貨方式選項', '出貨備註文字',
        '是否拆封選項', '拆封備註', '文字，如 2026-05-20',
        '出貨人員姓名', '系統處理狀態', '出貨收回文字', '收回狀態選項', '家羽備註'
    ]
    ws.append(notes)
    ws.cell(2, 1).font = Font(italic=True, color='808080')
    # 範例列
    ws.append([
        'C1001', '2026-05-19', 'Stacy', 'N00001',
        'ebook 7', 'ORD-12345', '螢幕破損', '王小明/0912345678/台北市',
        '否', 'SN123456', '宅配', '',
        '是', '', '2026-05-20',
        '家羽', '', '已收回', '', ''
    ])
    ws.append([])
    ws.append(['【欄位說明】'])
    ws.append(['換貨編號(客服)', '必填，C 開頭數字，如 C1001；已存在則跳過'])
    ws.append(['出貨收回', '自由文字，直接填寫收回狀況（如：已收回、未收回等）'])
    ws.append(['收回狀態', '請對照代碼管理中「出貨收回(換貨)」的選項值'])
    ws.append(['出貨方式', '請對照代碼管理中「出貨方式」的選項值'])
    ws.append(['是否拆封', '請對照代碼管理中「是否拆封」的選項值'])
    # 欄寬
    col_widths = [16, 14, 10, 12, 10, 16, 20, 24, 6, 12, 10, 14, 8, 12, 14, 10, 14, 10, 14, 12]
    for col_letter, w in zip('ABCDEFGHIJKLMNOPQRST', col_widths):
        ws.column_dimensions[col_letter].width = w
    ws.row_dimensions[1].height = 30
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name='客服換貨匯入範本.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/api/exchange/import', methods=['POST'])
@login_required
def import_exchange():
    """批次匯入客服換貨 xlsx"""
    if 'file' not in request.files:
        return jsonify({'error': '請上傳檔案'}), 400
    file = request.files['file']
    try:
        rows, skipped, errors = _process_exchange_xlsx(file)
        return jsonify({'imported': rows, 'skipped': skipped, 'errors': errors})
    except Exception as e:
        return jsonify({'error': f'處理失敗：{str(e)}'}), 500

# ============================================================
# 代碼管理
# ============================================================
@app.route('/api/codes')
@login_required
def list_all_codes():
    # ⚠️ 重要：此處故意不加 is_active 過濾，請勿擅自加入
    # 原因1：Python True 傳給 PostgREST 會變成 eq.True（大寫），無法匹配布林欄位，會導致全部代碼消失
    # 原因2：代碼刪除為軟刪除（is_active=False），管理介面需要看到全部記錄（含已停用）才能正確顯示
    # 若未來確需過濾，正確寫法為 .eq('is_active', 'true')（小寫字串），並同步更新前端 loadCodes 重試邏輯
    res = sb.table('code_options').select('*').order('field_key').order('sort_order').execute()
    result = {}
    for row in (res.data or []):
        fk = row['field_key']
        if fk not in result:
            result[fk] = {'label': row['field_label'], 'options': []}
        result[fk]['options'].append({'id': row['id'], 'value': row['value'], 'sort_order': row['sort_order']})
    return jsonify(result)

@app.route('/api/codes/<field_key>')
@login_required
def list_codes_by_field(field_key):
    res = sb.table('code_options').select('*').eq('field_key', field_key).order('sort_order').execute()
    return jsonify([r['value'] for r in (res.data or [])])

@app.route('/api/codes/template')
@admin_required
def code_template():
    """下載代碼管理匯入範本（含現有全部資料，未建資料欄位也會列出）"""
    import io
    from datetime import datetime
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font, Alignment
    from flask import send_file

    # 系統定義的所有欄位（與前端 CODE_FIELDS_MAP 保持一致）
    # 格式：(field_key, 欄位名稱, 使用模組)
    ALL_FIELDS = [
        ('form_filler',      '填表人(客服)',    '維修記錄'),
        ('data_source',      '資料來源(客服)',  '維修記錄'),
        ('repair_type',      '維修類型(客服)',  '維修記錄'),
        ('model',            '型號(客服)',      '維修記錄、維修追蹤'),
        ('accessories',      '配件(客服)',      '維修記錄'),
        ('zhanqi_notes',     '展碁備註',        '維修記錄'),
        ('zhanqi_channel',   '展碁通路',        '維修記錄'),
        ('welfare_product',  '福利品',          '維修記錄、客服換貨'),
        ('package_contents', '收件包裹內容',    '維修記錄'),
        ('progress_status',  '進度狀態(客服)',  '維修記錄'),
        ('close_method',     '結案方式',        '維修記錄'),
        ('warranty',         '保固與否',        '維修記錄'),
        ('fault_category',   '故障大項',        '維修記錄'),
        ('detail_category',  '故障細項',        '維修記錄'),
        ('repair_staff',     '維修員',          '維修記錄'),
        ('parts_checklist',  '更換零件記錄',    '維修記錄'),
        ('billing_system',   '帳單系統(Stacy)', '維修記錄'),
        ('detail_stats',     '細項統計(Stacy)', '維修記錄'),
        ('screen_damage',    '破屏/線條',       '維修記錄'),
        ('outsource_vendor', '委外廠商',        '維修記錄'),
        ('cs_staff',         '客服人員',        '客服換貨'),
        ('shipping_staff',   '出貨人員',        '客服換貨'),
        ('shipping_method',  '出貨方式(換貨)',  '客服換貨'),
        ('unpack_video',     '是否拆封(換貨)',  '客服換貨'),
        ('return_received',  '出貨收回(換貨)',  '客服換貨'),
    ]

    # 從 Supabase 取得所有現有資料
    res = sb.table('code_options').select('*').order('field_key').order('sort_order').execute()
    # 依 field_key 分組
    existing = {}
    for r in (res.data or []):
        existing.setdefault(r['field_key'], []).append(r)

    wb = Workbook()
    ws = wb.active
    ws.title = '代碼選項'

    # 表頭（第一欄為使用模組）
    headers = ['使用模組', '欄位代碼', '欄位名稱', '選項值', '排序']
    hfill  = PatternFill('solid', fgColor='1A5276')
    hfont  = Font(bold=True, color='FFFFFF')
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = hfill; cell.font = hfont; cell.alignment = Alignment(horizontal='center')

    empty_fill  = PatternFill('solid', fgColor='FFF3CD')   # 淡黃：尚無資料欄位
    empty_font  = Font(color='856404', italic=True)

    for fk, label, module in ALL_FIELDS:
        rows = existing.get(fk)
        if rows:
            for r in rows:
                ws.append([module, r['field_key'], r['field_label'], r['value'], r['sort_order']])
        else:
            # 欄位有定義但 Supabase 尚無資料 → 填入提示列（淡黃底）
            row_idx = ws.max_row + 1
            ws.append([module, fk, label, '（尚無選項，請填入後匯入）', ''])
            for cell in ws[row_idx]:
                cell.fill = empty_fill
                cell.font = empty_font

    ws.append([])
    ws.append(['', '【說明】欄位代碼與欄位名稱須完整填寫；排序數字越小越優先；淡黃列為尚未建立選項的欄位；使用模組欄位匯入時系統會自動忽略'])

    for col, w in zip('ABCDE', [20, 24, 24, 36, 8]):
        ws.column_dimensions[col].width = w

    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    today = datetime.now().strftime('%Y%m%d')
    return send_file(buf, as_attachment=True,
                     download_name=f'代碼管理_現有資料_{today}.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/api/codes/import', methods=['POST'])
@admin_required
def import_codes():
    """批次匯入代碼選項（mode=upsert 合併 / replace 覆蓋）"""
    if 'file' not in request.files:
        return jsonify({'error': '請上傳檔案'}), 400
    file = request.files['file']
    mode = request.form.get('mode', 'upsert')
    try:
        import openpyxl
        wb = openpyxl.load_workbook(file, data_only=True)
        ws = wb.active
        headers = [str(c.value or '').strip() for c in next(ws.iter_rows(min_row=1, max_row=1))]
        def find_col(names):
            for n in names:
                for i, h in enumerate(headers):
                    if n in h: return i
            return None
        ci_key   = find_col(['欄位代碼', 'field_key'])
        ci_label = find_col(['欄位名稱', 'field_label'])
        ci_val   = find_col(['選項值', 'value'])
        ci_sort  = find_col(['排序', 'sort_order'])
        if ci_key is None or ci_val is None:
            return jsonify({'error': '找不到「欄位代碼」或「選項值」欄位，請使用範本格式'}), 400
        rows = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if all((v is None or str(v).strip() == '') for v in row): continue
            fk  = str(row[ci_key]  or '').strip()
            val = str(row[ci_val]  or '').strip()
            if not fk or not val: continue
            if val == '（尚無選項，請填入後匯入）': continue   # 跳過範本佔位列
            lbl  = str(row[ci_label] or fk).strip() if ci_label is not None else fk
            sort = int(row[ci_sort]) if ci_sort is not None and row[ci_sort] is not None and str(row[ci_sort]).strip().isdigit() else 0
            rows.append({'field_key': fk, 'field_label': lbl, 'value': val, 'sort_order': sort, 'is_active': True})
        if not rows:
            return jsonify({'error': '檔案中找不到有效資料'}), 400

        # ── 模式說明 ────────────────────────────────────────────────────────────
        # upsert（合併，預設）：安全。新選項新增、已存在的更新排序，不刪任何資料。
        #   → 日常新增/修改選項請永遠使用此模式。
        #
        # replace（覆蓋）：⚠️ 高風險，請謹慎使用。
        #   步驟1：先將檔案內出現的 field_key 之現有選項全部標記 is_active=False（停用）
        #   步驟2：再逐筆 upsert 檔案內的選項（is_active 復原為 True）
        #   風險：若步驟1完成但步驟2因網路中斷失敗，舊選項會停留在 is_active=False
        #         雖然 list_all_codes 目前不過濾 is_active（所以管理介面還看得到），
        #         但未來若過濾邏輯有變動，停用的選項會從 UI 消失。
        #   建議：replace 模式僅在需要「完整重建某欄位所有選項順序」時使用，
        #         且匯入前務必先用「下載範本」備份現有資料。
        # ────────────────────────────────────────────────────────────────────────
        if mode == 'replace':
            for key in set(r['field_key'] for r in rows):
                sb.table('code_options').update({'is_active': False}).eq('field_key', key).execute()
        inserted = updated = 0
        for row in rows:
            ex = sb.table('code_options').select('id').eq('field_key', row['field_key']).eq('value', row['value']).execute()
            if ex.data:
                sb.table('code_options').update({
                    'sort_order': row['sort_order'], 'field_label': row['field_label'], 'is_active': True
                }).eq('id', ex.data[0]['id']).execute()
                updated += 1
            else:
                sb.table('code_options').insert(row).execute()
                inserted += 1
        return jsonify({'inserted': inserted, 'updated': updated, 'total': len(rows)})
    except Exception as e:
        return jsonify({'error': f'處理失敗：{str(e)}'}), 500

@app.route('/api/codes', methods=['POST'])
@admin_required
def create_code():
    data = request.json or {}
    res  = sb.table('code_options').insert(data).execute()
    return jsonify({'ok': True, 'id': res.data[0]['id']}), 201

@app.route('/api/codes/<int:cid>', methods=['PUT'])
@admin_required
def update_code(cid):
    data = request.json or {}
    data.pop('id', None)
    data.pop('field_key', None)    # 不允許更改欄位類型
    data.pop('created_at', None)
    sb.table('code_options').update(data).eq('id', cid).execute()
    return jsonify({'ok': True})

@app.route('/api/codes/<int:cid>', methods=['DELETE'])
@admin_required
def delete_code(cid):
    try:
        # ── 取得代碼資訊（用 execute 不用 single，避免找不到時拋 406）──
        code_res = sb.table('code_options').select('field_key, value').eq('id', cid).execute()
        if not code_res.data:
            return jsonify({'error': '找不到此代碼'}), 404
        field_key = code_res.data[0]['field_key']
        value     = code_res.data[0]['value']
    except Exception as e:
        return jsonify({'error': f'查詢代碼失敗：{str(e)}'}), 500

    # ── field_key → [(資料表, DB欄位, 顯示名稱), ...] ──────────
    # 注意：部分 field_key 與 DB 欄位名稱不同（見 CLAUDE.md「代碼欄位混淆」）
    FIELD_USAGE_MAP = {
        'form_filler':     [('repair_records',  'form_filler',      '維修記錄')],
        'data_source':     [('repair_records',  'data_source',      '維修記錄')],
        'repair_type':     [('repair_records',  'repair_type',      '維修記錄')],
        'model':           [('repair_records',  'model',            '維修記錄'),
                            ('repair_tracking', 'model',            '維修追蹤')],
        'accessories':     [('repair_records',  'accessories',      '維修記錄')],
        'zhanqi_notes':    [('repair_records',  'ebook_note',       '維修記錄')],
        'zhanqi_channel':  [('repair_records',  'ebook_channel',    '維修記錄')],
        'welfare_product': [('repair_records',  'welfare_product',  '維修記錄'),
                            ('exchange_orders', 'welfare_product',  '客服換貨')],
        'package_contents':[('repair_records',  'received_package', '維修記錄')],
        'progress_status': [('repair_records',  'progress_status',  '維修記錄')],
        'close_method':    [('repair_records',  'close_method',     '維修記錄')],
        'warranty':        [('repair_records',  'warranty',         '維修記錄')],
        'fault_category':  [('repair_records',  'fault_category',   '維修記錄')],
        'detail_category': [('repair_records',  'fault_detail',     '維修記錄')],
        'repair_staff':    [('repair_records',  'repair_staff',     '維修記錄')],
        'billing_system':  [('repair_records',  'billing_system',   '維修記錄')],
        'detail_stats':    [('repair_records',  'detail_stats',     '維修記錄')],
        'screen_damage':   [('repair_records',  'screen_damage',    '維修記錄')],
        'outsource_vendor':[('repair_records',  'outsource_vendor', '維修記錄')],
        'cs_staff':        [('exchange_orders', 'cs_staff',         '客服換貨')],
        'shipping_staff':  [('exchange_orders', 'shipping_staff',   '客服換貨')],
        'shipping_method': [('exchange_orders', 'shipping_method',  '客服換貨')],
        'unpack_video':    [('exchange_orders', 'unpack_video',     '客服換貨')],
        'return_received': [('exchange_orders', 'return_received',  '客服換貨')],
    }

    # ── 查詢各資料表使用量 ───────────────────────────────────────
    in_use_parts = []
    for table, column, label in FIELD_USAGE_MAP.get(field_key, []):
        try:
            cnt_res = sb.table(table).select('id', count='exact').eq(column, value).execute()
            cnt = cnt_res.count or 0
            if cnt > 0:
                in_use_parts.append(f'「{label}」{cnt} 筆')
        except Exception:
            pass  # 查詢失敗時忽略，不阻擋刪除

    if in_use_parts:
        return jsonify({
            'error': f'此代碼尚有記錄 {", ".join(in_use_parts)} 在使用，請先移除該選項，才能刪除！'
        }), 409

    # ── 確認無使用，執行刪除 ─────────────────────────────────────
    sb.table('code_options').delete().eq('id', cid).execute()
    return jsonify({'ok': True})

# ============================================================
# 帳號管理
# ============================================================
@app.route('/api/accounts/users')
@admin_required
def list_users():
    res = sb.table('users').select('id, username, display_name, is_active, last_login, created_at, group_id, permission_groups(name)').order('id').execute()
    return jsonify(res.data or [])

@app.route('/api/accounts/users', methods=['POST'])
@admin_required
def create_user():
    data        = request.json or {}
    username    = data.get('username', '').strip()
    password    = data.get('password', '').strip()
    display_name = data.get('display_name', '').strip()
    group_id    = data.get('group_id')
    if not username or not password:
        return jsonify({'error': '帳號與密碼為必填'}), 400
    payload = {
        'username':      username,
        'display_name':  display_name,
        'password_hash': hash_password(password),
        'group_id':      group_id,
        'is_active':     True,
    }
    try:
        res = sb.table('users').insert(payload).execute()
        return jsonify({'ok': True, 'id': res.data[0]['id']}), 201
    except Exception as e:
        return jsonify({'error': f'帳號已存在或建立失敗：{str(e)}'}), 409

@app.route('/api/accounts/users/<int:uid>', methods=['PUT'])
@admin_required
def update_user(uid):
    data = request.json or {}
    payload = {
        'display_name': data.get('display_name', ''),
        'group_id':     data.get('group_id'),
        'is_active':    data.get('is_active', True),
    }
    if data.get('password'):
        payload['password_hash'] = hash_password(data['password'])
    sb.table('users').update(payload).eq('id', uid).execute()
    return jsonify({'ok': True})

@app.route('/api/accounts/users/<int:uid>', methods=['DELETE'])
@admin_required
def delete_user(uid):
    if uid == session.get('user_id'):
        return jsonify({'error': '不能刪除自己的帳號'}), 400
    sb.table('users').delete().eq('id', uid).execute()
    return jsonify({'ok': True})

@app.route('/api/accounts/groups')
@login_required
def list_groups():
    res = sb.table('permission_groups').select('*').order('id').execute()
    return jsonify(res.data or [])

@app.route('/api/accounts/groups', methods=['POST'])
@admin_required
def create_group():
    data = request.json or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': '群組名稱為必填'}), 400
    # 'desc' 欄位不存在於 Supabase permission_groups 表，須過濾
    payload = {k: v for k, v in data.items() if k not in ('id', 'desc')}
    try:
        res = sb.table('permission_groups').insert(payload).execute()
        return jsonify({'ok': True, 'id': res.data[0]['id']}), 201
    except Exception as e:
        return jsonify({'error': f'建立失敗：{str(e)}'}), 409

@app.route('/api/accounts/groups/<int:gid>', methods=['PUT'])
@admin_required
def update_group(gid):
    data = request.json or {}
    data.pop('id', None)
    data.pop('desc', None)   # 'desc' 欄位不存在於 permission_groups 表
    sb.table('permission_groups').update(data).eq('id', gid).execute()
    return jsonify({'ok': True})

@app.route('/api/accounts/groups/<int:gid>', methods=['DELETE'])
@admin_required
def delete_group(gid):
    if gid == 1:
        return jsonify({'error': '不能刪除系統管理員群組'}), 400
    sb.table('permission_groups').delete().eq('id', gid).execute()
    return jsonify({'ok': True})

# ============================================================
# xlsx 批次匯入（內部函式）
# ============================================================
def _parse_date(val):
    """支援多種日期格式"""
    if val is None or val == '':
        return None
    if isinstance(val, datetime):
        return val.strftime('%Y-%m-%d')
    s = str(val).strip()
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%Y/%m/%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    # Excel 序號
    try:
        n = float(s)
        if 40000 < n < 50000:
            base = datetime(1899, 12, 30)
            return (base + timedelta(days=n)).strftime('%Y-%m-%d')
    except ValueError:
        pass
    return None

def _process_tracking_xlsx(file):
    import openpyxl, re
    wb = openpyxl.load_workbook(file, data_only=True)
    ws = wb.active
    headers = [str(c.value or '').strip() for c in next(ws.iter_rows(min_row=1, max_row=1))]

    # 欄位模糊對應（同前端 matchHeader：去除括號與空白後做子字串比對）
    # 格式：'關鍵字': 'db欄位'，一個 db 欄位可對應多個關鍵字
    COL_RULES = [
        (['維修編號'],                          'repair_no'),
        (['機型', '型號'],                       'model'),
        (['阿偉編號'],                           'awei_no'),
        (['已收檢測費', '收檢測費'],              'inspection_fee_received'),
        (['已給初檢', '給初檢', '已給竹涵', '給竹涵'], 'given_to_zhuhan'),
        (['已寄委外', '寄委外', '已寄阿偉', '寄阿偉'], 'sent_to_awei'),
        (['故障料件', '料件'],                   'fault_parts'),
        (['實測故障'],                           'actual_fault'),
        (['已通知客服報價', '通知客服報價'],       'notified_cs_quote'),
        (['已開付款網址', '付款網址'],            'payment_url_opened'),
        (['已報價客人', '報價客人'],              'quoted_customer'),
        (['已收維修費', '收維修費'],              'repair_fee_received'),
        (['已通知委外', '通知委外', '已通知阿偉', '通知阿偉'], 'notified_awei'),
        (['交給客服'],                           'repair_complete_cs'),
        (['備註', '聯絡進度'],                   'notes'),
    ]
    DATE_FIELDS = {'inspection_fee_received'}

    def _norm(s):
        """去除空白與括號內容，轉小寫，用於模糊比對"""
        return re.sub(r'\s|\(.*?\)|\（.*?\）', '', str(s)).lower()

    def _match(header, candidates):
        h = _norm(header)
        return any(h == _norm(c) or _norm(c) in h or h in _norm(c) for c in candidates)

    col_idx = {}
    for i, h in enumerate(headers):
        for candidates, field in COL_RULES:
            if field not in col_idx and _match(h, candidates):
                col_idx[field] = i
                break

    if 'repair_no' not in col_idx:
        return 0, 0, ['找不到「維修編號」欄位']

    # 取得已存在的維修編號
    existing = {r['repair_no'] for r in (sb.table('repair_tracking').select('repair_no').execute().data or [])}

    imported = skipped = 0
    errors = []

    for row in ws.iter_rows(min_row=2, values_only=True):
        repair_no = str(row[col_idx['repair_no']] or '').strip()
        if not repair_no:
            continue
        if repair_no in existing:
            skipped += 1
            continue

        rec = {'repair_no': repair_no, 'created_by_name': '批次匯入', 'updated_by_name': '批次匯入'}
        for field, idx in col_idx.items():
            if field == 'repair_no':
                continue
            val = row[idx] if idx < len(row) else None
            if field in DATE_FIELDS:
                rec[field] = _parse_date(val)
            else:
                # datetime 物件只取日期部分，避免顯示 00:00:00
                from datetime import datetime as _dt, date as _date
                if isinstance(val, (_dt, _date)):
                    rec[field] = val.strftime('%Y-%m-%d')
                else:
                    rec[field] = str(val).strip() if val is not None and val != '' else None

        # 阿偉編號：空白時自動補號
        if not rec.get('awei_no'):
            rec['awei_no'] = next_serial('awei_next_no', 'A', 4)

        # 自動帶入機型（用 limit(1) 避免 .single() 在找不到時回 406 讓匯入整批炸掉）
        if not rec.get('model'):
            try:
                rr = sb.table('repair_records').select('model').eq('repair_no', repair_no).limit(1).execute()
                if rr.data:
                    rec['model'] = rr.data[0].get('model', '')
            except Exception:
                pass   # 找不到機型不影響匯入，留空即可

        _clean_tracking(rec)   # 確保 repair_complete_cs 空字串轉 None
        try:
            sb.table('repair_tracking').insert(rec).execute()
            existing.add(repair_no)
            imported += 1
        except Exception as e:
            errors.append(f"{repair_no}: {str(e)}")

    return imported, skipped, errors


def _process_exchange_xlsx(file):
    import openpyxl, re
    wb = openpyxl.load_workbook(file, data_only=True)
    ws = wb.active
    headers = [str(c.value or '').strip() for c in next(ws.iter_rows(min_row=1, max_row=1))]

    DATE_FIELDS = {'fill_date'}   # expected_ship_date 已改為文字型，不做日期轉換
    VLOOKUP_FIELDS = {'order_info', 'customer_desc', 'customer_contact', 'welfare_product', 'original_sn'}

    def _norm(s):
        """去除空白與括號內容，轉小寫"""
        return re.sub(r'\s|\(.*?\)|\（.*?\）', '', str(s)).lower()

    # 優先序規則：含「家羽」的先處理，避免「出貨備註」誤判
    def _map_header(h_orig):
        h = h_orig.lower()
        h_n = _norm(h_orig)
        # ── 含「家羽」的欄位 ──────────────────────────────
        if '家羽' in h or 'jiayu' in h:
            if '備註' in h or '系統' in h or 'note' in h:
                return 'shipping_notes' if '備註' in h else 'system_process'
        # ── 換貨編號 ─────────────────────────────────────
        if '換貨編號' in h: return 'exchange_no'
        # ── 填表日期 ─────────────────────────────────────
        if '填表日期' in h: return 'fill_date'
        # ── 客服 / 出貨人員 ───────────────────────────────
        if ('客服' in h or 'cs' in h) and '人員' in h: return 'cs_staff'
        if h_n in ('客服',): return 'cs_staff'
        if '出貨人員' in h: return 'shipping_staff'
        # ── 維修編號 ─────────────────────────────────────
        if '維修編號' in h: return 'repair_no'
        # ── 品項 ─────────────────────────────────────────
        if '品項' in h and '訂' not in h: return 'item'
        # ── 訂單 ─────────────────────────────────────────
        if '訂單資訊' in h: return 'order_info'
        if '問題描述' in h or '客戶問題' in h: return 'customer_desc'
        if '電話' in h and ('地址' in h or '收件' in h): return 'customer_contact'
        # ── 福利品 / SN ───────────────────────────────────
        if '福利品' in h: return 'welfare_product'
        if '原sn' in h or ('sn' in h and '原' in h): return 'original_sn'
        # ── 出貨方式 ─────────────────────────────────────
        if '出貨方式' in h and '備註' not in h: return 'shipping_method'
        # ── 客服寄出備註 / 出貨備註（非家羽）──────────────
        if '客服寄出備註' in h: return 'shipping_remark'
        if '出貨備註' in h and '家羽' not in h: return 'shipping_remark'
        if '出貨方式備註' in h: return 'shipping_remark'
        # ── 是否拆封（備註要先判斷）──────────────────────
        if ('拆封' in h or '拆膜' in h) and '備註' in h: return 'unpack_remark'
        if '拆封' in h or '拆膜' in h: return 'unpack_video'
        # ── 預計出貨日期 ─────────────────────────────────
        if '預計出貨' in h: return 'expected_ship_date'
        # ── 出貨系統處理 ─────────────────────────────────
        if ('系統處理' in h or '出貨系統' in h) and '家羽' not in h: return 'system_process'
        # ── 出貨收回（狀態/備註先判斷）───────────────────────
        if '出貨收回備註' in h or '收回備註' in h or '收回狀態' in h: return 'return_remark'
        if '出貨收回' in h: return 'return_received'
        return None

    col_idx = {}
    for i, h in enumerate(headers):
        field = _map_header(h)
        if field and field not in col_idx:
            col_idx[field] = i
        # 精確補漏：針對無法模糊比對的特殊欄名
        FALLBACK = {
            '換貨編號': 'exchange_no', '填表日期': 'fill_date',
            '客服': 'cs_staff', '維修編號': 'repair_no', '品項': 'item',
        }
        if not field and h in FALLBACK and FALLBACK[h] not in col_idx:
            col_idx[FALLBACK[h]] = i

    if 'exchange_no' not in col_idx:
        return 0, 0, ['找不到「換貨編號(客服)」欄位']

    existing = {r['exchange_no'] for r in (sb.table('exchange_orders').select('exchange_no').execute().data or [])}

    imported = skipped = 0
    errors = []
    new_records = []   # 先收集全部要新增的列，再批次寫入

    for row in ws.iter_rows(min_row=2, values_only=True):
        exchange_no = str(row[col_idx['exchange_no']] or '').strip()
        if not exchange_no:
            continue
        if exchange_no in existing:
            skipped += 1
            continue
        existing.add(exchange_no)   # 即時加入，防止同一 Excel 內重複編號觸發整批失敗

        rec = {'exchange_no': exchange_no}
        for field, idx in col_idx.items():
            if field == 'exchange_no':
                continue
            val = row[idx] if idx < len(row) else None
            # VLOOKUP 欄位：若為公式結果（字串含 =VLOOKUP）則略過
            if field in VLOOKUP_FIELDS:
                s = str(val or '').strip()
                if s.startswith('=') or not s:
                    continue
                rec[field] = s
            elif field in DATE_FIELDS:
                rec[field] = _parse_date(val)
            else:
                # datetime 物件只取日期部分，避免 '2026-05-07 00:00:00' 字串
                from datetime import datetime as _dt, date as _date
                if isinstance(val, (_dt, _date)):
                    rec[field] = val.strftime('%Y-%m-%d')
                else:
                    rec[field] = str(val).strip() if val else None

        new_records.append(rec)

    print(f'[ExcImport] 檔案共 {ws.max_row-1} 列，new_records={len(new_records)}，skipped={skipped}')

    # ── PostgREST 要求同批次所有物件欄位名稱完全一致，先補齊缺少的欄位為 None ──
    if new_records:
        all_keys = set()
        for rec in new_records:
            all_keys.update(rec.keys())
        for rec in new_records:
            for key in all_keys:
                rec.setdefault(key, None)

    # ── 批次 INSERT（每批 100 筆，避免 Render 30s 超時）──────────
    BATCH = 100
    for i in range(0, len(new_records), BATCH):
        batch = new_records[i:i + BATCH]
        try:
            sb.table('exchange_orders').insert(batch).execute()
            for rec in batch:
                existing.add(rec['exchange_no'])
            imported += len(batch)
        except Exception as e:
            for rec in batch:
                errors.append(f"{rec['exchange_no']}: {str(e)[:80]}")

    # 更新換貨編號起點
    if imported > 0:
        all_nos = [int(n[1:]) for n in existing if n.startswith('C') and n[1:].isdigit()]
        if all_nos:
            next_no = f"C{max(all_nos) + 1}"
            try:
                sb.table('system_config').update({'value': next_no}).eq('key', 'exchange_next_no').execute()
            except Exception:
                pass   # 流水號更新失敗不影響主匯入結果

    return imported, skipped, errors


# ============================================================
# 啟動
# ============================================================
if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    print('=' * 50)
    print('  HyRead 維修記錄管理系統 (Supabase 版)')
    print(f'  網址: http://localhost:{port}')
    print('  預設帳號: admin / admin123')
    print('=' * 50)
    app.run(host='0.0.0.0', port=port, debug=debug)
:
                    rec[field] = str(val).strip() if val else None

        new_records.append(rec)

    print(f'[ExcImport] 檔案共 {ws.max_row-1} 列，new_records={len(new_records)}，skipped={skipped}')

    # ── PostgREST 要求同批次所有物件欄位名稱完全一致，先補齊缺少的欄位為 None ──
    if new_records:
        all_keys = set()
        for rec in new_records:
            all_keys.update(rec.keys())
        for rec in new_records:
            for key in all_keys:
                rec.setdefault(key, None)

    # ── 批次 INSERT（每批 100 筆，避免 Render 30s 超時）──────────
    BATCH = 100
    for i in range(0, len(new_records), BATCH):
        batch = new_records[i:i + BATCH]
        try:
            sb.table('exchange_orders').insert(batch).execute()
            for rec in batch:
                existing.add(rec['exchange_no'])
            imported += len(batch)
        except Exception as e:
            for rec in batch:
                errors.append(f"{rec['exchange_no']}: {str(e)[:80]}")

    # 更新換貨編號起點
    if imported > 0:
        all_nos = [int(n[1:]) for n in existing if n.startswith('C') and n[1:].isdigit()]
        if all_nos:
            next_no = f"C{max(all_nos) + 1}"
            try:
                sb.table('system_config').update({'value': next_no}).eq('key', 'exchange_next_no').execute()
            except Exception:
                pass   # 流水號更新失敗不影響主匯入結果

    return imported, skipped, errors


# ============================================================
# 啟動
# ============================================================
if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    print('=' * 50)
    print('  HyRead 維修記錄管理系統 (Supabase 版)')
    print(f'  網址: http://localhost:{port}')
    print('  預設帳號: admin / admin123')
    print('=' * 50)
    app.run(host='0.0.0.0', port=port, debug=debug)
