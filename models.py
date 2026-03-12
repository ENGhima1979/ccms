"""
نظام إدارة الاتصالات الإدارية المتكامل
Corporate Communication Management System (CCMS)
Version 2.0 — Professional Edition
"""
import sqlite3, os, datetime, uuid, hashlib, json
from functools import wraps
from flask import session, redirect, url_for, flash, request

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'ccms.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)  # 30s timeout لمنع database locked
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # WAL mode يسمح بقراءات متزامنة
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def now():
    return datetime.datetime.now().isoformat(timespec='seconds')

def today():
    return datetime.date.today().isoformat()

def new_id():
    return str(uuid.uuid4())

# ══════════════════════════════════════════════════════
#  SCHEMA — Complete Professional Database
# ══════════════════════════════════════════════════════
SCHEMA = """
-- ─────────────────────────────────────────
--  شركات / مستأجرون (Multi-tenant ready)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS companies (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    name_en       TEXT,
    code          TEXT UNIQUE NOT NULL,
    cr_number     TEXT,
    vat_number    TEXT,
    address       TEXT,
    address_en    TEXT,
    city          TEXT,
    country       TEXT DEFAULT 'المملكة العربية السعودية',
    phone         TEXT,
    fax           TEXT,
    email         TEXT,
    website       TEXT,
    po_box        TEXT,
    logo_path     TEXT,
    stamp_path    TEXT,
    letterhead_html TEXT,
    primary_color TEXT DEFAULT '#00b4d8',
    secondary_color TEXT DEFAULT '#0077b6',
    is_active     INTEGER DEFAULT 1,
    subscription_plan TEXT DEFAULT 'business',
    subscription_expiry TEXT,
    created_at    TEXT NOT NULL,
    settings_json TEXT DEFAULT '{}'
);

-- ─────────────────────────────────────────
--  أقسام / إدارات
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS departments (
    id          TEXT PRIMARY KEY,
    company_id  TEXT NOT NULL REFERENCES companies(id),
    name        TEXT NOT NULL,
    name_en     TEXT,
    code        TEXT NOT NULL,
    manager_id  TEXT,
    parent_id   TEXT REFERENCES departments(id),
    color       TEXT DEFAULT '#00b4d8',
    is_active   INTEGER DEFAULT 1,
    created_at  TEXT NOT NULL
);

-- ─────────────────────────────────────────
--  مستخدمون
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    company_id      TEXT NOT NULL REFERENCES companies(id),
    department_id   TEXT REFERENCES departments(id),
    username        TEXT NOT NULL,
    email           TEXT,
    full_name       TEXT NOT NULL,
    full_name_en    TEXT,
    job_title       TEXT,
    phone           TEXT,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'user',
    permissions_json TEXT DEFAULT '{}',
    is_active       INTEGER DEFAULT 1,
    all_projects    INTEGER DEFAULT 0,
    avatar_path     TEXT,
    signature_path  TEXT,
    last_login      TEXT,
    login_count     INTEGER DEFAULT 0,
    theme           TEXT DEFAULT 'dark',
    notifications_json TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL,
    created_by      TEXT,
    UNIQUE(company_id, username)
);

-- ─────────────────────────────────────────
--  مشاريع
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS projects (
    id              TEXT PRIMARY KEY,
    company_id      TEXT NOT NULL REFERENCES companies(id),
    code            TEXT NOT NULL,
    name            TEXT NOT NULL,
    name_en         TEXT,
    description     TEXT,
    client          TEXT,
    client_contact  TEXT,
    location        TEXT,
    contract_number TEXT,
    contract_value  REAL,
    currency        TEXT DEFAULT 'SAR',
    start_date      TEXT,
    end_date        TEXT,
    actual_end_date TEXT,
    progress        INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'active',
    priority        TEXT DEFAULT 'normal',
    color           TEXT DEFAULT '#00b4d8',
    manager_id      TEXT REFERENCES users(id),
    department_id   TEXT REFERENCES departments(id),
    tags            TEXT DEFAULT '[]',
    is_active       INTEGER DEFAULT 1,
    created_at      TEXT NOT NULL,
    created_by      TEXT REFERENCES users(id),
    UNIQUE(company_id, code)
);

-- ─────────────────────────────────────────
--  صلاحيات المستخدم على المشاريع
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_projects (
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    role       TEXT DEFAULT 'member',
    PRIMARY KEY(user_id, project_id)
);


-- ─────────────────────────────────────────
--  صلاحيات المراسلات الدقيقة
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS correspondence_permissions (
    id                  TEXT PRIMARY KEY,
    correspondence_id   TEXT NOT NULL REFERENCES correspondence(id) ON DELETE CASCADE,
    user_id             TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission_level    INTEGER NOT NULL DEFAULT 1,
    granted_by          TEXT REFERENCES users(id),
    created_at          TEXT NOT NULL,
    UNIQUE(correspondence_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_corr_perm ON correspondence_permissions(correspondence_id);
CREATE INDEX IF NOT EXISTS idx_user_perm ON correspondence_permissions(user_id);

-- ─────────────────────────────────────────
--  جهات التواصل الخارجية
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS contacts (
    id            TEXT PRIMARY KEY,
    company_id    TEXT NOT NULL REFERENCES companies(id),
    name          TEXT NOT NULL,
    name_en       TEXT,
    org_type      TEXT DEFAULT 'company',
    category      TEXT,
    address       TEXT,
    city          TEXT,
    country       TEXT,
    phone         TEXT,
    fax           TEXT,
    email         TEXT,
    website       TEXT,
    contact_person TEXT,
    contact_title  TEXT,
    contact_phone  TEXT,
    contact_email  TEXT,
    notes         TEXT,
    is_active     INTEGER DEFAULT 1,
    created_at    TEXT NOT NULL,
    created_by    TEXT REFERENCES users(id)
);

-- ─────────────────────────────────────────
--  قوالب الخطابات
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS templates (
    id            TEXT PRIMARY KEY,
    company_id    TEXT NOT NULL REFERENCES companies(id),
    name          TEXT NOT NULL,
    category      TEXT NOT NULL,
    corr_type     TEXT NOT NULL DEFAULT 'out',
    subject_template TEXT,
    body_template TEXT NOT NULL,
    variables_json TEXT DEFAULT '[]',
    is_active     INTEGER DEFAULT 1,
    usage_count   INTEGER DEFAULT 0,
    created_at    TEXT NOT NULL,
    created_by    TEXT REFERENCES users(id)
);

-- ─────────────────────────────────────────
--  تعريفات سير العمل
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS workflow_definitions (
    id            TEXT PRIMARY KEY,
    company_id    TEXT NOT NULL REFERENCES companies(id),
    name          TEXT NOT NULL,
    category      TEXT,
    steps_json    TEXT NOT NULL DEFAULT '[]',
    is_active     INTEGER DEFAULT 1,
    is_default    INTEGER DEFAULT 0,
    created_at    TEXT NOT NULL,
    created_by    TEXT REFERENCES users(id)
);

-- ─────────────────────────────────────────
--  المراسلات — الجدول المحوري
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS correspondence (
    id              TEXT PRIMARY KEY,
    company_id      TEXT NOT NULL REFERENCES companies(id),
    ref_num         TEXT NOT NULL,
    internal_ref    TEXT,
    type            TEXT NOT NULL CHECK(type IN ('out','in','internal')),
    direction       TEXT DEFAULT 'external',
    project_id      TEXT REFERENCES projects(id),
    department_id   TEXT REFERENCES departments(id),
    contact_id      TEXT REFERENCES contacts(id),
    subject         TEXT NOT NULL,
    subject_en      TEXT,
    party           TEXT NOT NULL,
    party_ref       TEXT,
    category        TEXT NOT NULL,
    subcategory     TEXT,
    priority        TEXT NOT NULL DEFAULT 'normal',
    classification  TEXT DEFAULT 'normal',
    body            TEXT,
    body_en         TEXT,
    action_required TEXT,
    due_date        TEXT,
    response_deadline TEXT,
    date            TEXT NOT NULL,
    received_date   TEXT,
    status          TEXT NOT NULL DEFAULT 'draft',
    workflow_status TEXT DEFAULT 'pending',
    workflow_id     TEXT REFERENCES workflow_definitions(id),
    current_step    INTEGER DEFAULT 0,
    reply_status    TEXT DEFAULT 'pending',
    reply_date      TEXT,
    related_ref     TEXT,
    parent_id       TEXT REFERENCES correspondence(id),
    tags            TEXT DEFAULT '[]',
    archived        INTEGER DEFAULT 0,
    archived_date   TEXT,
    archived_by     TEXT REFERENCES users(id),
    is_deleted      INTEGER DEFAULT 0,
    created_by      TEXT REFERENCES users(id),
    assigned_to     TEXT REFERENCES users(id),
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    metadata_json   TEXT DEFAULT '{}',
    UNIQUE(company_id, ref_num)
);

-- ─────────────────────────────────────────
--  مراحل سير العمل للمراسلات
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS workflow_steps (
    id                TEXT PRIMARY KEY,
    correspondence_id TEXT NOT NULL REFERENCES correspondence(id) ON DELETE CASCADE,
    step_number       INTEGER NOT NULL,
    step_name         TEXT NOT NULL,
    action_type       TEXT NOT NULL,
    assigned_to       TEXT REFERENCES users(id),
    assigned_role     TEXT,
    status            TEXT DEFAULT 'pending',
    due_date          TEXT,
    completed_at      TEXT,
    completed_by      TEXT REFERENCES users(id),
    note              TEXT,
    is_mandatory      INTEGER DEFAULT 1,
    created_at        TEXT NOT NULL
);

-- ─────────────────────────────────────────
--  المرفقات
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS attachments (
    id                TEXT PRIMARY KEY,
    correspondence_id TEXT NOT NULL REFERENCES correspondence(id) ON DELETE CASCADE,
    filename          TEXT NOT NULL,
    original_name     TEXT NOT NULL,
    file_size         INTEGER DEFAULT 0,
    mime_type         TEXT,
    category          TEXT DEFAULT 'attachment',
    description       TEXT,
    is_main           INTEGER DEFAULT 0,
    uploaded_by       TEXT REFERENCES users(id),
    uploaded_at       TEXT NOT NULL
);

-- ─────────────────────────────────────────
--  التعليقات والملاحظات الداخلية
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS comments (
    id                TEXT PRIMARY KEY,
    correspondence_id TEXT NOT NULL REFERENCES correspondence(id) ON DELETE CASCADE,
    user_id           TEXT NOT NULL REFERENCES users(id),
    body              TEXT NOT NULL,
    is_private        INTEGER DEFAULT 0,
    mentioned_users   TEXT DEFAULT '[]',
    created_at        TEXT NOT NULL,
    updated_at        TEXT
);

-- ─────────────────────────────────────────
--  الإشعارات
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notifications (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type        TEXT NOT NULL,
    title       TEXT NOT NULL,
    body        TEXT,
    link        TEXT,
    is_read     INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL,
    read_at     TEXT
);

-- ─────────────────────────────────────────
--  سجل التدقيق
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id          TEXT PRIMARY KEY,
    company_id  TEXT,
    user_id     TEXT,
    username    TEXT,
    action      TEXT NOT NULL,
    entity      TEXT,
    entity_id   TEXT,
    old_value   TEXT,
    new_value   TEXT,
    ip_address  TEXT,
    user_agent  TEXT,
    created_at  TEXT NOT NULL
);

-- ─────────────────────────────────────────
--  SLA (مستويات خدمة الاستجابة)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sla_rules (
    id          TEXT PRIMARY KEY,
    company_id  TEXT NOT NULL REFERENCES companies(id),
    name        TEXT NOT NULL,
    category    TEXT,
    priority    TEXT NOT NULL,
    response_hours INTEGER NOT NULL DEFAULT 24,
    escalate_to TEXT REFERENCES users(id),
    is_active   INTEGER DEFAULT 1,
    created_at  TEXT NOT NULL
);

-- ─────────────────────────────────────────
--  التفويضات المؤقتة
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS delegations (
    id            TEXT PRIMARY KEY,
    from_user_id  TEXT NOT NULL REFERENCES users(id),
    to_user_id    TEXT NOT NULL REFERENCES users(id),
    reason        TEXT,
    start_date    TEXT NOT NULL,
    end_date      TEXT NOT NULL,
    is_active     INTEGER DEFAULT 1,
    created_at    TEXT NOT NULL
);

-- ─────────────────────────────────────────
--  Indexes للأداء
-- ─────────────────────────────────────────

-- ═══════════════════════════════════════════════════════
--  المرحلة الثانية — جداول الذكاء الاصطناعي والإشعارات
-- ═══════════════════════════════════════════════════════

-- تحليلات الذكاء الاصطناعي للمراسلات
CREATE TABLE IF NOT EXISTS ai_analysis (
    id                TEXT PRIMARY KEY,
    correspondence_id TEXT NOT NULL REFERENCES correspondence(id) ON DELETE CASCADE,
    ai_category       TEXT,
    ai_subcategory    TEXT,
    ai_priority       TEXT,
    ai_sentiment      TEXT,
    ai_summary        TEXT,
    ai_suggested_reply TEXT,
    ai_keywords       TEXT DEFAULT '[]',
    ai_action_items   TEXT DEFAULT '[]',
    ai_confidence     REAL DEFAULT 0.0,
    model_used        TEXT DEFAULT 'claude-sonnet-4-5',
    tokens_used       INTEGER DEFAULT 0,
    created_at        TEXT NOT NULL,
    updated_at        TEXT
);

-- إعدادات الإشعارات لكل شركة
CREATE TABLE IF NOT EXISTS notification_settings (
    id              TEXT PRIMARY KEY,
    company_id      TEXT NOT NULL REFERENCES companies(id),
    -- إعدادات البريد الإلكتروني
    email_enabled   INTEGER DEFAULT 0,
    smtp_host       TEXT DEFAULT 'smtp.gmail.com',
    smtp_port       INTEGER DEFAULT 587,
    smtp_user       TEXT,
    smtp_password   TEXT,
    smtp_from_name  TEXT,
    smtp_use_tls    INTEGER DEFAULT 1,
    -- إعدادات واتساب
    whatsapp_enabled     INTEGER DEFAULT 0,
    whatsapp_api_url     TEXT,
    whatsapp_api_token   TEXT,
    whatsapp_phone_id    TEXT,
    -- قواعد الإشعارات
    notify_new_incoming  INTEGER DEFAULT 1,
    notify_due_soon      INTEGER DEFAULT 1,
    notify_overdue       INTEGER DEFAULT 1,
    notify_workflow      INTEGER DEFAULT 1,
    notify_assigned      INTEGER DEFAULT 1,
    due_soon_hours       INTEGER DEFAULT 24,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    UNIQUE(company_id)
);

-- سجل إرسال الإشعارات الخارجية
CREATE TABLE IF NOT EXISTS notification_log (
    id              TEXT PRIMARY KEY,
    company_id      TEXT,
    user_id         TEXT,
    channel         TEXT NOT NULL,
    recipient       TEXT NOT NULL,
    subject         TEXT,
    body            TEXT,
    status          TEXT DEFAULT 'pending',
    error_msg       TEXT,
    sent_at         TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_corr ON ai_analysis(correspondence_id);
CREATE INDEX IF NOT EXISTS idx_notlog_company ON notification_log(company_id);
CREATE INDEX IF NOT EXISTS idx_corr_company    ON correspondence(company_id);
CREATE INDEX IF NOT EXISTS idx_corr_project    ON correspondence(project_id);
CREATE INDEX IF NOT EXISTS idx_corr_type       ON correspondence(type);
CREATE INDEX IF NOT EXISTS idx_corr_status     ON correspondence(status);
CREATE INDEX IF NOT EXISTS idx_corr_date       ON correspondence(date);
CREATE INDEX IF NOT EXISTS idx_corr_archived   ON correspondence(archived);
CREATE INDEX IF NOT EXISTS idx_notif_user      ON notifications(user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_audit_entity    ON audit_log(entity, entity_id);
CREATE INDEX IF NOT EXISTS idx_wf_corr         ON workflow_steps(correspondence_id);
"""

