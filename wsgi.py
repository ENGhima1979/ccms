import os, sys, shutil

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

def organize_files():
    tmpl_dir  = os.path.join(BASE, 'templates')
    font_dir  = os.path.join(BASE, 'fonts')
    icon_dir  = os.path.join(BASE, 'static', 'icons')
    trans_dir = os.path.join(BASE, 'translations')
    stat_dir  = os.path.join(BASE, 'static')

    for d in [tmpl_dir, font_dir, icon_dir, trans_dir, stat_dir]:
        os.makedirs(d, exist_ok=True)

    for f in os.listdir(BASE):
        if f.endswith('.html'):
            dst = os.path.join(tmpl_dir, f)
            if not os.path.exists(dst):
                shutil.copy2(os.path.join(BASE, f), dst)
        elif f.endswith('.ttf'):
            dst = os.path.join(font_dir, f)
            if not os.path.exists(dst):
                shutil.copy2(os.path.join(BASE, f), dst)
        elif f.startswith('icon-') and f.endswith('.png'):
            dst = os.path.join(icon_dir, f)
            if not os.path.exists(dst):
                shutil.copy2(os.path.join(BASE, f), dst)

    for f in ['ar.json', 'en.json']:
        src = os.path.join(BASE, f)
        if os.path.exists(src):
            dst = os.path.join(trans_dir, f)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)

    for f in ['manifest.json', 'sw.js']:
        src = os.path.join(BASE, f)
        if os.path.exists(src):
            dst = os.path.join(stat_dir, f)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)

    print("Files organized")

organize_files()

os.makedirs(os.path.join(BASE, 'instance'), exist_ok=True)
os.makedirs(os.path.join(BASE, 'instance', 'uploads'), exist_ok=True)

try:
    from models import init_db
    init_db()
    print("Database ready")
except Exception as e:
    print(f"DB: {e}")

from main import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
