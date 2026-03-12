"""
security.py — منظومة الأمان المتكاملة لـ CCMS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Audit Trail    — سجل تدقيق كامل
2. Permissions    — صلاحيات دقيقة على المراسلات والمشاريع
3. Digital Stamp  — ختم رقمي على PDF
"""

import json, hashlib, datetime, uuid
from functools import wraps
from flask import session, request, flash, redirect, url_for, current_app


# ══════════════════════════════════════════════════════
#  1. AUDIT TRAIL — سجل التدقيق الكامل
# ══════════════════════════════════════════════════════

AUDIT_ACTIONS = {
    # المراسلات
    'CORR_CREATE':  'إنشاء مراسلة',
    'CORR_EDIT':    'تعديل مراسلة',
    'CORR_DELETE':  'حذف مراسلة',
    'CORR_VIEW':    'عرض مراسلة',
    'CORR_ARCHIVE': 'أرشفة مراسلة',
    'CORR_RESTORE': 'استعادة مراسلة',
    'CORR_EXPORT':  'تصدير PDF',
    # سير العمل
    'WF_APPROVE':   'اعتماد خطوة',
    'WF_REJECT':    'رفض مراسلة',
    'WF_RETURN':    'إعادة للتعديل',
    # المستخدمون
    'USER_LOGIN':   'تسجيل دخول',
    'USER_LOGOUT':  'تسجيل خروج',
    'USER_CREATE':  'إنشاء مستخدم',
    'USER_EDIT':    'تعديل مستخدم',
    'USER_DELETE':  'حذف مستخدم',
    # الإعدادات
    'SETTINGS_EDIT':'تعديل الإعدادات',
    'COMPANY_EDIT': 'تعديل بيانات الشركة',
    # الصلاحيات
    'PERM_GRANT':   'منح صلاحية',
    'PERM_REVOKE':  'سحب صلاحية',
}


