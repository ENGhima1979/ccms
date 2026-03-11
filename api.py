"""
REST API الخارجي — المرحلة الثالثة
يوفر API كامل للتكامل مع أنظمة ERP وأنظمة أخرى
"""
import json, hashlib, secrets
from functools import wraps
from flask import Blueprint, request, jsonify, session
from models import get_db, new_id, now, today

api = Blueprint('api', __name__, url_prefix='/api/v1')

# ─── API Key Auth ─────────────────────────────────────
def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if not key:
            return jsonify({'error': 'API key required', 'code': 401}), 401
        conn = get_db()
        row = conn.execute("""
            SELECT u.*, u.company_id FROM users u
            WHERE u.api_key = ? AND u.is_active = 1
        """, (key,)).fetchone()
        conn.close()
        if not row:
            return jsonify({'error': 'Invalid API key', 'code': 401}), 401
        request.api_user = dict(row)
        request.company_id = row['company_id']
        return f(*args, **kwargs)
    return decorated

def paginate(query_result, page, per_page=20):
    total = len(query_result)
    start = (page - 1) * per_page
    items = query_result[start:start+per_page]
    return {
        'items': [dict(r) for r in items],
        'pagination': {
            'page': page, 'per_page': per_page,
            'total': total, 'pages': (total + per_page - 1) // per_page
        }
    }

# ─── Health Check ─────────────────────────────────────
@api.route('/health')
def health():
    return jsonify({'status': 'ok', 'version': '3.0', 'system': 'CCMS'})

# ─── Correspondence ───────────────────────────────────
@api.route('/correspondence', methods=['GET'])
@require_api_key
def api_list_correspondence():
    cid   = request.company_id
    page  = int(request.args.get('page', 1))
    type_ = request.args.get('type')
    status= request.args.get('status')
    q     = request.args.get('q','')
    
    conn  = get_db()
    sql   = "SELECT c.*, p.name as project_name FROM correspondence c LEFT JOIN projects p ON c.project_id=p.id WHERE c.company_id=? AND c.is_deleted=0"
    params= [cid]
    if type_:   sql += " AND c.type=?";    params.append(type_)
    if status:  sql += " AND c.status=?";  params.append(status)
    if q:       sql += " AND (c.subject LIKE ? OR c.party LIKE ? OR c.ref_num LIKE ?)"; params += [f'%{q}%']*3
    sql += " ORDER BY c.created_at DESC"
    
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    result = paginate(rows, page)
    return jsonify({'success': True, **result})

@api.route('/correspondence/<cid>', methods=['GET'])
@require_api_key
def api_get_correspondence(cid):
    conn = get_db()
    item = conn.execute("""
        SELECT c.*, p.name as project_name, u.full_name as creator_name,
               d.name as dept_name
        FROM correspondence c
        LEFT JOIN projects p ON c.project_id=p.id
        LEFT JOIN users u ON c.created_by=u.id
        LEFT JOIN departments d ON c.department_id=d.id
        WHERE c.id=? AND c.company_id=? AND c.is_deleted=0
    """, (cid, request.company_id)).fetchone()
    
    if not item:
        conn.close()
        return jsonify({'error': 'Not found', 'code': 404}), 404
    
    atts = conn.execute("SELECT * FROM attachments WHERE correspondence_id=?", (cid,)).fetchall()
    comments = conn.execute("SELECT cm.*, u.full_name FROM comments cm JOIN users u ON cm.user_id=u.id WHERE cm.correspondence_id=?", (cid,)).fetchall()
    conn.close()
    
    return jsonify({
        'success': True,
        'data': {
            **dict(item),
            'attachments': [dict(a) for a in atts],
            'comments': [dict(c) for c in comments]
        }
    })

