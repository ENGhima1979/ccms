import os, sys
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
os.makedirs(os.path.join(BASE, 'instance'), exist_ok=True)
os.makedirs(os.path.join(BASE, 'instance', 'uploads'), exist_ok=True)

# Initialize DB - safe even if already exists
try:
    from models import init_db
    init_db()
except Exception:
    pass  # DB already initialized - that's fine

from main import app

if __name__ == '__main__':
    print("\n" + "="*55)
    print("  CCMS v2.0 - نظام ادارة الاتصالات الادارية")
    print("="*55)
    print("  الرابط  : http://localhost:5000")
    print("  المدير  : admin  /  Admin@2025")
    print("  المشرف  : pm_manager  /  User@2025")
    print("="*55 + "\n")

    import webbrowser, threading, time
    threading.Thread(target=lambda: (time.sleep(1.5), webbrowser.open('http://localhost:5000')), daemon=True).start()

    app.run(debug=False, host='0.0.0.0', port=5000)
