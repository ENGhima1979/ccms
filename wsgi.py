import os, sys, shutil

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

def organize_files():
    """
    Railway receives all files flat — this function puts them in correct folders.
    Only runs if structure is not already correct.
    """
    # Define which files go where
    html_files = [f for f in os.listdir(BASE) if f.endswith('.html')]
    ttf_files  = [f for f in os.listdir(BASE) if f.endswith('.ttf')]
    png_files  = [f for f in os.listdir(BASE) if f.startswith('icon-') and f.endswith('.png')]
    json_files = ['ar.json', 'en.json']
    sw_files   = ['sw.js', 'manifest.json']

    # Create folders
    tmpl_dir  = os.path.join(BASE, 'templates')
    font_dir  = os.path.join(BASE, 'fonts')
    icon_dir  = os.path.join(BASE, 'static', 'icons')
    trans_dir = os.path.join(BASE, 'translations')
    stat_dir  = os.path.join(BASE, 'static')

    for d in [tmpl_dir, font_dir, icon_dir, trans_dir, stat_dir]:
        os.makedirs(d, exist_ok=True)

    # Move HTML -> templates/
    for f in html_files:
        src = os.path.join(BASE, f)
        dst = os.path.join(tmpl_dir, f)
        if not os.path.exists(dst):
            shutil.copy2(src, dst)

    # Move TTF -> fonts/
    for f in ttf_files:
        src = os.path.join(BASE, f)
        dst = os.path.join(font_dir, f)
        if not os.path.exists(dst):
            shutil.copy2(src, dst)

    # Move icon PNGs -> static/icons/
    for f in png_files:
        src = os.path.join(BASE, f)
        dst = os.path.join(icon_dir, f)
        if not os.path.exists(dst):
            shutil.copy2(src, dst)

    # Move ar.json / en.json -> translations/
    for f in json_files:
        src = os.path.join(BASE, f)
        if os.path.exists(src):
            dst = os.path.join(trans_dir, f)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)

    # Move sw.js / manifest.json -> static/
    for f in sw_files:
        src = os.path.join(BASE, f)
        if os.path.exists(src):
            dst = os.path.join(stat_dir, f)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)

    print("✅ File structure organized successfully")

# Run organization
organize_files()

# Create required runtime folders
os.makedirs(os.path.join(BASE, 'instance'), exist_ok=True)
os.makedirs(os.path.join(BASE, 'instance', 'uploads'), exist_ok=True)

# Init DB
try:
    from models import init_db
    init_db()
    print("✅ Database initialized")
except Exception as e:
    print(f"DB init: {e}")

from main import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