@api.route('/correspondence', methods=['POST'])
@require_api_key
def api_create_correspondence():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400
    
    required = ['subject', 'party', 'type']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({'error': f'Missing fields: {", ".join(missing)}'}), 400
    
    conn = get_db()
    cid  = request.company_id
    uid  = request.api_user['id']
    
    # Generate ref_num
    co_code = conn.execute("SELECT code FROM companies WHERE id=?", (cid,)).fetchone()['code']
    type_code = {'out':'OUT','in':'IN','internal':'INT'}.get(data['type'],'OUT')
    import datetime
    year = datetime.datetime.now().year
    seq  = conn.execute("SELECT COUNT(*)+1 as n FROM correspondence WHERE company_id=? AND type=? AND substr(date,1,4)=?",
                        (cid, data['type'], str(year))).fetchone()['n']
    ref_num = f"{co_code}-{year}-{type_code}-{str(seq).zfill(5)}"
    
    new_cid = new_id()
    conn.execute("""INSERT INTO correspondence
        (id,company_id,ref_num,type,subject,party,priority,status,
         category,body,date,created_by,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (new_cid, cid, ref_num, data['type'], data['subject'], data['party'],
         data.get('priority','normal'), data.get('status','draft'),
         data.get('category','general'), data.get('body',''),
         data.get('date', today()), uid, now()))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'id': new_cid, 'ref_num': ref_num}), 201

@api.route('/correspondence/<cid>', methods=['PUT'])
@require_api_key
def api_update_correspondence(cid):
    data = request.get_json() or {}
    conn = get_db()
    item = conn.execute("SELECT id FROM correspondence WHERE id=? AND company_id=?",
                        (cid, request.company_id)).fetchone()
    if not item:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    
    allowed = ['subject','party','priority','status','body','category','due_date','action_required']
    updates = {k: v for k, v in data.items() if k in allowed}
    if updates:
        set_clause = ', '.join(f'{k}=?' for k in updates)
        conn.execute(f"UPDATE correspondence SET {set_clause}, updated_at=? WHERE id=?",
                     [*updates.values(), now(), cid])
        conn.commit()
    conn.close()
    return jsonify({'success': True, 'updated': list(updates.keys())})

# ─── Projects ─────────────────────────────────────────
@api.route('/projects', methods=['GET'])
@require_api_key
def api_projects():
    conn = get_db()
    rows = conn.execute("SELECT * FROM projects WHERE company_id=? AND is_active=1 ORDER BY name",
                        (request.company_id,)).fetchall()
    conn.close()
    return jsonify({'success': True, 'data': [dict(r) for r in rows]})

# ─── Contacts ─────────────────────────────────────────
@api.route('/contacts', methods=['GET'])
@require_api_key
def api_contacts():
    q    = request.args.get('q','')
    conn = get_db()
    if q:
        rows = conn.execute("SELECT * FROM contacts WHERE company_id=? AND is_active=1 AND (name LIKE ? OR email LIKE ?)",
                            (request.company_id, f'%{q}%', f'%{q}%')).fetchall()
    else:
        rows = conn.execute("SELECT * FROM contacts WHERE company_id=? AND is_active=1 ORDER BY name",
                            (request.company_id,)).fetchall()
    conn.close()
    return jsonify({'success': True, 'data': [dict(r) for r in rows]})

# ─── Stats ────────────────────────────────────────────
@api.route('/stats', methods=['GET'])
@require_api_key
def api_stats():
    conn = get_db()
    cid  = request.company_id
    stats = {}
    for key, sql in [
        ('total',    "SELECT COUNT(*) FROM correspondence WHERE company_id=? AND is_deleted=0"),
        ('outgoing', "SELECT COUNT(*) FROM correspondence WHERE company_id=? AND is_deleted=0 AND type='out'"),
        ('incoming', "SELECT COUNT(*) FROM correspondence WHERE company_id=? AND is_deleted=0 AND type='in'"),
        ('pending',  "SELECT COUNT(*) FROM correspondence WHERE company_id=? AND is_deleted=0 AND status='pending'"),
        ('today',    "SELECT COUNT(*) FROM correspondence WHERE company_id=? AND is_deleted=0 AND date=date('now')"),
    ]:
        stats[key] = conn.execute(sql, (cid,)).fetchone()[0]
    conn.close()
    return jsonify({'success': True, 'data': stats})

# ─── Generate API Key for user ────────────────────────
def generate_api_key_for_user(user_id):
    key = 'ccms_' + secrets.token_urlsafe(32)
    conn = get_db()
    # Add api_key column if not exists
    try:
        conn.execute("ALTER TABLE users ADD COLUMN api_key TEXT")
        conn.commit()
    except: pass
    conn.execute("UPDATE users SET api_key=? WHERE id=?", (key, user_id))
    conn.commit()
    conn.close()
    return key

def get_user_api_key(user_id):
    conn = get_db()
    try:
        row = conn.execute("SELECT api_key FROM users WHERE id=?", (user_id,)).fetchone()
        conn.close()
        return row['api_key'] if row else None
    except:
        conn.close()
        return None
