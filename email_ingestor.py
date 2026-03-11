"""
استقبال البريد الإلكتروني تلقائياً — المرحلة الثالثة
يتصل بصندوق IMAP ويحول الرسائل لمعاملات واردة
"""
import imaplib, email, json
from email.header import decode_header
from models import get_db, new_id, now, today

def decode_str(s):
    if s is None: return ''
    parts = decode_header(s)
    result = ''
    for part, enc in parts:
        if isinstance(part, bytes):
            result += part.decode(enc or 'utf-8', errors='replace')
        else:
            result += str(part)
    return result.strip()

def get_body(msg):
    body = ''
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get('Content-Disposition',''))
            if ct == 'text/plain' and 'attachment' not in cd:
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    body = part.get_payload(decode=True).decode(charset, errors='replace')
                    break
                except: pass
    else:
        try:
            charset = msg.get_content_charset() or 'utf-8'
            body = msg.get_payload(decode=True).decode(charset, errors='replace')
        except: pass
    return body[:5000]

def fetch_and_import(company_id, user_id, cfg):
    """Connect to IMAP and import new emails as incoming correspondence"""
    host     = cfg.get('imap_host','')
    port     = int(cfg.get('imap_port', 993))
    username = cfg.get('imap_user','')
    password = cfg.get('imap_password','')
    folder   = cfg.get('imap_folder','INBOX')
    mark_read= bool(cfg.get('mark_read', True))

    if not all([host, username, password]):
        raise Exception("إعدادات IMAP غير مكتملة")

    # Connect
    mail = imaplib.IMAP4_SSL(host, port)
    mail.login(username, password)
    mail.select(folder)

    # Search unread
    _, data = mail.search(None, 'UNSEEN')
    email_ids = data[0].split()
    
    if not email_ids:
        mail.close(); mail.logout()
        return 0

    conn = get_db()
    
    # Get company code for ref_num
    co = conn.execute("SELECT code FROM companies WHERE id=?", (company_id,)).fetchone()
    co_code = co['code'] if co else 'CO'
    
    imported = 0
    import datetime
    year = datetime.datetime.now().year

    for eid in email_ids[-50:]:  # Max 50 at a time
        _, msg_data = mail.fetch(eid, '(RFC822)')
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        subject = decode_str(msg.get('Subject','(بدون موضوع)'))
        from_   = decode_str(msg.get('From',''))
        date_   = msg.get('Date','')
        body    = get_body(msg)

        # Extract sender name and email
        import re
        email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', from_)
        sender_email = email_match.group() if email_match else from_
        sender_name  = re.sub(r'<.*?>', '', from_).strip().strip('"') or sender_email

        # Generate ref_num
        seq = conn.execute(
            "SELECT COUNT(*)+1 as n FROM correspondence WHERE company_id=? AND type='in' AND substr(created_at,1,4)=?",
            (company_id, str(year))).fetchone()['n']
        ref_num = f"{co_code}-{year}-IN-{str(seq).zfill(5)}"

        # Check duplicate
        exists = conn.execute(
            "SELECT id FROM correspondence WHERE company_id=? AND metadata_json LIKE ?",
            (company_id, f'%{eid.decode()}%')).fetchone()
        if exists:
            continue

        cid = new_id()
        metadata = json.dumps({
            'source': 'email',
            'email_id': eid.decode(),
            'sender_email': sender_email,
            'original_date': date_,
        })

        conn.execute("""INSERT INTO correspondence
            (id,company_id,ref_num,type,subject,party,body,status,priority,
             category,date,created_by,created_at,metadata_json)
            VALUES (?,?,?,'in',?,?,?,'pending','normal','incoming',?,?,?,?)""",
            (cid, company_id, ref_num, subject, sender_name, body,
             today(), user_id, now(), metadata))
        
        if mark_read:
            mail.store(eid, '+FLAGS', '\\Seen')
        
        imported += 1

    conn.commit()
    conn.close()
    mail.close()
    mail.logout()
    return imported
