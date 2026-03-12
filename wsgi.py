import os, sys, shutil

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
            if not os.path.exists(dst): shutil.copy2(fp, dst)
        elif f.endswith('.ttf'):
            dst = os.path.join(BASE, 'fonts', f)
            if not os.path.exists(dst): shutil.copy2(fp, dst)
        elif f.startswith('icon-') and f.endswith('.png'):
            dst = os.path.join(BASE, 'static', 'icons', f)
            if not os.path.exists(dst): shutil.copy2(fp, dst)

    for f in ['ar.json', 'en.json']:
        src = os.path.join(BASE, f)
        if os.path.exists(src):
            dst = os.path.join(BASE, 'translations', f)
            if not os.path.exists(dst): shutil.copy2(src, dst)

    for f in ['manifest.json', 'sw.js']:
        src = os.path.join(BASE, f)
        if os.path.exists(src):
            dst = os.path.join(BASE, 'static', f)
            if not os.path.exists(dst): shutil.copy2(src, dst)

    print("Files organized")

organize_files()
print("Database ready")

# Import app — main.py handles init_db internally on startup
from main import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"Starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
