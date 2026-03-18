import os, sys, shutil, traceback

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

def organize_files():
    for d in ['templates','fonts','static/icons','translations','static','instance','instance/uploads']:
        os.makedirs(os.path.join(BASE, d), exist_ok=True)
    for f in os.listdir(BASE):
        fp = os.path.join(BASE, f)
        if not os.path.isfile(fp): continue
        if f.endswith('.html'):
            dst = os.path.join(BASE, 'templates', f)
            # دائماً انسخ — لا تتحقق من الوجود (يضمن تحديث الملفات عند كل نشر)
            shutil.copy2(fp, dst)
        elif f.endswith('.ttf'):
            dst = os.path.join(BASE, 'fonts', f)
            if not os.path.exists(dst): shutil.copy2(fp, dst)
        elif f.startswith('icon-') and f.endswith('.png'):
            dst = os.path.join(BASE, 'static', 'icons', f)
            if not os.path.exists(dst): shutil.copy2(fp, dst)
    for fname in ['ar.json', 'en.json']:
        src = os.path.join(BASE, fname)
        if os.path.exists(src):
            dst = os.path.join(BASE, 'translations', fname)
            shutil.copy2(src, dst)  # دائماً حدّث
    for fname in ['manifest.json', 'sw.js']:
        src = os.path.join(BASE, fname)
        if os.path.exists(src):
            dst = os.path.join(BASE, 'static', fname)
            shutil.copy2(src, dst)  # دائماً حدّث
    print("Files organized")

try:
    organize_files()
except Exception as e:
    print(f"organize error: {e}")

# ── إصلاح FTS5 triggers تلقائياً عند بدء التطبيق ──────────────
def fix_fts_triggers():
    """
    يصلح triggers الـ FTS5 التي تسبب خطأ T.correspondence_id
    يعمل مرة واحدة فقط — آمن للتشغيل المتكرر
    """
    try:
        import sqlite3
        db_path = os.path.join(BASE, 'instance', 'ccms.db')
        if not os.path.exists(db_path):
            return  # DB لم تنشأ بعد
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        # تحقق من نوع الـ FTS الحالي
        fts = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='corr_fts' AND type='table'"
        ).fetchone()
        needs_fix = fts and ("content='correspondence'" in (fts['sql'] or ''))
        if needs_fix:
            print("[STARTUP] Fixing FTS5 triggers...")
            conn.execute("DROP TRIGGER IF EXISTS corr_fts_insert")
            conn.execute("DROP TRIGGER IF EXISTS corr_fts_update")
            conn.execute("DROP TRIGGER IF EXISTS corr_fts_delete")
            conn.execute("DROP TABLE IF EXISTS corr_fts")
            conn.execute('''CREATE VIRTUAL TABLE corr_fts USING fts5(
                correspondence_id,
                ref_num,
                subject,
                body,
                party,
                action_required,
                tokenize="unicode61"
            )''')
            conn.execute('''CREATE TRIGGER corr_fts_insert
                AFTER INSERT ON correspondence BEGIN
                    INSERT INTO corr_fts(correspondence_id,ref_num,subject,body,party,action_required)
                    VALUES (new.id,new.ref_num,new.subject,
                            COALESCE(new.body,''),COALESCE(new.party,''),
                            COALESCE(new.action_required,''));
                END''')
            conn.execute('''CREATE TRIGGER corr_fts_update
                AFTER UPDATE ON correspondence BEGIN
                    DELETE FROM corr_fts WHERE correspondence_id=old.id;
                    INSERT INTO corr_fts(correspondence_id,ref_num,subject,body,party,action_required)
                    VALUES (new.id,new.ref_num,new.subject,
                            COALESCE(new.body,''),COALESCE(new.party,''),
                            COALESCE(new.action_required,''));
                END''')
            conn.execute('''CREATE TRIGGER corr_fts_delete
                AFTER DELETE ON correspondence BEGIN
                    DELETE FROM corr_fts WHERE correspondence_id=old.id;
                END''')
            conn.execute('''INSERT INTO corr_fts(correspondence_id,ref_num,subject,body,party,action_required)
                SELECT id, ref_num, subject,
                       COALESCE(body,''), COALESCE(party,''), COALESCE(action_required,'')
                FROM correspondence WHERE is_deleted=0''')
            conn.commit()
            print("[STARTUP] FTS5 triggers fixed successfully")
        else:
            print("[STARTUP] FTS5 OK — no fix needed")
        conn.close()
    except Exception as e:
        print(f"[STARTUP] FTS fix warning (non-fatal): {e}")

fix_fts_triggers()
# ────────────────────────────────────────────────────────────────

try:
    from main import app
    print("App loaded OK")
except Exception as e:
    print(f"FATAL IMPORT ERROR: {e}")
    traceback.print_exc()
    raise

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"Starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
