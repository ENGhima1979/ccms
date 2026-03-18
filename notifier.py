# -*- coding: utf-8 -*-
"""
notifier.py — نظام الإشعارات
=============================
يدعم:
  1. CallMeBot  — WhatsApp مجاني عبر رقمك الشخصي (موصى به)
  2. WhatsApp Business API — رسمي (يحتاج Meta Business)
  3. البريد الإلكتروني SMTP

CallMeBot — كيف تُعدّه (مرة واحدة لكل موظف):
  1. أضف الرقم +34 644 59 78 35 في جهات الاتصال باسم "CallMeBot"
  2. أرسل له عبر واتساب: I allow callmebot to send me messages
  3. ستصلك رسالة تحتوي مفتاح API الخاص بك (مثل: 1234567)
  4. أدخل رقم الهاتف + المفتاح في إعدادات المستخدم
"""
import smtplib, json, logging, urllib.request, urllib.error, urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from models import get_db, new_id, now

log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════
#  CallMeBot — WhatsApp مجاني
# ══════════════════════════════════════════════════════
def send_whatsapp_callmebot(phone: str, message: str, apikey: str) -> tuple:
    """
    إرسال واتساب مجاني عبر CallMeBot
    phone  : رقم الهاتف الدولي مثل +966512345678
    message: النص (يدعم العربية)
    apikey : مفتاح CallMeBot الخاص بالمستخدم
    """
    if not phone or not apikey:
        return False, "رقم الهاتف أو مفتاح CallMeBot مفقود"

    # تنظيف الرقم
    phone = phone.strip()
    if not phone.startswith('+'):
        phone = '+' + phone.lstrip('0')

    # ترميز الرسالة
    encoded = urllib.parse.quote(message, safe='')

    url = (f"https://api.callmebot.com/whatsapp.php"
           f"?phone={urllib.parse.quote(phone)}"
           f"&text={encoded}"
           f"&apikey={apikey}")

    req = urllib.request.Request(url, headers={'User-Agent': 'CCMS/3.0'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            response_text = r.read().decode('utf-8', 'ignore')
            # CallMeBot يُرجع "Message queued" عند النجاح
            if 'queued' in response_text.lower() or 'sent' in response_text.lower() or r.status == 200:
                log.info(f"CallMeBot sent to {phone[:7]}***")
                return True, None
            else:
                return False, f"CallMeBot: {response_text[:100]}"
    except urllib.error.HTTPError as e:
        err = e.read().decode('utf-8', 'ignore')[:200]
        log.warning(f"CallMeBot HTTP {e.code}: {err}")
        return False, f"HTTP {e.code}: {err}"
    except Exception as e:
        log.warning(f"CallMeBot error: {e}")
        return False, str(e)


# ══════════════════════════════════════════════════════
#  WhatsApp Business API (رسمي)
# ══════════════════════════════════════════════════════
def send_whatsapp_business(phone: str, message: str, settings: dict) -> tuple:
    """إرسال عبر WhatsApp Business API الرسمي"""
    api_url  = settings.get('whatsapp_api_url','').rstrip('/')
    token    = settings.get('whatsapp_api_token','')
    phone_id = settings.get('whatsapp_phone_id','')

    if not all([api_url, token, phone_id]):
        return False, "إعدادات WhatsApp Business غير مكتملة"

    # تنظيف الرقم
    clean = phone.replace('+','').replace(' ','').replace('-','')
    if not clean.startswith('966') and len(clean) == 9:
        clean = '966' + clean

    payload = json.dumps({
        "messaging_product": "whatsapp",
        "to": clean,
        "type": "text",
        "text": {"body": message}
    }).encode('utf-8')

    url = f"{api_url}/{phone_id}/messages"
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }, method='POST')

    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return True, None
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode()[:100]}"
    except Exception as e:
        return False, str(e)


# ══════════════════════════════════════════════════════
#  UltraMsg — ربط رقمك الشخصي عبر QR
# ══════════════════════════════════════════════════════
def send_whatsapp_ultramsg(phone: str, message: str,
                            instance_id: str, token: str) -> tuple:
    """
    إرسال واتساب عبر UltraMsg (ربط رقمك الشخصي بـ QR)
    instance_id: من لوحة UltraMsg
    token: من لوحة UltraMsg
    """
    if not instance_id or not token:
        return False, "instance_id أو token مفقود"

    # تنظيف الرقم
    phone = phone.strip().replace('+','').replace(' ','').replace('-','')
    if not phone.startswith('966') and len(phone) == 9:
        phone = '966' + phone

    payload = urllib.parse.urlencode({
        'token': token,
        'to':    phone,
        'body':  message,
    }).encode('utf-8')

    url = f"https://api.ultramsg.com/{instance_id}/messages/chat"
    req = urllib.request.Request(url, data=payload,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST')
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read().decode())
            if resp.get('sent') == 'true' or resp.get('id'):
                log.info(f"UltraMsg sent to {phone[:7]}***")
                return True, None
            return False, str(resp)
    except Exception as e:
        log.warning(f"UltraMsg error: {e}")
        return False, str(e)


