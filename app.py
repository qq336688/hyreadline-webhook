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
    '舊維修編號':   'old_repair_no',
    '填表人':       'form_filler',
    '資料來源':     'data_source',
    '填單日期':     'fill_date',
    '維修類型':     'repair_type',
    '型號':         'model',
    'SN碼':         'serial_no',
    '客戶姓名':     'customer_name',
    '帳號':         'customer_account',
    '電話1':        'customer_phone1',
    '電話2':        'customer_phone2',
    '信箱':         'customer_email',
    '地址':         'customer_address',
    '展碁備註':     'ebook_note',
    '展碁通路':     'ebook_channel',
    '福利品':       'is_welfare',
    '發票號碼':     'invoice_no',
    '發票日期':     'invoice_date',
    '歷次維修編號': 'prev_repair_nos',
    '收件包裹':     'received_package',
    '收回日期':     'received_date',
    '原商品出貨日期': 'original_ship_date',
    '客戶問題備註': 'customer_issue',
    '換機換貨SN':   'exchange_sn',
    '付款單號1':    'payment_no1',
    '付款金額1':    'payment_amount1',
    '付款單號2':    'payment_no2',
    '付款金額2':    'payment_amount2',
    '其他備註':     'other_notes',
    '保固':         'warranty',
    '故障大項':     'fault_category',
    '故障細項':     'fault_detail',
    '破屏線條':     'screen_damage',
    '實測故障':     'actual_fault',
    '更換零件':     'replaced_parts',
    '維修紀錄':     'repair_record',
    '檢測費':       'inspection_fee',
    '維修費':       'repair_fee',
    '維修員':       'technician',
    '維修日期':     'repair_date',
    '換下壞品':     'bad_part_removed',
    '維修備註':     'repair_notes',
    '帳單系統':     'billing_system',
    '付款總額':     'total_payment',
    '委外廠商':     'outsource_vendor',
    '委外請款月份': 'outsource_month',
    '委外金額':     'outsource_amount',
    '進度狀態':     'progress_status',
    '結案方式':     'close_method',
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
    # 說明列
    notes = ['原系統序號','*必填','*必填','*必填 YYYY-MM-DD','*必填','*必填','*必填',
             '','','','','','','','','是/否','','YYYY-MM-DD','',
             '','YYYY-MM-DD','YYYY-MM-DD','','','','數字','','數字','',
             '保固內/保固外','','','有/無','','','','數字','數字','',
             'YYYY-MM-DD','','','','數字','','YYYY-MM',
             '數字','見下方選項','見下方選項']
    ws.append(notes)
    ws.cell(2,1).font = Font(italic=True, color='808080')
    # 範例
    ws.append(['1001','Stacy','電話','2026-05-17','保固維修','ebook 7','SN123456',
               '王小明','hyread001','0912345678','','user@email.com','台北市中正區',
               '','博客來','否','','','','原廠紙箱','2026-05-18','2025-01-01','螢幕破損',
               '','','','','','','保固內','螢幕','破屏','有','螢幕破裂','螢幕',
               '更換螢幕完成','0','0','阿偉','2026-05-19','','',
               '','0','','','0','已收貨，資料登錄中',''])
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
        # 找出哪些欄有對應
        col_idx = {}
        for i, h in enumerate(headers):
            if h in REPAIR_IMPORT_COLS:
                col_idx[REPAIR_IMPORT_COLS[h]] = i
        if 'serial_no' not in col_idx and 'form_filler' not in col_idx:
            return jsonify({'error': '找不到必要欄位，請使用範本格式'}), 400

        # 取得已存在的舊維修編號（避免重複）
        existing_res = sb.table('repair_records').select('old_repair_no').execute()
        existing_old = {r['old_repair_no'] for r in (existing_res.data or []) if r.get('old_repair_no')}

        imported = skipped = 0
        errors = []
        date_fields    = {'fill_date','invoice_date','received_date','original_ship_date','repair_date'}
        numeric_fields = {'inspection_fee','repair_fee','payment_amount1','payment_amount2',
                          'total_payment','outsource_amount'}
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

            # 自動產生新維修編號
            rec['repair_no']       = next_serial('repair_next_no', 'N', 5)
            rec['created_by']      = session['user_id']
            rec['updated_by']      = session['user_id']
            rec['created_by_name'] = session.get('display_name', session.get('username', ''))
            rec['updated_by_name'] = session.get('display_name', session.get('username', ''))
            rec.setdefault('progress_status', '待收貨，客服建單中')

            try:
                sb.table('repair_records').insert(rec).execute()
                if old_no:
                    existing_old.add(old_no)
                imported += 1
            except Exception as e:
                errors.append(f"第{imported+skipped+len(errors)+3}列：{str(e)[:60]}")

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
        '新維修編號','舊維修編號','填表人','資料來源','填單日期','維修類型','型號','SN碼',
        '客戶姓名','帳號','電話1','電話2','信箱','地址',
        '展碁備註','展碁通路','福利品','發票號碼','發票日期',
        '收件包裹','收回日期','客戶問題備註',
        '換機換貨SN','付款單號1','付款金額1','付款單號2','付款金額2','其他備註',
        '保固','故障大項','故障細項','破屏線條','實測故障','更換零件','維修紀錄',
        '檢測費','維修費','維修員','維修日期','維修備註',
        '帳單系統','付款總額','委外廠商','委外請款月份','委外金額',
        '進度狀態','結案方式'
    ]
    field_map = [
        'repair_no','old_repair_no','form_filler','data_source','fill_date','repair_type','model','serial_no',
        'customer_name','customer_account','customer_phone1','customer_phone2','customer_email','customer_address',
        'ebook_note','ebook_channel','is_welfare','invoice_no','invoice_date',
        'received_package','received_date','customer_issue',
        'exchange_sn','payment_no1','payment_amount1','payment_no2','payment_amount2','other_notes',
        'warranty','fault_category','fault_detail','screen_damage','actual_fault','replaced_parts','repair_record',
        'inspection_fee','repair_fee','technician','repair_date','repair_notes',
        'billing_system','total_payment','outsource_vendor','outsource_month','outsource_amount',
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
    # 資料列
    for r in records:
        row = [str(r.get(f, '') or '') for f in field_map]
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

@app.route('/api/repair/records', methods=['POST'])
@login_required
def create_repair_record():
    data = request.json or {}
    # 自動產生新維修編號
    repair_no = next_serial('repair_next_no', 'N', 5)
    data['repair_no']        = repair_no
    data['created_by']       = session['user_id']
    data['updated_by']       = session['user_id']
    data['created_by_name']  = session.get('display_name', session.get('username', ''))
    data['updated_by_name']  = session.get('display_name', session.get('username', ''))
    data.pop('id', None)
    res = sb.table('repair_records').insert(data).execute()
    if res.data:
        return jsonify({'id': res.data[0]['id'], 'repair_no': repair_no, 'ok': True}), 201
    return jsonify({'error': '建立失敗'}), 500

@app.route('/api/repair/records/<int:rid>', methods=['PUT'])
@login_required
def update_repair_record(rid):
    data = request.json or {}
    data['updated_by']       = session['user_id']
    data['updated_by_name']  = session.get('display_name', session.get('username', ''))
    data.pop('id', None)
    data.pop('repair_no', None)     # 不允許修改編號
    data.pop('created_by', None)
    data.pop('created_by_name', None)
    data.pop('created_at', None)
    res = sb.table('repair_records').update(data).eq('id', rid).execute()
    return jsonify({'ok': True})

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
            f"original_sn.ilike.%{search}%"
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
        '出貨人員(客服)', '出貨系統處理', '出貨收回', '收回備註', '出貨備註(家羽)'
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
        '出貨人員姓名', '系統處理狀態', '出貨收回選項', '收回備註文字', '家羽備註'
    ]
    ws.append(notes)
    ws.cell(2, 1).font = Font(italic=True, color='808080')
    # 範例列
    ws.append([
        'C1001', '2026-05-19', 'Stacy', 'N00001',
        'ebook 7', 'ORD-12345', '螢幕破損', '王小明/0912345678/台北市',
        '否', 'SN123456', '宅配', '',
        '是', '', '2026-05-20',
        '家羽', '', 'X', '', ''
    ])
    ws.append([])
    ws.append(['【欄位說明】'])
    ws.append(['換貨編號(客服)', '必填，C 開頭數字，如 C1001；已存在則跳過'])
    ws.append(['出貨收回', '請對照代碼管理中「出貨收回」的選項值'])
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
    res = sb.table('code_options').select('*').eq('is_active', True).order('field_key').order('sort_order').execute()
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
    res = sb.table('code_options').select('*').eq('field_key', field_key).eq('is_active', True).order('sort_order').execute()
    return jsonify([r['value'] for r in (res.data or [])])

