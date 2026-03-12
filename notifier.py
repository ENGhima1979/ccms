"""
نظام الإشعارات — المرحلة الثانية
بريد إلكتروني SMTP + واتساب Business API
"""
import smtplib, json, urllib.request, urllib.error
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from models import get_db, new_id, now

# --- البريد الإلكتروني --------------------------------
def send_email(settings, to_email, to_name, subject, body_html, body_text=None):
    """إرسال بريد إلكتروني عبر SMTP"""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = f"{settings.get('smtp_from_name','CCMS')} <{settings['smtp_user']}>"
    msg['To']      = f"{to_name} <{to_email}>"

    if body_text:
        msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
    msg.attach(MIMEText(body_html, 'html', 'utf-8'))

    try:
        if settings.get('smtp_use_tls', 1):
            server = smtplib.SMTP(settings['smtp_host'], settings.get('smtp_port', 587))
            server.ehlo()
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(settings['smtp_host'], settings.get('smtp_port', 465))
        server.login(settings['smtp_user'], settings['smtp_password'])
        server.sendmail(settings['smtp_user'], to_email, msg.as_string())
        server.quit()
        return True, None
    except Exception as e:
        return False, str(e)

# --- واتساب ------------------------------------------
def send_whatsapp(settings, to_phone, message):
    """إرسال رسالة واتساب عبر WhatsApp Cloud API"""
    api_url   = settings.get('whatsapp_api_url','').rstrip('/')
    token     = settings.get('whatsapp_api_token','')
    phone_id  = settings.get('whatsapp_phone_id','')

    if not all([api_url, token, phone_id]):
        return False, "إعدادات واتساب غير مكتملة"

    # Normalize phone
    phone = to_phone.replace('+','').replace(' ','').replace('-','')
    if not phone.startswith('966') and not phone.startswith('1'):
        phone = '966' + phone.lstrip('0')

    payload = json.dumps({
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": message}
    }).encode('utf-8')

    url = f"{api_url}/{phone_id}/messages"
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }, method='POST')

    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return True, None
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode()}"
    except Exception as e:
        return False, str(e)

# --- إرسال مع تسجيل ----------------------------------
def notify(company_id, user_id, channel, recipient, subject, body, settings):
    """إرسال إشعار وتسجيله"""
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
        ok, err = send_whatsapp(settings, recipient, body)

    conn.execute("""UPDATE notification_log SET
        status=?, error_msg=?, sent_at=? WHERE id=?""",
        ('sent' if ok else 'failed', err, now() if ok else None, log_id))
    conn.commit()
    conn.close()
    return ok, err

def get_company_notification_settings(company_id):
    """جلب إعدادات الإشعارات"""
    conn = get_db()
    s = conn.execute("SELECT * FROM notification_settings WHERE company_id=?", (company_id,)).fetchone()
    conn.close()
    return dict(s) if s else {}

# --- قوالب رسائل الإشعار -----------------------------
def build_email_html(title, body_lines, action_url=None, action_label=None, color='#00b4d8'):
    lines_html = ''.join(f'<p style="margin:6px 0;font-size:15px;">{l}</p>' for l in body_lines)
    btn = f'<a href="{action_url}" style="display:inline-block;margin-top:18px;padding:10px 28px;background:{color};color:#fff;text-decoration:none;border-radius:6px;font-size:15px;">{action_label}</a>' if action_url else ''
    return f"""
<div dir="rtl" style="font-family:Arial,sans-serif;max-width:560px;margin:auto;border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
  <div style="background:{color};padding:20px 24px;">
    <h2 style="color:#fff;margin:0;font-size:20px;">{title}</h2>
  </div>
  <div style="padding:24px;">{lines_html}{btn}</div>
  <div style="background:#f5f5f5;padding:12px 24px;font-size:12px;color:#888;text-align:center;">
    نظام إدارة الاتصالات الإدارية — CCMS
  </div>
</div>"""

def notify_new_correspondence(company_id, corr, assigned_user, settings, base_url='http://localhost:5000'):
    """إشعار معاملة جديدة"""
    if not assigned_user:
        return
    url = f"{base_url}/correspondence/{corr['id']}"
    
    # Email
    if assigned_user.get('email') and settings.get('email_enabled') and settings.get('notify_assigned'):
        html = build_email_html(
            f"📨 معاملة جديدة مُسنَدة إليك",
            [f"السلام عليكم {assigned_user.get('full_name','')},",
             f"تم إسناد معاملة جديدة إليك:",
             f"<b>الرقم المرجعي:</b> {corr['ref_num']}",
             f"<b>الموضوع:</b> {corr['subject']}",
             f"<b>الجهة:</b> {corr['party']}"],
            action_url=url, action_label="عرض المعاملة"
        )
        notify(company_id, assigned_user['id'], 'email',
               assigned_user['email'], f"معاملة جديدة: {corr['subject']}", html, settings)
    
    # WhatsApp
    if assigned_user.get('phone') and settings.get('whatsapp_enabled') and settings.get('notify_assigned'):
        msg = f"📨 معاملة جديدة مُسنَدة إليك\n\nالرقم: {corr['ref_num']}\nالموضوع: {corr['subject']}\nالجهة: {corr['party']}\n\nالرابط: {url}"
        notify(company_id, assigned_user['id'], 'whatsapp',
               assigned_user['phone'], corr['subject'], msg, settings)

def notify_due_soon(company_id, corr, assigned_user, settings, base_url='http://localhost:5000'):
    """إشعار اقتراب الموعد النهائي"""
    if not assigned_user:
        return
    url = f"{base_url}/correspondence/{corr['id']}"
    
    if assigned_user.get('email') and settings.get('email_enabled') and settings.get('notify_due_soon'):
        html = build_email_html(
            "⚠️ تنبيه: اقتراب الموعد النهائي",
            [f"السلام عليكم {assigned_user.get('full_name','')},",
             f"المعاملة التالية تقترب من موعدها النهائي:",
             f"<b>الرقم:</b> {corr['ref_num']}",
             f"<b>الموضوع:</b> {corr['subject']}",
             f"<b>الموعد النهائي:</b> {corr.get('due_date','')}"],
            action_url=url, action_label="عرض المعاملة", color='#ff9800'
        )
        notify(company_id, assigned_user['id'], 'email',
               assigned_user['email'], f"⚠️ اقتراب الموعد النهائي: {corr['ref_num']}", html, settings)