def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    _migrate_db(conn)      # أضف أعمدة ناقصة في DB القديمة
    _seed_defaults(conn)
    _populate_fts(conn)
    conn.commit()
    conn.close()

def _migrate_db(conn):
    """إضافة أعمدة جديدة للـ DB القديمة دون حذف البيانات"""
    migrations = [
        ("ALTER TABLE audit_log ADD COLUMN user_agent TEXT",),
        ("ALTER TABLE workflow_steps ADD COLUMN due_date TEXT",),
        ("ALTER TABLE correspondence ADD COLUMN workflow_status TEXT DEFAULT 'none'",),
    ]
    for (sql,) in migrations:
        try:
            conn.execute(sql)
        except Exception:
            pass  # العمود موجود مسبقاً

def _populate_fts(conn):
    """ملء فهرس FTS بالبيانات الحالية (عند أول تشغيل أو بعد migration)"""
    try:
        count = conn.execute("SELECT COUNT(*) as c FROM corr_fts").fetchone()['c']
        if count == 0:
            conn.execute("""
                INSERT INTO corr_fts(correspondence_id, ref_num, subject, body, party, action_required)
                SELECT id, ref_num, COALESCE(subject,''), COALESCE(body,''),
                       COALESCE(party,''), COALESCE(action_required,'')
                FROM correspondence WHERE is_deleted=0
            """)
    except Exception as e:
        pass  # FTS قد لا يكون متاحاً في بعض بيئات SQLite

