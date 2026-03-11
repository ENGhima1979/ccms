import os, sys, shutil

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

def organize_files():
    """Move flat files into correct subfolders before Flask starts."""
    
    tmpl_dir  = os.path.join(BASE, 'templates')
    font_dir  = os.path.join(BASE, 'fonts')
    icon_dir  = os.path.join(BASE, 'static', 'icons')
    trans_dir = os.path.join(BASE, 'translations')
    stat_dir  = os.path.join(BASE, 'static')

    for d in [tmpl_dir, font_dir, icon_dir, trans_dir, stat_dir]:
        os.makedirs(d, exist_ok=True)

    # HTML files → templates/
    for f in os.listdir(BASE):
        if f.endswith('.html'):
            dst = os.path.join(tmpl_dir, f)
            if not os.path.exists(dst):
                shutil.copy2(os.path.join(BASE, f), dst)
                print(f"  → templates/{f}")

    # TTF files → fonts/
    for f in os.listdir(BASE):
        if f.endswith('.ttf'):
            dst = os.path.join(font_dir, f)
            if not os.path.exists(dst):
                shutil.copy2(os.path.join(BASE, f), dst)
                print(f"  → fonts/{f}")

    # icon-*.png → static/icons/
    for f in os.listdir(BASE):
        if f.startswith('icon-') and f.endswith('.png'):
            dst = os.path.join(icon_dir, f)
            if not os.path.exists(dst):
                shutil.copy2(os.path.join(BASE, f), dst)
                print(f"  → static/icons/{f}")

    # ar.json / en.json → translations/
    for f in ['ar.json', 'en.json']:
        src = os.path.join(BASE, f)
        if os.path.exists(src):
            dst = os.path.join(trans_dir, f)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)
                print(f"  → translations/{f}")

    # manifest.json / sw.js → static/
    for f in ['manifest.json', 'sw.js']:
        src = os.path.join(BASE, f)
        if os.path.exists(src):
            dst = os.path.join(stat_dir, f)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)
                print(f"  → static/{f}")

    print("✅ Files organized")

print("🚀 Starting CCMS...")
organize_files()

# Instance folders
os.makedirs(os.path.join(BASE, 'instance'), exist_ok=True)
os.makedirs(os.path.join(BASE, 'instance', 'uploads'), exist_ok=True)

# Init DB
try:
    from models import init_db
    init_db()
    print("✅ Database ready")
except Exception as e:
    print(f"DB: {e}")

# NOW import Flask app (after folders are ready)
from main import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