@app.route('/api/codes/template')
@admin_required
def code_template():
    """下載代碼管理匯入範本（含現有全部資料）"""
    import io
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font, Alignment
    from flask import send_file
    res = sb.table('code_options').select('*').eq('is_active', True).order('field_key').order('sort_order').execute()
    wb = Workbook()
    ws = wb.active
    ws.title = '代碼選項'
    headers = ['欄位代碼', '欄位名稱', '選項值', '排序']
    hfill = PatternFill('solid', fgColor='1A5276')
    hfont = Font(bold=True, color='FFFFFF')
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = hfill; cell.font = hfont; cell.alignment = Alignment(horizontal='center')
    for r in (res.data or []):
        ws.append([r['field_key'], r['field_label'], r['value'], r['sort_order']])
    ws.append([])
    ws.append(['【說明】欄位代碼與欄位名稱須完整填寫；排序數字越小越優先'])
    for col, w in zip('ABCD', [22, 22, 28, 8]):
        ws.column_dimensions[col].width = w
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, as_attachment=True, download_name='代碼選項範本.xlsx',
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
            lbl  = str(row[ci_label] or fk).strip() if ci_label is not None else fk
            sort = int(row[ci_sort]) if ci_sort is not None and row[ci_sort] is not None and str(row[ci_sort]).strip().isdigit() else 0
            rows.append({'field_key': fk, 'field_label': lbl, 'value': val, 'sort_order': sort, 'is_active': True})
        if not rows:
            return jsonify({'error': '檔案中找不到有效資料'}), 400
        # 覆蓋模式：先停用受影響欄位的現有選項
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
    sb.table('code_options').update({'is_active': False}).eq('id', cid).execute()
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
        # ── 出貨收回（備註先判斷）───────────────────────
        if '出貨收回備註' in h or '收回備註' in h: return 'return_remark'
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

        rec.setdefault('return_received', 'X')
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
