"""
CCMS — Corporate Communication Management System
نظام إدارة الاتصالات الإدارية المتكامل
Flask Application — Professional Edition 2.0
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, jsonify, send_file, make_response)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import datetime, uuid, json, io

from models import get_db, init_db, now, today, new_id
from i18n import init_i18n, t
from api import api as api_blueprint, generate_api_key_for_user, get_user_api_key
from ai_engine import analyze_correspondence, get_ai_stats
from notifier import (get_company_notification_settings, notify_new_correspondence,
                      notify_due_soon, build_email_html, notify)
from helpers import (get_user_project_ids, get_visible_projects,
                     apply_project_filter, can_delete, can_manage_users,
                     can_manage_projects, get_unread_count,
                     get_pending_workflow_count, create_notification,
                     generate_letter_pdf, generate_excel_report, generate_qr_svg)

# ── App ──────────────────────────────────────────────
app = Flask(__name__, template_folder='templates', static_folder='static')
import os as _os
app.secret_key = _os.environ.get('SECRET_KEY', 'ccms-professional-2025-ibrahim-secure')
app.register_blueprint(api_blueprint)
init_i18n(app)
UPLOAD_FOLDER  = os.path.join(os.path.dirname(__file__), 'instance', 'uploads')
ALLOWED_EXT    = {'pdf','png','jpg','jpeg','doc','docx','xls','xlsx'}
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed(fn):
    return '.' in fn and fn.rsplit('.',1)[1].lower() in ALLOWED_EXT

def save_file(f, prefix='file'):
    ext = f.filename.rsplit('.',1)[1].lower()
    fn  = f"{prefix}_{uuid.uuid4().hex[:8]}.{ext}"
    f.save(os.path.join(UPLOAD_FOLDER, fn))
    return fn, os.path.getsize(os.path.join(UPLOAD_FOLDER, fn))

# ══════════════════════════════════════════════════════
#  AUTH DECORATORS
# ══════════════════════════════════════════════════════
def login_required(f):
    @wraps(f)
    def d(*a,**k):
        if 'user_id' not in session: return redirect(url_for('login'))
        return f(*a,**k)
    return d

def admin_required(f):
    @wraps(f)
    def d(*a,**k):
        if 'user_id' not in session: return redirect(url_for('login'))
        if session.get('role') not in ('super_admin','admin'):
            flash('هذه الصفحة متاحة للمدير فقط','error')
            return redirect(url_for('dashboard'))
        return f(*a,**k)
    return d

def manager_required(f):
    @wraps(f)
    def d(*a,**k):
        if 'user_id' not in session: return redirect(url_for('login'))
        if session.get('role') not in ('super_admin','admin','manager'):
            flash('صلاحية غير كافية','error')
            return redirect(url_for('dashboard'))
        return f(*a,**k)
    return d

# ── Context processor ─────────────────────────────────
@app.context_processor
def inject_globals():
    if 'user_id' not in session:
        return {'current_user':{},'is_admin':False,'is_manager':False,
                'unread':0,'pending_wf':0,'company':{}}
    conn = get_db()
    co   = conn.execute("SELECT * FROM companies WHERE id=?", (session.get('company_id'),)).fetchone()
    conn.close()
    return {
        'current_user': {
            'id':session.get('user_id'), 'username':session.get('username'),
            'full_name':session.get('full_name'), 'role':session.get('role'),
            'all_projects':session.get('all_projects','0'),
            'job_title':session.get('job_title',''),
        },
        'is_admin':   session.get('role') in ('super_admin','admin'),
        'is_manager': session.get('role') in ('super_admin','admin','manager'),
        'can_delete': can_delete(),
        'unread':     get_unread_count(),
        'pending_wf': get_pending_workflow_count(),
        'company':    dict(co) if co else {},
        'today':      __import__('datetime').date.today,
    }

# ── Template filters ──────────────────────────────────
@app.template_filter('ar_date')
def ar_date(v):
    if not v: return '—'
    months = ['','يناير','فبراير','مارس','أبريل','مايو','يونيو',
              'يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر']
    try:
        p = str(v)[:10].split('-')
        return f"{int(p[2])} {months[int(p[1])]} {p[0]}"
    except: return v

@app.template_filter('time_ago')
def time_ago(v):
    if not v: return ''
    try:
        dt  = datetime.datetime.fromisoformat(str(v))
        dif = datetime.datetime.now() - dt
        s   = int(dif.total_seconds())
        if s < 60:    return 'الآن'
        if s < 3600:  return f"منذ {s//60} دقيقة"
        if s < 86400: return f"منذ {s//3600} ساعة"
        return f"منذ {s//86400} يوم"
    except: return v

@app.template_filter('filesize')
def filesize_f(v):
    try:
        v = int(v)
        if v < 1024: return f"{v} B"
        if v < 1048576: return f"{v/1024:.1f} KB"
        return f"{v/1048576:.1f} MB"
    except: return ''

@app.template_filter('priority_label')
def priority_label(v):
    return {'urgent':'عاجل جداً','high':'عالية','normal':'عادية','low':'منخفضة'}.get(v,v)

@app.template_filter('status_label')
def status_label(v):
    return {'draft':'مسودة','pending':'معلق','sent':'مُرسل',
            'received':'مستلم','approved':'معتمد','rejected':'مرفوض',
            'archived':'مؤرشف','cancelled':'ملغى'}.get(v,v)

@app.template_filter('reply_label')
def reply_label(v):
    return {'pending':'في الانتظار','replied':'تم الرد','not_required':'لا يحتاج رداً',
            'overdue':'متأخر'}.get(v,v)


# ══════════════════════════════════════════════════════
#  AUTH
# ══════════════════════════════════════════════════════
@app.route('/login', methods=['GET','POST'])
def login():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        un = request.form.get('username','').strip()
        pw = request.form.get('password','')
        conn = get_db()
        u = conn.execute("""SELECT u.*,c.name as co_name,c.primary_color,c.logo_path
                            FROM users u JOIN companies c ON u.company_id=c.id
                            WHERE u.username=? AND u.is_active=1""", (un,)).fetchone()
        conn.close()
        if u and check_password_hash(u['password_hash'], pw):
            session.update({
                'user_id':u['id'], 'username':u['username'],
                'full_name':u['full_name'], 'role':u['role'],
                'company_id':u['company_id'], 'company_name':u['co_name'],
                'all_projects': u['all_projects'],
                'job_title': u['job_title'] or '',
            })
            # Update last login
            conn = get_db()
            conn.execute("UPDATE users SET last_login=?,login_count=login_count+1 WHERE id=?",
                         (now(), u['id']))
            conn.execute("""INSERT INTO audit_log (id,company_id,user_id,username,action,ip_address,created_at)
                            VALUES (?,?,?,?,?,?,?)""",
                         (new_id(),u['company_id'],u['id'],u['username'],'LOGIN',
                          request.remote_addr, now()))
            conn.commit(); conn.close()
            flash(f"مرحباً {u['full_name']} 👋",'success')
            return redirect(request.args.get('next') or url_for('dashboard'))
        flash('اسم المستخدم أو كلمة المرور غير صحيحة','error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    if 'user_id' in session:
        conn = get_db()
        conn.execute("""INSERT INTO audit_log (id,company_id,user_id,username,action,ip_address,created_at)
                        VALUES (?,?,?,?,?,?,?)""",
                     (new_id(),session.get('company_id'),session['user_id'],
                      session.get('username'),'LOGOUT',request.remote_addr,now()))
        conn.commit(); conn.close()
    session.clear()
    return redirect(url_for('login'))


# ══════════════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════════════
@app.route('/')
@login_required
def dashboard():
    conn = get_db()
    cid  = session['company_id']
    pid_list = get_user_project_ids()

    base = """SELECT c.*,p.name as proj_name,p.color as proj_color,u.full_name as creator_name
              FROM correspondence c
              LEFT JOIN projects p ON c.project_id=p.id
              LEFT JOIN users u ON c.created_by=u.id
              WHERE c.company_id=? AND c.archived=0 AND c.is_deleted=0"""
    sql, params = apply_project_filter(base, [cid], pid_list)
    all_c = conn.execute(sql + " ORDER BY c.date DESC", params).fetchall()

    # KPIs
    total  = len(all_c)
    out_c  = sum(1 for x in all_c if x['type']=='out')
    in_c   = sum(1 for x in all_c if x['type']=='in')
    urgent = sum(1 for x in all_c if x['priority']=='urgent')
    pending_reply = sum(1 for x in all_c if x['reply_status']=='pending' and x['type']=='in')
    drafts = sum(1 for x in all_c if x['status']=='draft')

    # SLA overdue: in-correspondence with reply due > 72h ago
    overdue = []
    for x in all_c:
        if x['type']=='in' and x['reply_status']=='pending' and x['date']:
            try:
                age = (datetime.date.today() - datetime.date.fromisoformat(x['date'][:10])).days
                if age > 3: overdue.append(x)
            except: pass

    # Recent (last 10)
    recent = all_c[:10]

    # Projects summary
    projects = get_visible_projects(conn)

    # Chart data: last 6 months
    monthly = {}
    for i in range(5,-1,-1):
        d = datetime.date.today().replace(day=1) - datetime.timedelta(days=i*28)
        k = d.strftime('%Y-%m')
        monthly[k] = {'label': ar_month(d.month), 'out':0, 'in':0}
    for x in all_c:
        if x['date']:
            k = x['date'][:7]
            if k in monthly:
                monthly[k][x['type'] if x['type'] in ('out','in') else 'out'] += 1

    # Top active projects
    proj_activity = {}
    for x in all_c:
        if x['project_id']:
            proj_activity[x['project_id']] = proj_activity.get(x['project_id'],0)+1

    # Pending workflow tasks for this user
    wf_tasks = conn.execute("""
        SELECT ws.*,c.ref_num,c.subject,c.priority,p.name as proj_name
        FROM workflow_steps ws
        JOIN correspondence c ON ws.correspondence_id=c.id
        LEFT JOIN projects p ON c.project_id=p.id
        WHERE ws.assigned_to=? AND ws.status='pending' AND c.is_deleted=0
        ORDER BY ws.created_at LIMIT 5""", (session['user_id'],)).fetchall()

    # Notifications
    notifs = conn.execute("""SELECT * FROM notifications WHERE user_id=?
                             ORDER BY created_at DESC LIMIT 8""",
                          (session['user_id'],)).fetchall()

    conn.close()
    return render_template('dashboard.html',
        total=total, out_c=out_c, in_c=in_c, urgent=urgent,
        pending_reply=pending_reply, drafts=drafts,
        overdue=overdue, recent=recent, projects=projects,
        monthly=list(monthly.values()), wf_tasks=wf_tasks,
        notifs=notifs, proj_activity=proj_activity)

def ar_month(m):
    return ['','يناير','فبراير','مارس','أبريل','مايو','يونيو',
            'يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر'][m]


# ══════════════════════════════════════════════════════
#  CORRESPONDENCE — List / Create / View / Edit
# ══════════════════════════════════════════════════════
def _corr_query(type_filter=None, archived=0):
    conn = get_db()
    cid  = session['company_id']
    pid_list = get_user_project_ids()

    q        = request.args.get('q','')
    proj     = request.args.get('project','')
    status   = request.args.get('status','')
    priority = request.args.get('priority','')
    cat      = request.args.get('category','')
    reply    = request.args.get('reply','')
    date_from= request.args.get('date_from','')
    date_to  = request.args.get('date_to','')
    page     = max(1, int(request.args.get('page','1')))
    per_page = 20

    base = """SELECT c.*,p.name as proj_name,p.color as proj_color,
                     p.code as proj_code,
                     u.full_name as creator_name,
                     ct.name as contact_name
              FROM correspondence c
              LEFT JOIN projects p  ON c.project_id=p.id
              LEFT JOIN users u     ON c.created_by=u.id
              LEFT JOIN contacts ct ON c.contact_id=ct.id
              WHERE c.company_id=? AND c.archived=? AND c.is_deleted=0"""
    params = [cid, archived]
    sql, params = apply_project_filter(base, params, pid_list)

    if type_filter:
        sql += " AND c.type=?"; params.append(type_filter)
    if q:
        sql += " AND (c.subject LIKE ? OR c.party LIKE ? OR c.ref_num LIKE ? OR c.body LIKE ?)"
        params += [f'%{q}%']*4
    if proj:   sql += " AND c.project_id=?";    params.append(proj)
    if status: sql += " AND c.status=?";        params.append(status)
    if priority: sql += " AND c.priority=?";    params.append(priority)
    if cat:    sql += " AND c.category=?";      params.append(cat)
    if reply:  sql += " AND c.reply_status=?";  params.append(reply)
    if date_from: sql += " AND c.date>=?";      params.append(date_from)
    if date_to:   sql += " AND c.date<=?";      params.append(date_to)

    count_sql = f"SELECT COUNT(*) as c FROM ({sql})"
    total = conn.execute(count_sql, params).fetchone()['c']

    sql += " ORDER BY c.date DESC, c.created_at DESC LIMIT ? OFFSET ?"
    items_raw = conn.execute(sql, params + [per_page, (page-1)*per_page]).fetchall()

    items = []
    for item in items_raw:
        att = conn.execute("SELECT COUNT(*) as c FROM attachments WHERE correspondence_id=?",
                           (item['id'],)).fetchone()['c']
        items.append({'item':item,'att_count':att})

    projects  = get_visible_projects(conn)
    contacts  = conn.execute("SELECT * FROM contacts WHERE company_id=? AND is_active=1 ORDER BY name",
                             (cid,)).fetchall()
    conn.close()
    pages = (total + per_page - 1) // per_page
    return items, projects, contacts, total, page, pages

@app.route('/outgoing')
@login_required
def outgoing():
    items, projects, contacts, total, page, pages = _corr_query('out')
    return render_template('correspondence_list.html',
        items=items, projects=projects, contacts=contacts,
        list_type='out', total=total, page=page, pages=pages,
        q=request.args.get('q',''),
        sel_project=request.args.get('project',''),
        sel_status=request.args.get('status',''),
        sel_priority=request.args.get('priority',''),
        sel_cat=request.args.get('category',''),
        sel_date_from=request.args.get('date_from',''),
        sel_date_to=request.args.get('date_to',''))

@app.route('/incoming')
@login_required
def incoming():
    items, projects, contacts, total, page, pages = _corr_query('in')
    return render_template('correspondence_list.html',
        items=items, projects=projects, contacts=contacts,
        list_type='in', total=total, page=page, pages=pages,
        q=request.args.get('q',''),
        sel_project=request.args.get('project',''),
        sel_status=request.args.get('status',''),
        sel_priority=request.args.get('priority',''),
        sel_reply=request.args.get('reply',''),
        sel_date_from=request.args.get('date_from',''),
        sel_date_to=request.args.get('date_to',''))

@app.route('/internal')
@login_required
def internal():
    items, projects, contacts, total, page, pages = _corr_query('internal')
    return render_template('correspondence_list.html',
        items=items, projects=projects, contacts=contacts,
        list_type='internal', total=total, page=page, pages=pages,
        q=request.args.get('q',''))

@app.route('/correspondence/new', methods=['GET','POST'])
@login_required
def new_correspondence():
    conn    = get_db()
    cid     = session['company_id']
    projects = get_visible_projects(conn)
    contacts = conn.execute("SELECT * FROM contacts WHERE company_id=? AND is_active=1 ORDER BY name",(cid,)).fetchall()
    templates_list = conn.execute("SELECT * FROM templates WHERE company_id=? AND is_active=1 ORDER BY name",(cid,)).fetchall()
    departments = conn.execute("SELECT * FROM departments WHERE company_id=? AND is_active=1 ORDER BY name",(cid,)).fetchall()

    if request.method == 'POST':
        type_       = request.form.get('type','out')
        proj_id     = request.form.get('project_id') or None
        contact_id  = request.form.get('contact_id') or None
        dept_id     = request.form.get('department_id') or None
        subject     = request.form.get('subject','').strip()
        party       = request.form.get('party','').strip()
        party_ref   = request.form.get('party_ref','').strip()
        category    = request.form.get('category','general')
        priority    = request.form.get('priority','normal')
        classification = request.form.get('classification','normal')
        body        = request.form.get('body','').strip()
        action_req  = request.form.get('action_required','').strip()
        date_       = request.form.get('date', today())
        due_date    = request.form.get('due_date','') or None
        status      = request.form.get('status','draft')
        reply_st    = request.form.get('reply_status','pending') if type_=='in' else None
        tags        = json.dumps(request.form.getlist('tags'))

        if not subject or not party:
            flash('يرجى تعبئة الحقول المطلوبة','error')
            conn.close()
            return render_template('correspondence_form.html', projects=projects,
                contacts=contacts, templates=templates_list, departments=departments,
                form=request.form)

        # Generate reference number
        proj_code = 'GEN'
        if proj_id:
            p = conn.execute("SELECT code FROM projects WHERE id=?", (proj_id,)).fetchone()
            if p: proj_code = p['code']
        year = datetime.datetime.now().year
        co_code = conn.execute("SELECT code FROM companies WHERE id=?", (cid,)).fetchone()['code']
        seq = conn.execute("""SELECT COUNT(*)+1 as n FROM correspondence
                              WHERE company_id=? AND type=? AND substr(date,1,4)=?""",
                           (cid, type_, str(year))).fetchone()['n']
        type_code = {'out':'OUT','in':'IN','internal':'INT'}[type_]
        ref_num = f"{co_code}-{proj_code}-{year}-{type_code}-{str(seq).zfill(5)}"

        corr_id = new_id()
        conn.execute("""INSERT INTO correspondence
            (id,company_id,ref_num,type,project_id,department_id,contact_id,
             subject,party,party_ref,category,priority,classification,
             body,action_required,date,due_date,status,reply_status,tags,
             created_by,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (corr_id,cid,ref_num,type_,proj_id,dept_id,contact_id,
             subject,party,party_ref,category,priority,classification,
             body,action_req,date_,due_date,status,reply_st,tags,
             session['user_id'],now()))

        # Handle file attachments (multiple)
        files = request.files.getlist('attachments')
        for f in files:
            if f and f.filename and allowed(f.filename):
                fn, fsize = save_file(f, 'att')
                conn.execute("""INSERT INTO attachments
                    (id,correspondence_id,filename,original_name,file_size,mime_type,uploaded_by,uploaded_at)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (new_id(),corr_id,fn,secure_filename(f.filename),fsize,f.content_type,session['user_id'],now()))

        # Workflow: if status is 'pending' create workflow steps
        if status == 'pending':
            wf_def = conn.execute("SELECT * FROM workflow_definitions WHERE company_id=? AND is_default=1",
                                  (cid,)).fetchone()
            if wf_def:
                steps = json.loads(wf_def['steps_json'])
                for step in steps:
                    conn.execute("""INSERT INTO workflow_steps
                        (id,correspondence_id,step_number,step_name,action_type,
                         assigned_role,status,is_mandatory,created_at)
                        VALUES (?,?,?,?,?,?,?,?,?)""",
                        (new_id(),corr_id,step['step'],step['name'],step['action'],
                         step.get('role','manager'),'pending' if step['step']==1 else 'waiting',
                         1 if step.get('mandatory') else 0, now()))

                conn.execute("UPDATE correspondence SET workflow_id=?,workflow_status='in_review' WHERE id=?",
                             (wf_def['id'],corr_id))

        # Audit log
        conn.execute("""INSERT INTO audit_log
            (id,company_id,user_id,username,action,entity,entity_id,new_value,ip_address,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (new_id(),cid,session['user_id'],session['username'],
             'CREATE','correspondence',corr_id,ref_num,request.remote_addr,now()))

        conn.commit(); conn.close()
        flash(f'✅ تم إنشاء المراسلة <strong>{ref_num}</strong> بنجاح','success')
        return redirect(url_for('view_correspondence', cid=corr_id))

    conn.close()
    return render_template('correspondence_form.html', projects=projects,
        contacts=contacts, templates=templates_list, departments=departments, form={})

@app.route('/correspondence/<cid>')
@login_required
def view_correspondence(cid):
    conn = get_db()
    item = conn.execute("""
        SELECT c.*,p.name as proj_name,p.color as proj_color,p.code as proj_code,
               u.full_name as creator_name, u.job_title as creator_title,
               d.name as dept_name, ct.name as contact_name
        FROM correspondence c
        LEFT JOIN projects p  ON c.project_id=p.id
        LEFT JOIN users u     ON c.created_by=u.id
        LEFT JOIN departments d ON c.department_id=d.id
        LEFT JOIN contacts ct ON c.contact_id=ct.id
        WHERE c.id=? AND c.is_deleted=0""", (cid,)).fetchone()

    if not item or item['company_id'] != session['company_id']:
        flash('المراسلة غير موجودة','error'); conn.close()
        return redirect(url_for('dashboard'))

    pid_list = get_user_project_ids()
    if pid_list is not None and item['project_id'] and item['project_id'] not in pid_list:
        flash('ليس لديك صلاحية عرض هذه المراسلة','error'); conn.close()
        return redirect(url_for('dashboard'))

    attachments   = conn.execute("SELECT a.*,u.full_name as uploader FROM attachments a LEFT JOIN users u ON a.uploaded_by=u.id WHERE a.correspondence_id=? ORDER BY a.uploaded_at", (cid,)).fetchall()
    comments      = conn.execute("SELECT cm.*,u.full_name,u.job_title FROM comments cm JOIN users u ON cm.user_id=u.id WHERE cm.correspondence_id=? ORDER BY cm.created_at", (cid,)).fetchall()
    wf_steps      = conn.execute("SELECT ws.*,u.full_name as assignee_name FROM workflow_steps ws LEFT JOIN users u ON ws.assigned_to=u.id WHERE ws.correspondence_id=? ORDER BY ws.step_number", (cid,)).fetchall()
    related       = conn.execute("SELECT * FROM correspondence WHERE parent_id=? AND is_deleted=0 ORDER BY date", (cid,)).fetchall()

    # QR Data
    qr_data = f"CCMS|{item['ref_num']}|{item['subject']}|{item['date']}|{item['party']}"
    qr_img  = generate_qr_svg(qr_data)

    conn.close()
    return render_template('correspondence_detail.html',
        item=item, attachments=attachments, comments=comments,
        wf_steps=wf_steps, related=related, qr_img=qr_img)

@app.route('/correspondence/<cid>/edit', methods=['GET','POST'])
@login_required
def edit_correspondence(cid):
    conn = get_db()
    co   = session['company_id']
    item = conn.execute("SELECT * FROM correspondence WHERE id=? AND company_id=? AND is_deleted=0",(cid,co)).fetchone()
    if not item:
        flash('المراسلة غير موجودة','error'); conn.close()
        return redirect(url_for('dashboard'))

    pid_list = get_user_project_ids()
    if pid_list is not None and item['project_id'] and item['project_id'] not in pid_list:
        flash('ليس لديك صلاحية تعديل هذه المراسلة','error'); conn.close()
        return redirect(url_for('dashboard'))

    projects    = get_visible_projects(conn)
    contacts    = conn.execute("SELECT * FROM contacts WHERE company_id=? AND is_active=1 ORDER BY name",(co,)).fetchall()
    departments = conn.execute("SELECT * FROM departments WHERE company_id=? AND is_active=1 ORDER BY name",(co,)).fetchall()
    attachments = conn.execute("SELECT * FROM attachments WHERE correspondence_id=?",(cid,)).fetchall()

    if request.method == 'POST':
        old_status = item['status']
        new_status = request.form.get('status', old_status)
        conn.execute("""UPDATE correspondence SET
            project_id=?,department_id=?,contact_id=?,subject=?,party=?,
            party_ref=?,category=?,priority=?,classification=?,body=?,
            action_required=?,date=?,due_date=?,status=?,reply_status=?,updated_at=?
            WHERE id=?""",
            (request.form.get('project_id') or None,
             request.form.get('department_id') or None,
             request.form.get('contact_id') or None,
             request.form.get('subject','').strip(),
             request.form.get('party','').strip(),
             request.form.get('party_ref','').strip(),
             request.form.get('category','general'),
             request.form.get('priority','normal'),
             request.form.get('classification','normal'),
             request.form.get('body','').strip(),
             request.form.get('action_required','').strip(),
             request.form.get('date', today()),
             request.form.get('due_date','') or None,
             new_status,
             request.form.get('reply_status', item['reply_status']),
             now(), cid))

        files = request.files.getlist('attachments')
        for f in files:
            if f and f.filename and allowed(f.filename):
                fn, fsize = save_file(f, 'att')
                conn.execute("INSERT INTO attachments (id,correspondence_id,filename,original_name,file_size,mime_type,uploaded_by,uploaded_at) VALUES (?,?,?,?,?,?,?,?)",
                             (new_id(),cid,fn,secure_filename(f.filename),fsize,f.content_type,session['user_id'],now()))

        conn.execute("""INSERT INTO audit_log
            (id,company_id,user_id,username,action,entity,entity_id,ip_address,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (new_id(),co,session['user_id'],session['username'],'EDIT','correspondence',cid,request.remote_addr,now()))
        conn.commit(); conn.close()
        flash('✅ تم تحديث المراسلة بنجاح','success')
        return redirect(url_for('view_correspondence', cid=cid))

    conn.close()
    return render_template('correspondence_form.html', projects=projects,
        contacts=contacts, departments=departments, item=item,
        attachments=attachments, form=item)

@app.route('/correspondence/<cid>/delete', methods=['POST'])
@login_required
def delete_correspondence(cid):
    if not can_delete():
        flash('ليس لديك صلاحية الحذف','error')
        return redirect(url_for('dashboard'))
    conn = get_db()
    conn.execute("UPDATE correspondence SET is_deleted=1,updated_at=? WHERE id=? AND company_id=?",
                 (now(), cid, session['company_id']))
    conn.execute("""INSERT INTO audit_log (id,company_id,user_id,username,action,entity,entity_id,ip_address,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                 (new_id(),session['company_id'],session['user_id'],session['username'],
                  'DELETE','correspondence',cid,request.remote_addr,now()))
    conn.commit(); conn.close()
    flash('تم حذف المراسلة','info')
    return redirect(url_for('dashboard'))

@app.route('/correspondence/<cid>/archive', methods=['POST'])
@login_required
def archive_correspondence(cid):
    conn = get_db()
    conn.execute("""UPDATE correspondence SET archived=1,archived_date=?,archived_by=?
                    WHERE id=? AND company_id=?""",
                 (now(), session['user_id'], cid, session['company_id']))
    conn.commit(); conn.close()
    flash('✅ تمت أرشفة المراسلة','success')
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/correspondence/<cid>/unarchive', methods=['POST'])
@login_required
def unarchive_correspondence(cid):
    conn = get_db()
    conn.execute("UPDATE correspondence SET archived=0 WHERE id=? AND company_id=?",
                 (cid, session['company_id']))
    conn.commit(); conn.close()
    flash('تم إلغاء الأرشفة','success')
    return redirect(url_for('archive'))


# ══════════════════════════════════════════════════════
#  WORKFLOW ACTIONS
# ══════════════════════════════════════════════════════
@app.route('/workflow/<step_id>/action', methods=['POST'])
@login_required
def workflow_action(step_id):
    conn   = get_db()
    action = request.form.get('action','')  # approve / reject / review
    note   = request.form.get('note','').strip()

    step = conn.execute("SELECT * FROM workflow_steps WHERE id=?", (step_id,)).fetchone()
    if not step:
        flash('الخطوة غير موجودة','error'); conn.close()
        return redirect(url_for('dashboard'))

    corr_id = step['correspondence_id']
    new_status = 'approved' if action == 'approve' else ('rejected' if action == 'reject' else 'done')

    conn.execute("UPDATE workflow_steps SET status=?,completed_at=?,completed_by=?,note=? WHERE id=?",
                 (new_status, now(), session['user_id'], note, step_id))

    if action == 'reject':
        conn.execute("UPDATE correspondence SET workflow_status='rejected',status='rejected' WHERE id=?", (corr_id,))
    else:
        # Move to next step
        next_step = conn.execute("""SELECT * FROM workflow_steps
                                    WHERE correspondence_id=? AND step_number>? AND status='waiting'
                                    ORDER BY step_number LIMIT 1""",
                                 (corr_id, step['step_number'])).fetchone()
        if next_step:
            conn.execute("UPDATE workflow_steps SET status='pending' WHERE id=?", (next_step['id'],))
            # Notify assignee
            if next_step['assigned_to']:
                corr = conn.execute("SELECT ref_num,subject FROM correspondence WHERE id=?", (corr_id,)).fetchone()
                create_notification(next_step['assigned_to'], 'workflow',
                    f"طلب مراجعة: {corr['ref_num']}",
                    f"يتطلب موافقتك: {corr['subject']}",
                    url_for('view_correspondence', cid=corr_id), conn)
        else:
            # All steps done
            conn.execute("UPDATE correspondence SET workflow_status='approved',status='approved' WHERE id=?", (corr_id,))

    conn.commit(); conn.close()
    flash(f'✅ تم تنفيذ الإجراء بنجاح','success')
    return redirect(url_for('view_correspondence', cid=corr_id))


# ══════════════════════════════════════════════════════
#  COMMENTS
# ══════════════════════════════════════════════════════
@app.route('/correspondence/<cid>/comment', methods=['POST'])
@login_required
def add_comment(cid):
    body    = request.form.get('body','').strip()
    private = 1 if request.form.get('is_private') else 0
    if not body:
        flash('يرجى كتابة تعليق','error')
        return redirect(url_for('view_correspondence', cid=cid))
    conn = get_db()
    conn.execute("INSERT INTO comments (id,correspondence_id,user_id,body,is_private,created_at) VALUES (?,?,?,?,?,?)",
                 (new_id(), cid, session['user_id'], body, private, now()))
    conn.commit(); conn.close()
    return redirect(url_for('view_correspondence', cid=cid))


# ══════════════════════════════════════════════════════
#  ATTACHMENTS
# ══════════════════════════════════════════════════════
@app.route('/attachment/<att_id>/download')
@login_required
def download_attachment(att_id):
    conn = get_db()
    att  = conn.execute("SELECT * FROM attachments WHERE id=?", (att_id,)).fetchone()
    conn.close()
    if not att: flash('المرفق غير موجود','error'); return redirect(url_for('dashboard'))
    path = os.path.join(UPLOAD_FOLDER, att['filename'])
    return send_file(path, as_attachment=True, download_name=att['original_name'])

@app.route('/attachment/<att_id>/delete', methods=['POST'])
@login_required
def delete_attachment(att_id):
    if not can_delete():
        flash('ليس لديك صلاحية','error')
        return redirect(request.referrer or url_for('dashboard'))
    conn = get_db()
    att  = conn.execute("SELECT * FROM attachments WHERE id=?", (att_id,)).fetchone()
    cid  = request.form.get('cid','')
    if att:
        fp = os.path.join(UPLOAD_FOLDER, att['filename'])
        if os.path.exists(fp): os.remove(fp)
        conn.execute("DELETE FROM attachments WHERE id=?", (att_id,))
        conn.commit()
    conn.close()
    return redirect(url_for('view_correspondence', cid=cid))


# ══════════════════════════════════════════════════════
#  ARCHIVE
# ══════════════════════════════════════════════════════
@app.route('/archive')
@login_required
def archive():
    conn = get_db()
    cid  = session['company_id']
    pid_list = get_user_project_ids()
    q    = request.args.get('q','')
    base = """SELECT c.*,p.name as proj_name,p.color as proj_color,u.full_name as creator_name
              FROM correspondence c
              LEFT JOIN projects p ON c.project_id=p.id
              LEFT JOIN users u ON c.created_by=u.id
              WHERE c.company_id=? AND c.archived=1 AND c.is_deleted=0"""
    sql, params = apply_project_filter(base, [cid], pid_list)
    if q:
        sql += " AND (c.subject LIKE ? OR c.ref_num LIKE ?)"; params += [f'%{q}%']*2
    sql += " ORDER BY c.archived_date DESC"
    items = conn.execute(sql, params).fetchall()
    conn.close()
    return render_template('archive.html', items=items, q=q)


# ══════════════════════════════════════════════════════
#  PROJECTS
# ══════════════════════════════════════════════════════
@app.route('/projects')
@login_required
def projects():
    conn = get_db()
    projs = get_visible_projects(conn)
    result = []
    for p in projs:
        out_c = conn.execute("SELECT COUNT(*) as c FROM correspondence WHERE project_id=? AND type='out' AND archived=0 AND is_deleted=0",(p['id'],)).fetchone()['c']
        in_c  = conn.execute("SELECT COUNT(*) as c FROM correspondence WHERE project_id=? AND type='in'  AND archived=0 AND is_deleted=0",(p['id'],)).fetchone()['c']
        last  = conn.execute("SELECT date FROM correspondence WHERE project_id=? AND is_deleted=0 ORDER BY date DESC LIMIT 1",(p['id'],)).fetchone()
        result.append({'p':p,'out_c':out_c,'in_c':in_c,'last_activity':last['date'] if last else None})
    conn.close()
    return render_template('projects.html', projects=result)

@app.route('/projects/new', methods=['GET','POST'])
@manager_required
def new_project():
    conn = get_db()
    cid  = session['company_id']
    depts = conn.execute("SELECT * FROM departments WHERE company_id=? AND is_active=1",(cid,)).fetchall()
    managers = conn.execute("SELECT * FROM users WHERE company_id=? AND role IN ('admin','manager','super_admin') AND is_active=1",(cid,)).fetchall()
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        code = request.form.get('code','').strip().upper()
        if not name or not code:
            flash('الاسم والرمز مطلوبان','error')
            conn.close()
            return render_template('project_form.html', form=request.form, depts=depts, managers=managers)
        pid = new_id()
        try:
            conn.execute("""INSERT INTO projects
                (id,company_id,code,name,name_en,description,client,client_contact,
                 location,contract_number,contract_value,currency,start_date,end_date,
                 progress,status,priority,color,manager_id,department_id,created_at,created_by)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pid,cid,code,name,
                 request.form.get('name_en',''),
                 request.form.get('description',''),
                 request.form.get('client',''),
                 request.form.get('client_contact',''),
                 request.form.get('location',''),
                 request.form.get('contract_number',''),
                 float(request.form.get('contract_value','0') or 0),
                 request.form.get('currency','SAR'),
                 request.form.get('start_date','') or None,
                 request.form.get('end_date','') or None,
                 int(request.form.get('progress',0)),
                 request.form.get('status','active'),
                 request.form.get('priority','normal'),
                 request.form.get('color','#00b4d8'),
                 request.form.get('manager_id','') or None,
                 request.form.get('department_id','') or None,
                 now(), session['user_id']))
            conn.commit()
            flash(f'✅ تم إضافة المشروع {name}','success')
            return redirect(url_for('projects'))
        except Exception as e:
            flash(f'رمز المشروع مستخدم مسبقاً أو خطأ: {e}','error')
        finally:
            conn.close()
    conn.close()
    return render_template('project_form.html', form={}, depts=depts, managers=managers)

@app.route('/projects/<pid>/edit', methods=['GET','POST'])
@manager_required
def edit_project(pid):
    conn = get_db()
    proj = conn.execute("SELECT * FROM projects WHERE id=? AND company_id=?", (pid,session['company_id'])).fetchone()
    if not proj: flash('المشروع غير موجود','error'); conn.close(); return redirect(url_for('projects'))
    depts    = conn.execute("SELECT * FROM departments WHERE company_id=? AND is_active=1",(session['company_id'],)).fetchall()
    managers = conn.execute("SELECT * FROM users WHERE company_id=? AND role IN ('admin','manager','super_admin') AND is_active=1",(session['company_id'],)).fetchall()
    if request.method == 'POST':
        conn.execute("""UPDATE projects SET name=?,name_en=?,description=?,client=?,client_contact=?,
                        location=?,contract_number=?,contract_value=?,currency=?,start_date=?,
                        end_date=?,progress=?,status=?,priority=?,color=?,manager_id=?,department_id=?
                        WHERE id=?""",
                     (request.form.get('name'),request.form.get('name_en',''),
                      request.form.get('description',''),request.form.get('client',''),
                      request.form.get('client_contact',''),request.form.get('location',''),
                      request.form.get('contract_number',''),
                      float(request.form.get('contract_value','0') or 0),
                      request.form.get('currency','SAR'),
                      request.form.get('start_date','') or None,
                      request.form.get('end_date','') or None,
                      int(request.form.get('progress',0)),
                      request.form.get('status','active'),
                      request.form.get('priority','normal'),
                      request.form.get('color','#00b4d8'),
                      request.form.get('manager_id','') or None,
                      request.form.get('department_id','') or None, pid))
        conn.commit(); conn.close()
        flash('✅ تم تحديث المشروع','success')
        return redirect(url_for('projects'))
    conn.close()
    return render_template('project_form.html', form=proj, pid=pid, depts=depts, managers=managers)

@app.route('/projects/<pid>/delete', methods=['POST'])
@manager_required
def delete_project(pid):
    conn = get_db()
    conn.execute("UPDATE projects SET is_active=0 WHERE id=? AND company_id=?", (pid,session['company_id']))
    conn.commit(); conn.close()
    flash('تم أرشفة المشروع','info')
    return redirect(url_for('projects'))


# ══════════════════════════════════════════════════════
#  CONTACTS (جهات الاتصال)
# ══════════════════════════════════════════════════════
@app.route('/contacts')
@login_required
def contacts():
    conn = get_db()
    cid  = session['company_id']
    q    = request.args.get('q','')
    sql  = "SELECT * FROM contacts WHERE company_id=? AND is_active=1"
    params = [cid]
    if q:
        sql += " AND (name LIKE ? OR city LIKE ? OR contact_person LIKE ?)"; params += [f'%{q}%']*3
    sql += " ORDER BY name"
    items = conn.execute(sql, params).fetchall()
    result = []
    for c in items:
        cnt = conn.execute("SELECT COUNT(*) as n FROM correspondence WHERE contact_id=? AND is_deleted=0",(c['id'],)).fetchone()['n']
        result.append({'c':c,'corr_count':cnt})
    conn.close()
    return render_template('contacts.html', items=result, q=q)

@app.route('/contacts/new', methods=['GET','POST'])
@login_required
def new_contact():
    conn = get_db()
    cid  = session['company_id']
    if request.method == 'POST':
        ctid = new_id()
        conn.execute("""INSERT INTO contacts
            (id,company_id,name,name_en,org_type,category,address,city,country,
             phone,fax,email,website,contact_person,contact_title,contact_phone,contact_email,notes,created_at,created_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ctid,cid,
             request.form.get('name','').strip(),
             request.form.get('name_en','').strip(),
             request.form.get('org_type','company'),
             request.form.get('category',''),
             request.form.get('address',''),
             request.form.get('city',''),
             request.form.get('country','المملكة العربية السعودية'),
             request.form.get('phone',''),
             request.form.get('fax',''),
             request.form.get('email',''),
             request.form.get('website',''),
             request.form.get('contact_person',''),
             request.form.get('contact_title',''),
             request.form.get('contact_phone',''),
             request.form.get('contact_email',''),
             request.form.get('notes',''),
             now(), session['user_id']))
        conn.commit(); conn.close()
        flash('✅ تمت إضافة جهة الاتصال','success')
        return redirect(url_for('contacts'))
    conn.close()
    return render_template('contact_form.html', form={})

@app.route('/contacts/<ctid>/edit', methods=['GET','POST'])
@login_required
def edit_contact(ctid):
    conn = get_db()
    ct   = conn.execute("SELECT * FROM contacts WHERE id=? AND company_id=?",(ctid,session['company_id'])).fetchone()
    if not ct: flash('جهة الاتصال غير موجودة','error'); conn.close(); return redirect(url_for('contacts'))
    if request.method == 'POST':
        conn.execute("""UPDATE contacts SET name=?,name_en=?,org_type=?,category=?,address=?,city=?,
                        country=?,phone=?,fax=?,email=?,website=?,contact_person=?,contact_title=?,
                        contact_phone=?,contact_email=?,notes=? WHERE id=?""",
                     (request.form.get('name'),request.form.get('name_en',''),
                      request.form.get('org_type','company'),request.form.get('category',''),
                      request.form.get('address',''),request.form.get('city',''),
                      request.form.get('country',''),request.form.get('phone',''),
                      request.form.get('fax',''),request.form.get('email',''),
                      request.form.get('website',''),request.form.get('contact_person',''),
                      request.form.get('contact_title',''),request.form.get('contact_phone',''),
                      request.form.get('contact_email',''),request.form.get('notes',''), ctid))
        conn.commit(); conn.close()
        flash('✅ تم التحديث','success')
        return redirect(url_for('contacts'))
    conn.close()
    return render_template('contact_form.html', form=ct, ctid=ctid)


# ══════════════════════════════════════════════════════
#  REPORTS & ANALYTICS
# ══════════════════════════════════════════════════════
@app.route('/reports')
@login_required
def reports():
    conn = get_db()
    cid  = session['company_id']
    pid_list = get_user_project_ids()

    base = "SELECT * FROM correspondence WHERE company_id=? AND is_deleted=0"
    sql, params = apply_project_filter(base, [cid], pid_list)
    all_c = conn.execute(sql, params).fetchall()

    projs = get_visible_projects(conn)

    # Project stats
    proj_stats = []
    for p in projs:
        items = [c for c in all_c if c['project_id']==p['id']]
        proj_stats.append({
            'name':p['name'],'code':p['code'],'color':p['color'],
            'total':len(items),
            'out':sum(1 for c in items if c['type']=='out'),
            'in': sum(1 for c in items if c['type']=='in'),
            'urgent':sum(1 for c in items if c['priority']=='urgent'),
            'pending':sum(1 for c in items if c['reply_status']=='pending'),
        })

    # Category distribution
    cat_dist = {}
    for c in all_c:
        cat_dist[c['category']] = cat_dist.get(c['category'],0)+1

    # Priority distribution
    pri_dist = {'urgent':0,'high':0,'normal':0,'low':0}
    for c in all_c:
        if c['priority'] in pri_dist:
            pri_dist[c['priority']] += 1

    # Monthly trend (last 12)
    monthly = {}
    for i in range(11,-1,-1):
        d = (datetime.date.today().replace(day=1) - datetime.timedelta(days=i*28))
        k = d.strftime('%Y-%m')
        monthly[k] = {'label':f"{ar_month(d.month)} {d.year}",'out':0,'in':0}
    for c in all_c:
        if c['date']:
            k = c['date'][:7]
            if k in monthly and c['type'] in ('out','in'):
                monthly[k][c['type']] += 1

    # Top parties (external)
    party_count = {}
    for c in all_c:
        party_count[c['party']] = party_count.get(c['party'],0)+1
    top_parties = sorted(party_count.items(), key=lambda x:-x[1])[:10]

    # SLA compliance
    compliant = 0; overdue = 0
    for c in all_c:
        if c['type']=='in' and c['date']:
            try:
                age = (datetime.date.today() - datetime.date.fromisoformat(c['date'][:10])).days
                if c['reply_status']=='replied' or age<=3: compliant+=1
                elif age>3 and c['reply_status']=='pending': overdue+=1
            except: pass

    conn.close()
    return render_template('reports.html',
        proj_stats=proj_stats,
        total=len(all_c),
        out_total=sum(1 for c in all_c if c['type']=='out'),
        in_total= sum(1 for c in all_c if c['type']=='in'),
        archived_total=sum(1 for c in all_c if c['archived']),
        cat_dist=cat_dist, pri_dist=pri_dist,
        monthly=list(monthly.values()),
        top_parties=top_parties,
        compliant=compliant, overdue=overdue)

@app.route('/reports/export/excel')
@login_required
def export_excel():
    conn = get_db()
    cid  = session['company_id']
    pid_list = get_user_project_ids()
    base = """SELECT c.ref_num,c.type,c.subject,c.party,c.category,c.priority,
                     c.status,c.reply_status,c.date,p.name as proj_name
              FROM correspondence c LEFT JOIN projects p ON c.project_id=p.id
              WHERE c.company_id=? AND c.is_deleted=0"""
    sql, params = apply_project_filter(base, [cid], pid_list)
    sql += " ORDER BY c.date DESC"
    rows_raw = conn.execute(sql, params).fetchall()
    conn.close()

    rows = [dict(r) for r in rows_raw]
    columns = [
        {'key':'ref_num','label':'رقم المرجع','width':25},
        {'key':'type','label':'النوع','width':12},
        {'key':'subject','label':'الموضوع','width':40},
        {'key':'party','label':'الجهة','width':30},
        {'key':'proj_name','label':'المشروع','width':25},
        {'key':'category','label':'التصنيف','width':18},
        {'key':'priority','label':'الأولوية','width':15},
        {'key':'status','label':'الحالة','width':15},
        {'key':'reply_status','label':'حالة الرد','width':18},
        {'key':'date','label':'التاريخ','width':15},
    ]
    data = generate_excel_report(rows, columns, 'تقرير المراسلات الإدارية', 'المراسلات')
    return send_file(io.BytesIO(data), as_attachment=True,
                     download_name=f"correspondence_{today()}.xlsx",
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/correspondence/<cid>/pdf')
@login_required
def export_pdf(cid):
    conn = get_db()
    item = conn.execute("SELECT * FROM correspondence WHERE id=? AND is_deleted=0",(cid,)).fetchone()
    if not item:
        conn.close()
        flash('المراسلة غير موجودة','error')
        return redirect(url_for('dashboard'))
    co = conn.execute("SELECT * FROM companies WHERE id=?",(session['company_id'],)).fetchone()
    d  = dict(item)
    if item['project_id']:
        proj = conn.execute("SELECT name FROM projects WHERE id=?",(item['project_id'],)).fetchone()
        d['proj_name'] = proj['name'] if proj else ''
    sender = conn.execute("SELECT full_name,job_title FROM users WHERE id=?",(item['created_by'],)).fetchone()
    if sender:
        d['sender_name']  = sender['full_name']
        d['sender_title'] = sender['job_title'] or ''
    atts    = conn.execute("SELECT filename FROM attachments WHERE correspondence_id=?",(cid,)).fetchall()
    co_d    = dict(co)
    att_d   = [dict(a) for a in atts]
    ref_num = item['ref_num']
    conn.close()
    pdf_data = generate_letter_pdf(d, co_d, attachments=att_d)
    return send_file(io.BytesIO(pdf_data), as_attachment=False,
                     download_name=f"{ref_num}.pdf",
                     mimetype='application/pdf')



# ══════════════════════════════════════════════════════
#  المرحلة الثانية — الذكاء الاصطناعي
# ══════════════════════════════════════════════════════

def get_ai_key(company_id):
    """جلب مفتاح AI من إعدادات الشركة"""
    conn = get_db()
    co = conn.execute("SELECT settings_json FROM companies WHERE id=?", (company_id,)).fetchone()
    conn.close()
    if co and co['settings_json']:
        try:
            return json.loads(co['settings_json']).get('ai_api_key','')
        except: pass
    return ''

@app.route('/correspondence/<cid>/analyze', methods=['POST'])
@login_required
def ai_analyze(cid):
    """تحليل المراسلة بالذكاء الاصطناعي"""
    api_key = get_ai_key(session['company_id'])
    if not api_key:
        return jsonify({'error': 'يرجى إضافة مفتاح Claude API في الإعدادات أولاً'}), 400
    try:
        result = analyze_correspondence(cid, session['company_id'], api_key)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai/stats')
@login_required
def ai_stats():
    """إحصاءات ذكية"""
    api_key = get_ai_key(session['company_id'])
    if not api_key:
        return jsonify({'error': 'مفتاح API غير موجود'}), 400
    try:
        result = get_ai_stats(session['company_id'], api_key)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/correspondence/<cid>/ai-data')
@login_required
def get_ai_data(cid):
    """جلب بيانات AI المحفوظة"""
    conn = get_db()
    ai = conn.execute("SELECT * FROM ai_analysis WHERE correspondence_id=?", (cid,)).fetchone()
    conn.close()
    if not ai:
        return jsonify({'exists': False})
    d = dict(ai)
    d['ai_keywords']     = json.loads(d.get('ai_keywords','[]'))
    d['ai_action_items'] = json.loads(d.get('ai_action_items','[]'))
    return jsonify({'exists': True, 'data': d})

# ══════════════════════════════════════════════════════
#  المرحلة الثانية — الإشعارات الخارجية
# ══════════════════════════════════════════════════════

@app.route('/settings/notifications', methods=['GET','POST'])
@admin_required
def notification_settings_view():
    conn = get_db()
    cid  = session['company_id']
    s    = conn.execute("SELECT * FROM notification_settings WHERE company_id=?", (cid,)).fetchone()

    if request.method == 'POST':
        action = request.form.get('action','save')
        if action == 'test_email':
            settings = dict(s) if s else {}
            # Use form values for test
            test_settings = {
                'email_enabled': 1,
                'smtp_host':  request.form.get('smtp_host',''),
                'smtp_port':  int(request.form.get('smtp_port', 587)),
                'smtp_user':  request.form.get('smtp_user',''),
                'smtp_password': request.form.get('smtp_password',''),
                'smtp_from_name': request.form.get('smtp_from_name','CCMS'),
                'smtp_use_tls': int(request.form.get('smtp_use_tls', 1)),
            }
            from notifier import send_email, build_email_html
            html = build_email_html("✅ اختبار ناجح", ["إعدادات البريد الإلكتروني تعمل بشكل صحيح."])
            ok, err = send_email(test_settings, test_settings['smtp_user'], 'اختبار', 'اختبار CCMS', html)
            if ok:
                flash('✅ تم إرسال رسالة الاختبار بنجاح', 'success')
            else:
                flash(f'❌ فشل الإرسال: {err}', 'error')

        elif action == 'test_whatsapp':
            test_phone = request.form.get('test_phone','')
            test_settings = {
                'whatsapp_enabled': 1,
                'whatsapp_api_url': request.form.get('whatsapp_api_url',''),
                'whatsapp_api_token': request.form.get('whatsapp_api_token',''),
                'whatsapp_phone_id': request.form.get('whatsapp_phone_id',''),
            }
            from notifier import send_whatsapp
            ok, err = send_whatsapp(test_settings, test_phone, '✅ رسالة اختبار من نظام CCMS - الإعدادات تعمل بشكل صحيح.')
            if ok:
                flash('✅ تم إرسال رسالة واتساب التجريبية بنجاح', 'success')
            else:
                flash(f'❌ فشل الإرسال: {err}', 'error')

        else:  # save
            vals = (
                cid,
                int(request.form.get('email_enabled', 0)),
                request.form.get('smtp_host','smtp.gmail.com'),
                int(request.form.get('smtp_port', 587)),
                request.form.get('smtp_user',''),
                request.form.get('smtp_password','') or (s['smtp_password'] if s else ''),
                request.form.get('smtp_from_name',''),
                int(request.form.get('smtp_use_tls', 1)),
                int(request.form.get('whatsapp_enabled', 0)),
                request.form.get('whatsapp_api_url',''),
                request.form.get('whatsapp_api_token','') or (s['whatsapp_api_token'] if s else ''),
                request.form.get('whatsapp_phone_id',''),
                int(request.form.get('notify_new_incoming', 1)),
                int(request.form.get('notify_due_soon', 1)),
                int(request.form.get('notify_overdue', 1)),
                int(request.form.get('notify_workflow', 1)),
                int(request.form.get('notify_assigned', 1)),
                int(request.form.get('due_soon_hours', 24)),
                now(),
            )
            if s:
                conn.execute("""UPDATE notification_settings SET
                    email_enabled=?,smtp_host=?,smtp_port=?,smtp_user=?,smtp_password=?,
                    smtp_from_name=?,smtp_use_tls=?,whatsapp_enabled=?,whatsapp_api_url=?,
                    whatsapp_api_token=?,whatsapp_phone_id=?,notify_new_incoming=?,
                    notify_due_soon=?,notify_overdue=?,notify_workflow=?,notify_assigned=?,
                    due_soon_hours=?,updated_at=? WHERE company_id=?""",
                    vals[1:] + (cid,))
            else:
                conn.execute("""INSERT INTO notification_settings
                    (company_id,email_enabled,smtp_host,smtp_port,smtp_user,smtp_password,
                     smtp_from_name,smtp_use_tls,whatsapp_enabled,whatsapp_api_url,
                     whatsapp_api_token,whatsapp_phone_id,notify_new_incoming,notify_due_soon,
                     notify_overdue,notify_workflow,notify_assigned,due_soon_hours,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", vals)
            conn.commit()
            
            # Also save AI key to company metadata
            ai_key = request.form.get('ai_api_key','')
            if ai_key:
                co = conn.execute("SELECT settings_json FROM companies WHERE id=?", (cid,)).fetchone()
                meta = {}
                if co and co['settings_json']:
                    try: meta = json.loads(co['settings_json'])
                    except: pass
                meta['ai_api_key'] = ai_key
                conn.execute("UPDATE companies SET metadata_json=? WHERE id=?", (json.dumps(meta), cid))
                conn.commit()
            
            flash('✅ تم حفظ الإعدادات بنجاح', 'success')
        
        conn.close()
        return redirect(url_for('notification_settings_view'))

    # GET
    s = conn.execute("SELECT * FROM notification_settings WHERE company_id=?", (cid,)).fetchone()
    co = conn.execute("SELECT settings_json FROM companies WHERE id=?", (cid,)).fetchone()
    ai_key_saved = ''
    if co and co['settings_json']:
        try: ai_key_saved = '****' if json.loads(co['settings_json']).get('ai_api_key') else ''
        except: pass
    
    # Notification logs
    logs = conn.execute("""SELECT * FROM notification_log WHERE company_id=?
        ORDER BY created_at DESC LIMIT 20""", (cid,)).fetchall()
    conn.close()
    return render_template('notification_settings.html', s=s, logs=logs, ai_key_saved=ai_key_saved)

@app.route('/api/send-notification', methods=['POST'])
@login_required
def send_manual_notification():
    """إرسال إشعار يدوي"""
    data     = request.get_json()
    channel  = data.get('channel','email')
    recipient= data.get('recipient','')
    subject  = data.get('subject','إشعار من CCMS')
    body     = data.get('body','')
    cid      = session['company_id']
    settings = get_company_notification_settings(cid)
    
    ok, err = notify(cid, session['user_id'], channel, recipient, subject, body, settings)
    return jsonify({'success': ok, 'error': err})

# ══════════════════════════════════════════════════════
#  المرحلة الثانية — التقارير المتقدمة
# ══════════════════════════════════════════════════════

@app.route('/reports/advanced')
@login_required
def advanced_reports():
    conn = get_db()
    cid  = session['company_id']
    
    # Monthly trend (12 months)
    monthly = conn.execute("""
        SELECT substr(date,1,7) as month, type, COUNT(*) as cnt
        FROM correspondence WHERE company_id=? AND is_deleted=0
        AND date >= date('now','-12 months')
        GROUP BY month, type ORDER BY month
    """, (cid,)).fetchall()

    # By project
    by_project = conn.execute("""
        SELECT p.name, p.color, COUNT(c.id) as cnt,
               SUM(CASE WHEN c.status='approved' THEN 1 ELSE 0 END) as approved,
               SUM(CASE WHEN c.priority IN ('urgent','high') THEN 1 ELSE 0 END) as high_priority
        FROM correspondence c
        JOIN projects p ON c.project_id = p.id
        WHERE c.company_id=? AND c.is_deleted=0
        GROUP BY p.id ORDER BY cnt DESC LIMIT 10
    """, (cid,)).fetchall()

    # By party (top senders/receivers)
    by_party = conn.execute("""
        SELECT party, type, COUNT(*) as cnt
        FROM correspondence WHERE company_id=? AND is_deleted=0
        GROUP BY party, type ORDER BY cnt DESC LIMIT 15
    """, (cid,)).fetchall()

    # SLA compliance
    sla_data = conn.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN due_date IS NOT NULL AND date <= due_date THEN 1 ELSE 0 END) as on_time,
            SUM(CASE WHEN due_date IS NOT NULL AND date > due_date THEN 1 ELSE 0 END) as overdue,
            AVG(CASE WHEN due_date IS NOT NULL 
                THEN CAST(julianday(due_date) - julianday(date) AS INTEGER) END) as avg_days
        FROM correspondence WHERE company_id=? AND is_deleted=0
        AND date >= date('now','-3 months')
    """, (cid,)).fetchone()

    # User productivity
    user_stats = conn.execute("""
        SELECT u.full_name, u.job_title,
               COUNT(c.id) as total,
               SUM(CASE WHEN c.type='out' THEN 1 ELSE 0 END) as out_count,
               SUM(CASE WHEN c.type='in' THEN 1 ELSE 0 END) as in_count,
               SUM(CASE WHEN c.status='approved' THEN 1 ELSE 0 END) as approved
        FROM users u
        LEFT JOIN correspondence c ON u.id = c.created_by AND c.company_id=? AND c.is_deleted=0
        WHERE u.company_id=? AND u.is_active=1
        GROUP BY u.id ORDER BY total DESC
    """, (cid, cid)).fetchall()

    # Category breakdown (from AI if available)
    ai_cats = conn.execute("""
        SELECT ai_category, COUNT(*) as cnt
        FROM ai_analysis a
        JOIN correspondence c ON a.correspondence_id = c.id
        WHERE c.company_id=? AND ai_category IS NOT NULL
        GROUP BY ai_category ORDER BY cnt DESC
    """, (cid,)).fetchall()

    # Priority heatmap by day of week
    heatmap = conn.execute("""
        SELECT strftime('%w', date) as dow, priority, COUNT(*) as cnt
        FROM correspondence WHERE company_id=? AND is_deleted=0
        GROUP BY dow, priority
    """, (cid,)).fetchall()

    conn.close()
    # Convert sqlite Row objects to plain dicts for JSON serialization
    def rows2list(rows):
        return [dict(r) for r in rows]
    
    return render_template('advanced_reports.html',
        monthly=rows2list(monthly),
        by_project=rows2list(by_project),
        by_party=rows2list(by_party),
        sla_data=dict(sla_data) if sla_data else {},
        user_stats=rows2list(user_stats),
        ai_cats=rows2list(ai_cats),
        heatmap=rows2list(heatmap))

# ══════════════════════════════════════════════════════
#  USERS
# ══════════════════════════════════════════════════════
@app.route('/users')
@admin_required
def users():
    conn = get_db()
    cid  = session['company_id']
    user_list = conn.execute("""SELECT u.*,d.name as dept_name FROM users u
                                LEFT JOIN departments d ON u.department_id=d.id
                                WHERE u.company_id=? ORDER BY u.role,u.full_name""",(cid,)).fetchall()
    result = []
    for u in user_list:
        cnt  = conn.execute("SELECT COUNT(*) as c FROM user_projects WHERE user_id=?",(u['id'],)).fetchone()['c']
        lcnt = conn.execute("SELECT COUNT(*) as c FROM correspondence WHERE created_by=? AND is_deleted=0",(u['id'],)).fetchone()['c']
        result.append({'u':u,'proj_count':cnt,'corr_count':lcnt})
    conn.close()
    return render_template('users.html', user_list=result)

@app.route('/users/new', methods=['GET','POST'])
@admin_required
def new_user():
    conn = get_db()
    cid  = session['company_id']
    all_projs = conn.execute("SELECT * FROM projects WHERE company_id=? AND is_active=1 ORDER BY name",(cid,)).fetchall()
    depts     = conn.execute("SELECT * FROM departments WHERE company_id=? AND is_active=1 ORDER BY name",(cid,)).fetchall()
    if request.method == 'POST':
        un = request.form.get('username','').strip()
        if conn.execute("SELECT 1 FROM users WHERE username=? AND company_id=?",(un,cid)).fetchone():
            flash('اسم المستخدم موجود مسبقاً','error')
            conn.close()
            return render_template('user_form.html', form=request.form, all_projects=all_projs, depts=depts, assigned=[])
        uid = new_id()
        all_proj_flag = 1 if (request.form.get('all_projects') or request.form.get('role') in ('admin','super_admin')) else 0
        conn.execute("""INSERT INTO users
            (id,company_id,department_id,username,email,full_name,full_name_en,
             job_title,phone,password_hash,role,is_active,all_projects,created_at,created_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)""",
            (uid,cid,
             request.form.get('department_id','') or None,
             un,
             request.form.get('email',''),
             request.form.get('full_name','').strip(),
             request.form.get('full_name_en','').strip(),
             request.form.get('job_title','').strip(),
             request.form.get('phone','').strip(),
             generate_password_hash(request.form.get('password','')),
             request.form.get('role','user'),
             all_proj_flag, now(), session['user_id']))
        if not all_proj_flag:
            for pid in request.form.getlist('project_ids'):
                conn.execute("INSERT OR IGNORE INTO user_projects (user_id,project_id) VALUES (?,?)",(uid,pid))
        conn.commit(); conn.close()
        flash(f'✅ تم إضافة المستخدم {request.form.get("full_name")}','success')
        return redirect(url_for('users'))
    conn.close()
    return render_template('user_form.html', form={}, all_projects=all_projs, depts=depts, assigned=[])

@app.route('/users/<uid>/edit', methods=['GET','POST'])
@admin_required
def edit_user(uid):
    conn = get_db()
    cid  = session['company_id']
    user = conn.execute("SELECT * FROM users WHERE id=? AND company_id=?",(uid,cid)).fetchone()
    if not user: flash('المستخدم غير موجود','error'); conn.close(); return redirect(url_for('users'))
    all_projs = conn.execute("SELECT * FROM projects WHERE company_id=? AND is_active=1 ORDER BY name",(cid,)).fetchall()
    depts     = conn.execute("SELECT * FROM departments WHERE company_id=? AND is_active=1 ORDER BY name",(cid,)).fetchall()
    assigned  = [r['project_id'] for r in conn.execute("SELECT project_id FROM user_projects WHERE user_id=?",(uid,)).fetchall()]
    if request.method == 'POST':
        role = request.form.get('role','user')
        all_proj_flag = 1 if (request.form.get('all_projects') or role in ('admin','super_admin')) else 0
        upd = """UPDATE users SET department_id=?,email=?,full_name=?,full_name_en=?,
                 job_title=?,phone=?,role=?,is_active=?,all_projects=?"""
        params = [request.form.get('department_id','') or None,
                  request.form.get('email',''),
                  request.form.get('full_name','').strip(),
                  request.form.get('full_name_en','').strip(),
                  request.form.get('job_title','').strip(),
                  request.form.get('phone','').strip(),
                  role, 1 if request.form.get('is_active') else 0, all_proj_flag]
        np = request.form.get('new_password','').strip()
        if np:
            upd += ",password_hash=?"
            params.append(generate_password_hash(np))
        params.append(uid)
        conn.execute(upd + " WHERE id=?", params)
        conn.execute("DELETE FROM user_projects WHERE user_id=?",(uid,))
        if not all_proj_flag:
            for pid in request.form.getlist('project_ids'):
                conn.execute("INSERT OR IGNORE INTO user_projects (user_id,project_id) VALUES (?,?)",(uid,pid))
        conn.commit(); conn.close()
        flash('✅ تم تحديث بيانات المستخدم','success')
        return redirect(url_for('users'))
    conn.close()
    return render_template('user_form.html', form=user, uid=uid, all_projects=all_projs, depts=depts, assigned=assigned)

@app.route('/users/<uid>/delete', methods=['POST'])
@admin_required
def delete_user(uid):
    if uid == session['user_id']:
        flash('لا يمكنك حذف حسابك الخاص','error')
        return redirect(url_for('users'))
    conn = get_db()
    conn.execute("UPDATE users SET is_active=0 WHERE id=? AND company_id=?",(uid,session['company_id']))
    conn.commit(); conn.close()
    flash('تم إلغاء تفعيل المستخدم','info')
    return redirect(url_for('users'))


# ══════════════════════════════════════════════════════
#  NOTIFICATIONS
# ══════════════════════════════════════════════════════
@app.route('/notifications')
@login_required
def notifications():
    conn = get_db()
    notifs = conn.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
                          (session['user_id'],)).fetchall()
    conn.execute("UPDATE notifications SET is_read=1,read_at=? WHERE user_id=? AND is_read=0",
                 (now(), session['user_id']))
    conn.commit(); conn.close()
    return render_template('notifications.html', notifs=notifs)


# ══════════════════════════════════════════════════════
#  SETTINGS
# ══════════════════════════════════════════════════════
@app.route('/settings', methods=['GET','POST'])
@admin_required
def settings():
    conn = get_db()
    cid  = session['company_id']
    co   = conn.execute("SELECT * FROM companies WHERE id=?",(cid,)).fetchone()
    depts = conn.execute("SELECT * FROM departments WHERE company_id=? ORDER BY name",(cid,)).fetchall()
    wf_defs = conn.execute("SELECT * FROM workflow_definitions WHERE company_id=? ORDER BY name",(cid,)).fetchall()
    sla_rules = conn.execute("SELECT * FROM sla_rules WHERE company_id=? ORDER BY priority",(cid,)).fetchall()

    if request.method == 'POST':
        action = request.form.get('action','company')
        if action == 'company':
            conn.execute("""UPDATE companies SET name=?,name_en=?,cr_number=?,vat_number=?,
                            address=?,city=?,phone=?,fax=?,email=?,website=?,po_box=?,
                            primary_color=?,secondary_color=? WHERE id=?""",
                         (request.form.get('name'),request.form.get('name_en',''),
                          request.form.get('cr_number',''),request.form.get('vat_number',''),
                          request.form.get('address',''),request.form.get('city',''),
                          request.form.get('phone',''),request.form.get('fax',''),
                          request.form.get('email',''),request.form.get('website',''),
                          request.form.get('po_box',''),
                          request.form.get('primary_color','#00b4d8'),
                          request.form.get('secondary_color','#0077b6'), cid))
            logo = request.files.get('logo')
            if logo and logo.filename:
                ext = logo.filename.rsplit('.',1)[-1].lower()
                if ext in {'png','jpg','jpeg','svg','webp'}:
                    fn  = f"logo_{cid}.{ext}"
                    logo.save(os.path.join(UPLOAD_FOLDER, fn))
                    conn.execute("UPDATE companies SET logo_path=? WHERE id=?", (fn, cid))
            conn.commit()
            flash('✅ تم حفظ إعدادات الشركة','success')

        elif action == 'dept':
            dept_name = request.form.get('dept_name','').strip()
            dept_code = request.form.get('dept_code','').strip().upper()
            if dept_name and dept_code:
                conn.execute("INSERT INTO departments (id,company_id,name,name_en,code,created_at) VALUES (?,?,?,?,?,?)",
                             (new_id(),cid,dept_name,request.form.get('dept_name_en',''),dept_code,now()))
                conn.commit()
                flash('✅ تمت إضافة القسم','success')

        return redirect(url_for('settings'))

    conn.close()
    return render_template('settings.html', co=co, depts=depts, wf_defs=wf_defs, sla_rules=sla_rules)


# ══════════════════════════════════════════════════════
#  API — JSON endpoints
# ══════════════════════════════════════════════════════
@app.route('/api/notifications/count')
@login_required
def api_notif_count():
    return jsonify({'count': get_unread_count()})

@app.route('/api/notifications/mark-read', methods=['POST'])
@login_required
def api_mark_read():
    conn = get_db()
    conn.execute("UPDATE notifications SET is_read=1,read_at=? WHERE user_id=?",(now(),session['user_id']))
    conn.commit(); conn.close()
    return jsonify({'ok':True})

@app.route('/api/contacts/search')
@login_required
def api_contacts_search():
    q    = request.args.get('q','')
    conn = get_db()
    rows = conn.execute("SELECT id,name,contact_person,phone FROM contacts WHERE company_id=? AND name LIKE ? LIMIT 10",
                        (session['company_id'], f'%{q}%')).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/templates/<tid>')
@login_required
def api_get_template(tid):
    conn = get_db()
    t = conn.execute("SELECT * FROM templates WHERE id=? AND company_id=?",(tid,session['company_id'])).fetchone()
    conn.close()
    if not t: return jsonify({'error':'not found'}),404
    return jsonify(dict(t))

@app.route('/api/dashboard/stats')
@login_required
def api_dashboard_stats():
    conn = get_db()
    cid  = session['company_id']
    pid_list = get_user_project_ids()
    base = "SELECT type,priority,reply_status,status FROM correspondence WHERE company_id=? AND archived=0 AND is_deleted=0"
    sql, params = apply_project_filter(base, [cid], pid_list)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return jsonify({
        'total': len(rows),
        'out':   sum(1 for r in rows if r['type']=='out'),
        'in':    sum(1 for r in rows if r['type']=='in'),
        'urgent':sum(1 for r in rows if r['priority']=='urgent'),
        'pending':sum(1 for r in rows if r['reply_status']=='pending'),
    })


# ══════════════════════════════════════════════════════
#  المرحلة الثالثة — Multi-tenant + API Docs + Email Ingestion
# ══════════════════════════════════════════════════════

# ─── API Documentation ────────────────────────────────
@app.route('/api-docs')
@admin_required
def api_docs():
    from api import get_user_api_key, generate_api_key_for_user
    user_id = session['user_id']
    api_key = get_user_api_key(user_id)
    base_url = request.host_url.rstrip('/')
    return render_template('api_docs.html', api_key=api_key, base_url=base_url)

@app.route('/api-docs/generate-key', methods=['POST'])
@admin_required
def generate_api_key():
    from api import generate_api_key_for_user
    key = generate_api_key_for_user(session['user_id'])
    flash('✅ تم إنشاء مفتاح API جديد بنجاح', 'success')
    return redirect(url_for('api_docs'))

# ─── Multi-tenant Admin ───────────────────────────────
@app.route('/super-admin')
@login_required
def super_admin():
    # Only super admin (first user ever created, id=1 or role=super_admin)
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    if not user or user['role'] not in ('super_admin', 'admin'):
        conn.close()
        flash('غير مصرح لك بالوصول', 'error')
        return redirect(url_for('dashboard'))
    
    companies = conn.execute("""
        SELECT c.*,
               (SELECT COUNT(*) FROM users WHERE company_id=c.id AND is_active=1) as user_count,
               (SELECT COUNT(*) FROM correspondence WHERE company_id=c.id AND is_deleted=0) as corr_count,
               (SELECT COUNT(*) FROM projects WHERE company_id=c.id AND is_active=1) as proj_count
        FROM companies c ORDER BY c.created_at DESC
    """).fetchall()
    conn.close()
    return render_template('super_admin.html', companies=companies)

@app.route('/super-admin/company/new', methods=['GET','POST'])
@admin_required
def new_company():
    if request.method == 'POST':
        conn = get_db()
        import re
        name = request.form.get('name','').strip()
        code = request.form.get('code','').strip().upper()
        
        if not name or not code:
            flash('الاسم والكود مطلوبان', 'error')
            return redirect(url_for('new_company'))
        
        cid = new_id()
        conn.execute("""INSERT INTO companies
            (id,name,code,email,phone,country,city,is_active,created_at)
            VALUES (?,?,?,?,?,?,?,1,?)""",
            (cid, name, code,
             request.form.get('email',''),
             request.form.get('phone',''),
             request.form.get('country','SA'),
             request.form.get('city',''),
             now()))
        
        # Create default admin for this company
        admin_pass = request.form.get('admin_password','Admin@2025')
        from werkzeug.security import generate_password_hash
        uid = new_id()
        conn.execute("""INSERT INTO users
            (id,company_id,username,password_hash,full_name,role,is_active,created_at)
            VALUES (?,?,?,?,?,?,1,?)""",
            (uid, cid,
             request.form.get('admin_username', code.lower()+'_admin'),
             generate_password_hash(admin_pass),
             request.form.get('admin_name', name + ' - المدير'),
             'admin', now()))
        
        # Create default department
        conn.execute("INSERT INTO departments (id,company_id,name,code,is_active,created_at) VALUES (?,?,?,?,1,?)",
                     (new_id(), cid, 'الإدارة العامة', 'MGMT', now()))
        
        conn.commit()
        conn.close()
        flash(f'✅ تم إنشاء الشركة "{name}" بنجاح. بيانات الدخول: {request.form.get("admin_username", code.lower()+"_admin")} / {admin_pass}', 'success')
        return redirect(url_for('super_admin'))
    
    return render_template('company_form.html')

@app.route('/super-admin/switch/<company_id>', methods=['POST'])
@admin_required
def switch_company(company_id):
    """Super admin switches to manage another company"""
    conn = get_db()
    co = conn.execute("SELECT * FROM companies WHERE id=?", (company_id,)).fetchone()
    conn.close()
    if co:
        session['company_id'] = company_id
        session['company_name'] = co['name']
        flash(f'تم التبديل إلى شركة: {co["name"]}', 'info')
    return redirect(url_for('dashboard'))

# ─── Email Ingestion ──────────────────────────────────
@app.route('/email-ingestion')
@admin_required
def email_ingestion():
    conn = get_db()
    cid = session['company_id']
    # Get settings
    co = conn.execute("SELECT settings_json FROM companies WHERE id=?", (cid,)).fetchone()
    settings = {}
    if co and co['settings_json']:
        try: settings = json.loads(co['settings_json'])
        except: pass
    email_cfg = settings.get('email_ingestion', {})
    
    # Recent ingested
    recent = conn.execute("""
        SELECT * FROM correspondence 
        WHERE company_id=? AND is_deleted=0 
        AND metadata_json LIKE '%"source":"email"%'
        ORDER BY created_at DESC LIMIT 20
    """, (cid,)).fetchall()
    conn.close()
    return render_template('email_ingestion.html', cfg=email_cfg, recent=recent)

@app.route('/email-ingestion/save', methods=['POST'])
@admin_required
def save_email_ingestion():
    conn = get_db()
    cid = session['company_id']
    co = conn.execute("SELECT settings_json FROM companies WHERE id=?", (cid,)).fetchone()
    settings = {}
    if co and co['settings_json']:
        try: settings = json.loads(co['settings_json'])
        except: pass
    
    settings['email_ingestion'] = {
        'enabled': 1 if request.form.get('enabled') else 0,
        'imap_host': request.form.get('imap_host',''),
        'imap_port': int(request.form.get('imap_port', 993)),
        'imap_user': request.form.get('imap_user',''),
        'imap_password': request.form.get('imap_password','') or settings.get('email_ingestion',{}).get('imap_password',''),
        'imap_folder': request.form.get('imap_folder','INBOX'),
        'auto_category': request.form.get('auto_category','incoming'),
        'mark_read': int(request.form.get('mark_read', 1)),
        'check_interval': int(request.form.get('check_interval', 15)),
    }
    conn.execute("UPDATE companies SET settings_json=? WHERE id=?", (json.dumps(settings), cid))
    conn.commit()
    conn.close()
    flash('✅ تم حفظ إعدادات استقبال البريد', 'success')
    return redirect(url_for('email_ingestion'))

@app.route('/email-ingestion/fetch', methods=['POST'])
@admin_required
def fetch_emails_now():
    """Manually trigger email fetch"""
    from email_ingestor import fetch_and_import
    conn = get_db()
    cid = session['company_id']
    co = conn.execute("SELECT settings_json FROM companies WHERE id=?", (cid,)).fetchone()
    conn.close()
    settings = {}
    if co and co['settings_json']:
        try: settings = json.loads(co['settings_json'])
        except: pass
    cfg = settings.get('email_ingestion', {})
    if not cfg.get('enabled') or not cfg.get('imap_host'):
        return jsonify({'error': 'إعدادات IMAP غير مكتملة'}), 400
    try:
        count = fetch_and_import(cid, session['user_id'], cfg)
        return jsonify({'success': True, 'imported': count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── Offline Page ─────────────────────────────────────
@app.route('/offline')
def offline():
    return render_template('offline.html')

def _offline_old():
    return """<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>غير متصل — CCMS</title>
<style>
body{font-family:'Cairo',sans-serif;background:#030b1f;color:#e2f0fb;
  display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;text-align:center}
.container{padding:40px 20px}
.icon{font-size:80px;margin-bottom:24px}
h1{font-size:24px;margin-bottom:12px}
p{color:#4a7fa5;margin-bottom:24px}
button{background:linear-gradient(135deg,#00b4d8,#06ffa5);color:#000;border:none;
  padding:12px 28px;border-radius:8px;font-size:15px;cursor:pointer;font-family:inherit}
</style></head>
<body><div class="container">
  <div class="icon">📡</div>
  <h1>أنت غير متصل بالإنترنت</h1>
  <p>تحقق من اتصالك ثم حاول مجدداً</p>
  <button onclick="location.reload()">🔄 إعادة المحاولة</button>
</div></body></html>"""


if __name__ == '__main__':
    init_db()
    print("=" * 60)
    print("  🏢 نظام إدارة الاتصالات الإدارية المتكامل")
    print("  CCMS — Corporate Communication Management System")
    print("  Version 2.0 Professional Edition")
    print("=" * 60)
    print("  🌐 URL      : http://localhost:5000")
    print("  🔑 Admin    : admin / Admin@2025")
    print("  👤 Manager  : pm_manager / User@2025")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)