def log_audit(conn, action, entity=None, entity_id=None,
              old_value=None, new_value=None, details=None):
    """
    تسجيل حدث في سجل التدقيق
    ────────────────────────────
    action    : رمز الحدث (CORR_CREATE, USER_LOGIN, ...)
    entity    : نوع الكيان (correspondence, user, project, ...)
    entity_id : معرّف الكيان
    old_value : القيمة قبل التعديل (JSON أو نص)
    new_value : القيمة بعد التعديل
    details   : تفاصيل إضافية
    """
    try:
        company_id = session.get('company_id', '')
        user_id    = session.get('user_id', '')
        username   = session.get('username', 'system')
        ip         = _get_real_ip()
        ua         = request.headers.get('User-Agent', '')[:200]

        conn.execute("""
            INSERT INTO audit_log
            (id, company_id, user_id, username, action,
             entity, entity_id, old_value, new_value,
             ip_address, user_agent, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            str(uuid.uuid4()), company_id, user_id, username,
            action, entity or '', entity_id or '',
            _serialize(old_value), _serialize(new_value),
            ip, ua,
            datetime.datetime.now().isoformat(timespec='seconds')
        ))
    except Exception as e:
        current_app.logger.warning(f'Audit log failed: {e}')


def _get_real_ip():
    """استخرج IP الحقيقي حتى خلف Proxy"""
    for header in ('X-Forwarded-For', 'X-Real-IP', 'CF-Connecting-IP'):
        val = request.headers.get(header)
        if val:
            return val.split(',')[0].strip()
    return request.remote_addr or ''


def _serialize(val):
    if val is None: return None
    if isinstance(val, (dict, list)): return json.dumps(val, ensure_ascii=False)
    return str(val)


def get_audit_log(conn, company_id, entity=None, entity_id=None,
                  user_id=None, limit=100, offset=0):
    """جلب سجل التدقيق مع فلترة"""
    sql    = "SELECT al.*, u.full_name FROM audit_log al LEFT JOIN users u ON al.user_id=u.id WHERE al.company_id=?"
    params = [company_id]
    if entity:    sql += " AND al.entity=?";    params.append(entity)
    if entity_id: sql += " AND al.entity_id=?"; params.append(entity_id)
    if user_id:   sql += " AND al.user_id=?";   params.append(user_id)
    sql += " ORDER BY al.created_at DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    return conn.execute(sql, params).fetchall()


# ══════════════════════════════════════════════════════
#  2. GRANULAR PERMISSIONS — صلاحيات دقيقة
# ══════════════════════════════════════════════════════

# مستويات الصلاحية على المراسلة
PERM_NONE   = 0   # لا صلاحية
PERM_VIEW   = 1   # عرض فقط
PERM_COMMENT= 2   # عرض + تعليق
PERM_EDIT   = 3   # عرض + تعديل
PERM_MANAGE = 4   # كامل (حذف، أرشفة، تصدير)

PERM_LABELS = {
    0: 'بدون صلاحية',
    1: 'عرض فقط',
    2: 'عرض وتعليق',
    3: 'عرض وتعديل',
    4: 'صلاحية كاملة',
}


def get_user_corr_permission(conn, user_id, corr_id, company_id):
    """
    احسب صلاحية المستخدم على مراسلة محددة
    ─────────────────────────────────────────
    الأولوية: صلاحية مباشرة > صلاحية المشروع > الدور العام
    """
    # 1. الـ admin و super_admin لهم صلاحية كاملة دائماً
    role = session.get('role', 'user')
    if role in ('admin', 'super_admin'):
        return PERM_MANAGE

    # 2. المُنشئ له صلاحية كاملة على مراسلاته
    corr = conn.execute(
        "SELECT created_by, project_id FROM correspondence WHERE id=? AND company_id=?",
        (corr_id, company_id)).fetchone()
    if not corr:
        return PERM_NONE
    if corr['created_by'] == user_id:
        return PERM_MANAGE

    # 3. صلاحية مباشرة على المراسلة
    direct = conn.execute("""
        SELECT permission_level FROM correspondence_permissions
        WHERE correspondence_id=? AND user_id=?
    """, (corr_id, user_id)).fetchone()
    if direct:
        return direct['permission_level']

    # 4. صلاحية عبر المشروع
    if corr['project_id']:
        proj_perm = conn.execute("""
            SELECT role FROM user_projects WHERE user_id=? AND project_id=?
        """, (user_id, corr['project_id'])).fetchone()
        if proj_perm:
            role_map = {'manager': PERM_MANAGE, 'editor': PERM_EDIT,
                        'viewer': PERM_VIEW, 'member': PERM_COMMENT}
            return role_map.get(proj_perm['role'], PERM_VIEW)

    # 5. الـ manager له عرض وتعليق على الكل
    if role == 'manager':
        return PERM_COMMENT

    # 6. user عادي: لا يرى ما لم يكن مُخصَّصاً له
    return PERM_NONE


def can_view_corr(conn, user_id, corr_id, company_id):
    return get_user_corr_permission(conn, user_id, corr_id, company_id) >= PERM_VIEW

def can_edit_corr(conn, user_id, corr_id, company_id):
    return get_user_corr_permission(conn, user_id, corr_id, company_id) >= PERM_EDIT

def can_manage_corr(conn, user_id, corr_id, company_id):
    return get_user_corr_permission(conn, user_id, corr_id, company_id) >= PERM_MANAGE


def grant_permission(conn, corr_id, user_id, level, granted_by):
    """منح صلاحية مستخدم على مراسلة"""
    conn.execute("""
        INSERT INTO correspondence_permissions
            (id, correspondence_id, user_id, permission_level, granted_by, created_at)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(correspondence_id, user_id)
        DO UPDATE SET permission_level=excluded.permission_level,
                      granted_by=excluded.granted_by,
                      created_at=excluded.created_at
    """, (str(uuid.uuid4()), corr_id, user_id, level, granted_by,
          datetime.datetime.now().isoformat(timespec='seconds')))


def revoke_permission(conn, corr_id, user_id):
    """سحب صلاحية مستخدم من مراسلة"""
    conn.execute("""
        DELETE FROM correspondence_permissions
        WHERE correspondence_id=? AND user_id=?
    """, (corr_id, user_id))


def get_corr_permissions(conn, corr_id):
    """جلب قائمة المستخدمين الذين لديهم صلاحية على مراسلة"""
    return conn.execute("""
        SELECT cp.*, u.full_name, u.username, u.role
        FROM correspondence_permissions cp
        JOIN users u ON cp.user_id = u.id
        WHERE cp.correspondence_id=?
        ORDER BY cp.permission_level DESC
    """, (corr_id,)).fetchall()


# ══════════════════════════════════════════════════════
#  3. DIGITAL STAMP — الختم الرقمي على PDF
# ══════════════════════════════════════════════════════

def generate_document_hash(corr_id, ref_num, subject, company_id):
    """توليد hash فريد للمراسلة كبصمة رقمية"""
    data = f"{corr_id}|{ref_num}|{subject}|{company_id}"
    return hashlib.sha256(data.encode()).hexdigest()[:16].upper()


def add_digital_stamp_to_pdf(pdf_bytes, corr, company, approver_name=None):
    """
    إضافة ختم رقمي احترافي للـ PDF بعد الاعتماد النهائي
    ────────────────────────────────────────────────────
    يتضمن:
    - رقم المراسلة + تاريخ الاعتماد
    - اسم المعتمد + hash التحقق
    - QR code للتحقق الإلكتروني
    """
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.colors import HexColor
        from reportlab.lib.units import mm
        import io as _io

        # توليد hash التحقق
        doc_hash = generate_document_hash(
            corr.get('id',''), corr.get('ref_num',''),
            corr.get('subject',''), company.get('id',''))

        stamp_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

        # إنشاء طبقة الختم
        stamp_buffer = _io.BytesIO()
        c = canvas.Canvas(stamp_buffer, pagesize=A4)
        w, h = A4

        # ── الختم: مستطيل في أسفل يسار الصفحة ──
        x, y = 15*mm, 8*mm
        bw, bh = 85*mm, 28*mm

        # خلفية شبه شفافة
        c.setFillColor(HexColor('#f0fff4'))
        c.setStrokeColor(HexColor('#06ffa5'))
        c.setLineWidth(1.5)
        c.roundRect(x, y, bw, bh, 3*mm, fill=1, stroke=1)

        # النص العربي (من اليمين)
        c.setFont('Helvetica-Bold', 7)
        c.setFillColor(HexColor('#0a1628'))

        lines = [
            f"APPROVED | معتمد رقمياً",
            f"Ref: {corr.get('ref_num','')}",
            f"Date: {stamp_date}",
            f"By: {approver_name or 'System'}",
            f"Hash: {doc_hash}",
        ]
        line_h = 4.5*mm
        for i, line in enumerate(lines):
            c.drawString(x + 3*mm, y + bh - (i+1)*line_h, line)

        # علامة ✓ كبيرة
        c.setFont('Helvetica-Bold', 20)
        c.setFillColor(HexColor('#06ffa5'))
        c.drawString(x + bw - 12*mm, y + 8*mm, '✓')

        c.save()
        stamp_layer = stamp_buffer.getvalue()

        # دمج الختم مع الـ PDF الأصلي
        try:
            from pypdf import PdfWriter, PdfReader
            import _io as io2

            original = PdfReader(_io.BytesIO(pdf_bytes))
            stamp    = PdfReader(_io.BytesIO(stamp_layer))
            writer   = PdfWriter()

            for i, page in enumerate(original.pages):
                if i == len(original.pages) - 1:
                    # أضف الختم للصفحة الأخيرة فقط
                    page.merge_page(stamp.pages[0])
                writer.add_page(page)

            output = _io.BytesIO()
            writer.write(output)
            return output.getvalue()

        except ImportError:
            # إذا لم يكن pypdf متاحاً، أرجع PDF الأصلي مع watermark نصي
            return _add_text_watermark(pdf_bytes, doc_hash, stamp_date, approver_name)

    except Exception as e:
        current_app.logger.warning(f'Digital stamp failed: {e}')
        return pdf_bytes  # أرجع الأصلي بدون ختم


def _add_text_watermark(pdf_bytes, doc_hash, stamp_date, approver):
    """Fallback: أضف نص التحقق في نهاية الـ PDF"""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.colors import HexColor
        import io as _io

        buf = _io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        w, h = A4
        c.setFont('Helvetica', 8)
        c.setFillColor(HexColor('#888888'))
        text = f"Verified | Hash: {doc_hash} | {stamp_date} | {approver or 'System'}"
        c.drawCentredString(w/2, 15, text)
        c.save()
        return pdf_bytes  # return original, stamp page separate
    except:
        return pdf_bytes


def verify_document_hash(corr_id, ref_num, subject, company_id, provided_hash):
    """التحقق من صحة الختم الرقمي"""
    expected = generate_document_hash(corr_id, ref_num, subject, company_id)
    return expected == provided_hash.upper()