# ══════════════════════════════════════════════════════
#  دالة واتساب الموحّدة
# ══════════════════════════════════════════════════════
def send_whatsapp(settings: dict, phone: str, message: str,
                  user_callmebot_key: str = "") -> tuple:
    """
    إرسال واتساب — تختار المزود تلقائياً:
    - callmebot  → CallMeBot (مجاني — رقم شخصي)
    - ultramsg   → UltraMsg  (مجاني — ربط رقمك بـ QR)
    - business   → WhatsApp Business API (رسمي)
    """
    provider = settings.get('whatsapp_provider', 'callmebot')

    log.debug(f"send_whatsapp: provider={provider}, phone={phone[:8]}***")

    # UltraMsg — أولوية إذا كان المزود محدداً
    if provider == 'ultramsg':
        iid   = settings.get('ultramsg_instance_id','').strip()
        token = settings.get('ultramsg_token','').strip()
        log.debug(f"UltraMsg: instance={iid}, token_len={len(token)}")
        return send_whatsapp_ultramsg(phone, message, iid, token)

    # CallMeBot — إذا كان المزود callmebot أو لدى المستخدم مفتاح شخصي
    elif provider == 'callmebot' or user_callmebot_key:
        key = user_callmebot_key or settings.get('whatsapp_callmebot_key','')
        return send_whatsapp_callmebot(phone, message, key)

    # Business API
    else:
        return send_whatsapp_business(phone, message, settings)


# ══════════════════════════════════════════════════════
#  البريد الإلكتروني
# ══════════════════════════════════════════════════════
def send_email(settings: dict, to_email: str, to_name: str,
               subject: str, body_html: str, body_text: str = None) -> tuple:
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = f"{settings.get('smtp_from_name','CCMS')} <{settings['smtp_user']}>"
    msg['To']      = f"{to_name} <{to_email}>"

    if body_text:
        msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
    msg.attach(MIMEText(body_html, 'html', 'utf-8'))

    try:
        if settings.get('smtp_use_tls', 1):
            srv = smtplib.SMTP(settings['smtp_host'], settings.get('smtp_port', 587))
            srv.ehlo(); srv.starttls()
        else:
            srv = smtplib.SMTP_SSL(settings['smtp_host'], settings.get('smtp_port', 465))
        srv.login(settings['smtp_user'], settings['smtp_password'])
        srv.sendmail(settings['smtp_user'], to_email, msg.as_string())
        srv.quit()
        return True, None
    except Exception as e:
        return False, str(e)


# ══════════════════════════════════════════════════════
#  إرسال مع تسجيل في DB
# ══════════════════════════════════════════════════════
def notify(company_id, user_id, channel, recipient,
           subject, body, settings, extra: dict = None):
    """
    إرسال إشعار وتسجيله في notification_log
    extra: {'callmebot_key': '...'} لتمرير مفتاح CallMeBot الخاص بالمستخدم
    """
    extra = extra or {}
    conn = get_db()
    log_id = new_id()
    conn.execute("""INSERT INTO notification_log
        (id,company_id,user_id,channel,recipient,subject,body,status,created_at)
        VALUES (?,?,?,?,?,?,?,'pending',?)""",
        (log_id, company_id, user_id, channel, recipient, subject, body, now()))
    conn.commit()

    ok, err = False, "القناة غير مفعّلة"

    if channel == 'email' and settings.get('email_enabled'):
        ok, err = send_email(settings, recipient, '', subject, body)

    elif channel == 'whatsapp' and settings.get('whatsapp_enabled'):
        ok, err = send_whatsapp(
            settings, recipient, body,
            user_callmebot_key=extra.get('callmebot_key', ''))

    conn.execute("""UPDATE notification_log SET
        status=?, error_msg=?, sent_at=? WHERE id=?""",
        ('sent' if ok else 'failed', err, now() if ok else None, log_id))
    conn.commit(); conn.close()

    if not ok and err:
        log.warning(f"Notify [{channel}] failed: {err}")
    return ok, err


# ══════════════════════════════════════════════════════
#  جلب إعدادات الإشعارات
# ══════════════════════════════════════════════════════
def get_company_notification_settings(company_id: str) -> dict:
    conn = get_db()
    s = conn.execute(
        "SELECT * FROM notification_settings WHERE company_id=?",
        (company_id,)).fetchone()
    conn.close()
    return dict(s) if s else {}