def _seed_defaults(conn):
    from werkzeug.security import generate_password_hash

    # Default company - skip if already exists
    co = conn.execute("SELECT id FROM companies WHERE code='MUI'").fetchone()
    if co: return  # Already seeded, skip everything
    if True:
        cid = new_id()
        conn.execute("""INSERT INTO companies
            (id,name,name_en,code,cr_number,address,city,phone,email,
             primary_color,secondary_color,subscription_plan,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (cid,'مجموعة الإنشاء المتحدة','United Construction Group',
             'MUI','1010000001',
             'طريق الملك فهد، حي العليا','الرياض',
             '+966 11 000 0000','info@ucg.sa',
             '#00b4d8','#0077b6','enterprise', now()))

        # Default departments
        depts = [
            (new_id(), cid, 'الإدارة العامة',   'General Management',   'GM'),
            (new_id(), cid, 'إدارة المشاريع',   'Project Management',   'PM'),
            (new_id(), cid, 'الشؤون القانونية', 'Legal Affairs',        'LEG'),
            (new_id(), cid, 'الموارد البشرية',  'Human Resources',      'HR'),
            (new_id(), cid, 'المالية والمحاسبة','Finance & Accounting',  'FIN'),
            (new_id(), cid, 'المشتريات',        'Procurement',          'PROC'),
        ]
        for d in depts:
            conn.execute("INSERT INTO departments (id,company_id,name,name_en,code,created_at) VALUES (?,?,?,?,?,?)",
                         (*d, now()))

        # Admin user
        uid = new_id()
        conn.execute("""INSERT INTO users
            (id,company_id,username,email,full_name,full_name_en,
             job_title,password_hash,role,is_active,all_projects,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,1,1,?)""",
            (uid, cid, 'admin', 'admin@ucg.sa',
             'مدير النظام', 'System Administrator',
             'مدير تقنية المعلومات',
             generate_password_hash('Admin@2025'),
             'super_admin', now()))

        # Sample project manager
        uid2 = new_id()
        conn.execute("""INSERT INTO users
            (id,company_id,username,email,full_name,job_title,
             password_hash,role,is_active,created_at)
            VALUES (?,?,?,?,?,?,?,?,1,?)""",
            (uid2, cid, 'pm_manager', 'pm@ucg.sa',
             'محمد العتيبي', 'مدير المشاريع',
             generate_password_hash('User@2025'),
             'manager', now()))

        # Sample projects
        projects = [
            (new_id(),cid,'NEOM01','مشروع نيوم - مقاطعة الخطوط','NEOM - The Line','شركة نيوم','تبوك','2024-01-15','2026-06-30',45,'#00b4d8','active','high'),
            (new_id(),cid,'RYDH02','برج الرياض المالي','Riyadh Financial Tower','صندوق الاستثمارات العامة','الرياض','2023-08-01','2025-12-31',72,'#0077b6','active','normal'),
            (new_id(),cid,'JEDD03','ميناء جدة الجديد','New Jeddah Port','الهيئة العامة للموانئ','جدة','2024-03-10','2027-03-10',28,'#48cae4','active','normal'),
            (new_id(),cid,'DMAM04','مجمع الدمام السكني','Dammam Residential Complex','أرامكو السعودية','الدمام','2024-06-01','2026-12-31',15,'#06ffa5','active','low'),
        ]
        for p in projects:
            conn.execute("""INSERT INTO projects
                (id,company_id,code,name,name_en,client,location,
                 start_date,end_date,progress,color,status,priority,
                 manager_id,created_at,created_by)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (*p, uid2, now(), uid))

        # SLA Rules
        sla_rules = [
            (new_id(),cid,'استجابة عاجلة','','urgent',4),
            (new_id(),cid,'استجابة عالية','','high',24),
            (new_id(),cid,'استجابة عادية','','normal',72),
            (new_id(),cid,'استجابة منخفضة','','low',168),
        ]
        for s in sla_rules:
            conn.execute("INSERT INTO sla_rules (id,company_id,name,category,priority,response_hours,created_at) VALUES (?,?,?,?,?,?,?)",
                         (*s, now()))

        # Letter templates
        templates_data = [
            (new_id(),cid,'خطاب تقديم عرض','tender','out',
             'عرض سعر - {{subject}}',
             'السادة / {{party}}\nالمحترمين\n\nالسلام عليكم ورحمة الله وبركاته\n\nيسرنا أن نتقدم بعرضنا لتنفيذ {{subject}}، وذلك وفقاً للمواصفات والشروط المرفقة.\n\nنأمل أن يحظى عرضنا باهتمامكم الكريم، ونحن على أتم الاستعداد لتزويدكم بأي معلومات إضافية.\n\nوتفضلوا بقبول فائق الاحترام والتقدير'),
            (new_id(),cid,'خطاب مطالبة','legal','out',
             'إشعار مطالبة - {{subject}}',
             'السادة / {{party}}\nالمحترمين\n\nإشارةً إلى العقد رقم {{party_ref}} المبرم بيننا، نودّ إشعاركم بأن {{subject}}.\n\nلذا نطلب منكم اتخاذ الإجراء اللازم خلال مدة لا تتجاوز 14 يوم عمل من تاريخ هذا الخطاب.\n\nوتفضلوا بقبول وافر الاحترام والتقدير'),
            (new_id(),cid,'خطاب شكر وتقدير','general','out',
             'شكر وتقدير - {{subject}}',
             'السادة / {{party}}\nالمحترمين\n\nالسلام عليكم ورحمة الله وبركاته\n\nيطيب لنا أن نتقدم إليكم بخالص الشكر والتقدير على {{subject}}، ونثمّن عالياً جهودكم وتعاونكم المتميز.\n\nوتفضلوا بقبول فائق الاحترام والتقدير'),
        ]
        for t in templates_data:
            conn.execute("""INSERT INTO templates
                (id,company_id,name,category,corr_type,subject_template,body_template,created_at)
                VALUES (?,?,?,?,?,?,?,?)""", (*t, now()))

        # Default workflow
        wf_id = new_id()
        wf_steps = json.dumps([
            {"step": 1, "name": "مراجعة المشرف", "action": "review", "role": "manager", "mandatory": True},
            {"step": 2, "name": "اعتماد المدير", "action": "approve", "role": "director", "mandatory": True},
            {"step": 3, "name": "إرسال", "action": "send", "role": "user", "mandatory": True},
        ])
        conn.execute("""INSERT INTO workflow_definitions
            (id,company_id,name,category,steps_json,is_active,is_default,created_at)
            VALUES (?,?,?,?,?,1,1,?)""",
            (wf_id, cid, 'سير العمل الافتراضي', 'default', wf_steps, now()))

        # Sample correspondence
        proj_ids = [p[0] for p in projects]
        sample_corr = [
            (new_id(),cid,'MUI-NEOM01-2025-OUT-00001','out',proj_ids[0],'طلب الموافقة على مخططات المرحلة الأولى','شركة نيوم','tender','urgent','sent','pending','2025-01-15',uid),
            (new_id(),cid,'MUI-NEOM01-2025-IN-00001','in',proj_ids[0],'الموافقة على المخططات المعدلة','شركة نيوم - قسم التصميم','approval','normal','received','replied','2025-01-20',uid),
            (new_id(),cid,'MUI-RYDH02-2025-OUT-00001','out',proj_ids[1],'طلب تمديد مدة العقد - المرحلة الثانية','صندوق الاستثمارات العامة','contract','high','sent','pending','2025-02-01',uid2),
            (new_id(),cid,'MUI-JEDD03-2025-OUT-00001','out',proj_ids[2],'تقرير التقدم الشهري - فبراير 2025','الهيئة العامة للموانئ','report','normal','sent','replied','2025-02-05',uid2),
            (new_id(),cid,'MUI-NEOM01-2025-OUT-00002','out',proj_ids[0],'طلب توريد مواد البناء - دفعة ثانية','موردون متعددون','procurement','high','draft','pending','2025-02-10',uid),
            (new_id(),cid,'MUI-DMAM04-2025-IN-00001','in',proj_ids[3],'ملاحظات على تصاميم الوحدات السكنية','أرامكو السعودية - قسم الإسكان','general','normal','received','pending','2025-02-15',uid2),
        ]
        for c in sample_corr:
            conn.execute("""INSERT INTO correspondence
                (id,company_id,ref_num,type,project_id,subject,party,
                 category,priority,status,reply_status,date,created_by,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (*c, now()))

-- ─────────────────────────────────────────
--  التوقيعات الرقمية للمستخدمين
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_signatures (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company_id  TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    sig_data    TEXT NOT NULL,        -- Base64 PNG image of signature
    sig_type    TEXT DEFAULT 'drawn', -- drawn | uploaded | stamp
    is_active   INTEGER DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);

-- التوقيعات المُطبَّقة على المراسلات
CREATE TABLE IF NOT EXISTS correspondence_signatures (
    id                TEXT PRIMARY KEY,
    correspondence_id TEXT NOT NULL REFERENCES correspondence(id) ON DELETE CASCADE,
    user_id           TEXT NOT NULL REFERENCES users(id),
    sig_data          TEXT NOT NULL,
    signed_at         TEXT NOT NULL,
    sign_role         TEXT,           -- approver / creator / witness
    page_number       INTEGER DEFAULT 1,
    x_pos             REAL DEFAULT 0.7,
    y_pos             REAL DEFAULT 0.1
);
CREATE INDEX IF NOT EXISTS idx_corr_sigs ON correspondence_signatures(correspondence_id);

-- ─────────────────────────────────────────
--  Push Notification Subscriptions
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id                TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subscription_json TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    UNIQUE(user_id)
);