def get_user_whatsapp_info(user_id: str) -> dict:
    """جلب رقم هاتف ومفتاح CallMeBot للمستخدم"""
    conn = get_db()
    u = conn.execute(
        "SELECT phone, callmebot_key FROM users WHERE id=?",
        (user_id,)).fetchone()
    conn.close()
    if not u:
        return {'phone': '', 'callmebot_key': ''}
    return {
        'phone':          u['phone'] or '',
        'callmebot_key':  u['callmebot_key'] if 'callmebot_key' in u.keys() else '',
    }


# ══════════════════════════════════════════════════════
#  قوالب الرسائل
# ══════════════════════════════════════════════════════

def build_whatsapp_message(corr_type: str, ref_num: str, subject: str,
                            party: str, action: str = "", url: str = "") -> str:
    """
    بناء رسالة واتساب منسّقة
    corr_type: out | in | internal
    action: 'new' | 'approved' | 'rejected' | 'returned' | 'workflow'
    """
    type_labels = {'out': '📤 صادر', 'in': '📥 وارد', 'internal': '🔄 داخلي'}
    type_label  = type_labels.get(corr_type, '📋 معاملة')

    action_labels = {
        'new':       '📨 معاملة جديدة تحتاج مراجعتك',
        'approved':  '✅ تم اعتماد معاملتك',
        'rejected':  '❌ تم رفض معاملتك',
        'returned':  '↩️ معاملتك أُعيدت للتعديل',
        'workflow':  '🔔 مطلوب موافقتك على معاملة',
        'assigned':  '📌 معاملة جديدة مُسنَدة إليك',
    }
    action_label = action_labels.get(action, '🔔 إشعار معاملة')

    lines = [
        f"*CCMS — نظام إدارة المراسلات*",
        f"{'─'*30}",
        f"{action_label}",
        f"",
        f"*النوع:*  {type_label}",
        f"*الرقم:* `{ref_num}`",
        f"*الموضوع:* {subject}",
    ]
    if party:
        lines.append(f"*الجهة:* {party}")
    if url:
        lines.append(f"")
        lines.append(f"🔗 {url}")
    lines.append(f"{'─'*30}")
    lines.append(f"_CCMS Professional_")

    return '\n'.join(lines)


def build_email_html(title, body_lines, action_url=None,
                     action_label=None, color='#00b4d8'):
    lines_html = ''.join(
        f'<p style="margin:6px 0;font-size:15px;">{l}</p>' for l in body_lines)
    btn = (f'<a href="{action_url}" style="display:inline-block;margin-top:18px;'
           f'padding:10px 28px;background:{color};color:#fff;text-decoration:none;'
           f'border-radius:6px;font-size:15px;">{action_label}</a>'
           if action_url else '')
    return f"""
<div dir="rtl" style="font-family:Arial,sans-serif;max-width:560px;margin:auto;
     border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
  <div style="background:{color};padding:20px 24px;">
    <h2 style="color:#fff;margin:0;font-size:20px;">{title}</h2>
  </div>
  <div style="padding:24px;">{lines_html}{btn}</div>
  <div style="background:#f5f5f5;padding:12px 24px;font-size:12px;color:#888;text-align:center;">
    نظام إدارة الاتصالات الإدارية — CCMS Professional
  </div>
</div>"""


# ══════════════════════════════════════════════════════
#  دوال الإشعار الجاهزة
# ══════════════════════════════════════════════════════

def notify_new_correspondence(company_id, corr, assigned_user,
                               settings, base_url=''):
    """إشعار معاملة جديدة مُسنَدة لمستخدم"""
    if not assigned_user:
        return
    url = f"{base_url}/correspondence/{corr['id']}" if base_url else ''

    # واتساب
    if settings.get('whatsapp_enabled') and settings.get('notify_assigned'):
        phone = assigned_user.get('phone','')
        if phone:
            msg = build_whatsapp_message(
                corr.get('type','out'),
                corr['ref_num'], corr['subject'],
                corr.get('party',''), 'assigned', url)
            notify(company_id, assigned_user['id'], 'whatsapp', phone,
                   corr['subject'], msg, settings,
                   extra={'callmebot_key': assigned_user.get('callmebot_key','')})

    # بريد إلكتروني
    if assigned_user.get('email') and settings.get('email_enabled') and settings.get('notify_assigned'):
        html = build_email_html(
            "📨 معاملة جديدة مُسنَدة إليك",
            [f"السلام عليكم {assigned_user.get('full_name','')},",
             "تم إسناد معاملة جديدة إليك:",
             f"<b>الرقم:</b> {corr['ref_num']}",
             f"<b>الموضوع:</b> {corr['subject']}",
             f"<b>الجهة:</b> {corr.get('party','')}"],
            action_url=url, action_label="عرض المعاملة")
        notify(company_id, assigned_user['id'], 'email',
               assigned_user['email'],
               f"معاملة جديدة: {corr['subject']}", html, settings)


def notify_workflow_action(company_id, corr, target_user,
                            action: str, note: str = '',
                            settings: dict = None, base_url: str = ''):
    """
    إشعار إجراء سير العمل
    action: approved | rejected | returned | pending_review
    """
    if not target_user or not settings:
        return
    url = f"{base_url}/correspondence/{corr['id']}" if base_url else ''

    action_map = {
        'approved':       '✅ اعتُمدت معاملتك',
        'rejected':       '❌ رُفضت معاملتك',
        'returned':       '↩️ أُعيدت معاملتك للتعديل',
        'pending_review': '🔔 معاملة تنتظر مراجعتك',
    }
    email_subjects = {
        'approved':       f'✅ اعتُمدت: {corr["ref_num"]}',
        'rejected':       f'❌ رُفضت: {corr["ref_num"]}',
        'returned':       f'↩️ للتعديل: {corr["ref_num"]}',
        'pending_review': f'🔔 للمراجعة: {corr["ref_num"]}',
    }

    # واتساب
    if settings.get('whatsapp_enabled') and settings.get('notify_workflow'):
        phone = target_user.get('phone','')
        if phone:
            msg = build_whatsapp_message(
                corr.get('type','out'),
                corr['ref_num'], corr['subject'],
                corr.get('party',''), action, url)
            if note:
                msg += f"\n\n*ملاحظة:* {note}"
            notify(company_id, target_user['id'], 'whatsapp', phone,
                   corr['subject'], msg, settings,
                   extra={'callmebot_key': target_user.get('callmebot_key','')})

    # بريد إلكتروني
    if target_user.get('email') and settings.get('email_enabled') and settings.get('notify_workflow'):
        body_lines = [
            f"السلام عليكم {target_user.get('full_name','')},",
            action_map.get(action, ''),
            f"<b>الرقم:</b> {corr['ref_num']}",
            f"<b>الموضوع:</b> {corr['subject']}",
        ]
        if note:
            body_lines.append(f"<b>ملاحظة:</b> {note}")
        colors = {'approved':'#06FFA5','rejected':'#FF3860','returned':'#FFC107','pending_review':'#00B4D8'}
        html = build_email_html(
            action_map.get(action,'إشعار'), body_lines,
            action_url=url, action_label="عرض المعاملة",
            color=colors.get(action,'#00b4d8'))
        notify(company_id, target_user['id'], 'email',
               target_user['email'],
               email_subjects.get(action, corr['subject']), html, settings)


def notify_due_soon(company_id, corr, assigned_user,
                    settings, base_url=''):
    """إشعار اقتراب الموعد النهائي"""
    if not assigned_user:
        return
    url = f"{base_url}/correspondence/{corr['id']}" if base_url else ''

    if settings.get('whatsapp_enabled') and settings.get('notify_due_soon'):
        phone = assigned_user.get('phone','')
        if phone:
            msg = (f"*CCMS — تنبيه موعد نهائي*\n{'─'*30}\n"
                   f"⏰ المعاملة التالية تقترب من موعدها:\n\n"
                   f"*الرقم:* `{corr['ref_num']}`\n"
                   f"*الموضوع:* {corr['subject']}\n"
                   f"*الموعد النهائي:* {corr.get('due_date','')}\n"
                   f"\n🔗 {url}" if url else '')
            notify(company_id, assigned_user['id'], 'whatsapp', phone,
                   corr['subject'], msg, settings,
                   extra={'callmebot_key': assigned_user.get('callmebot_key','')})

    if assigned_user.get('email') and settings.get('email_enabled') and settings.get('notify_due_soon'):
        html = build_email_html(
            "⚠️ اقتراب الموعد النهائي",
            [f"السلام عليكم {assigned_user.get('full_name','')},",
             "المعاملة التالية تقترب من موعدها النهائي:",
             f"<b>الرقم:</b> {corr['ref_num']}",
             f"<b>الموضوع:</b> {corr['subject']}",
             f"<b>الموعد النهائي:</b> {corr.get('due_date','')}"],
            action_url=url, action_label="عرض المعاملة", color='#ff9800')
        notify(company_id, assigned_user['id'], 'email',
               assigned_user['email'],
               f"⚠️ موعد نهائي: {corr['ref_num']}", html, settings)
