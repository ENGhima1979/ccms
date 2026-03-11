# دليل النشر السحابي — CCMS v3.0

## 🚀 الخيارات المتاحة

### 1. نشر على VPS (الخادم الخاص) — موصى به
أي خادم Ubuntu 22.04+ من: Contabo, DigitalOcean, Hetzner, AWS EC2

```bash
# على الخادم
sudo apt update && sudo apt install python3-pip nginx certbot python3-certbot-nginx -y

# رفع ملفات المشروع
scp -r corr_pro/ user@YOUR_SERVER:/opt/ccms/

# تثبيت المتطلبات
cd /opt/ccms
pip3 install flask reportlab openpyxl pillow gunicorn --break-system-packages

# تشغيل مؤقت للاختبار
gunicorn -w 4 -b 0.0.0.0:5000 "main:app"
```

### 2. إعداد Systemd (التشغيل التلقائي)
```ini
# /etc/systemd/system/ccms.service
[Unit]
Description=CCMS - Corporate Communication Management System
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/ccms
ExecStart=/usr/local/bin/gunicorn -w 4 -b 127.0.0.1:5000 "main:app"
Restart=always
Environment=FLASK_ENV=production

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable ccms && sudo systemctl start ccms
```

### 3. إعداد Nginx (الوصول من الإنترنت)
```nginx
# /etc/nginx/sites-available/ccms
server {
    listen 80;
    server_name ccms.yourcompany.com;
    
    client_max_body_size 50M;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
    
    location /static/ {
        alias /opt/ccms/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```
```bash
sudo ln -s /etc/nginx/sites-available/ccms /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# SSL مجاني من Let's Encrypt
sudo certbot --nginx -d ccms.yourcompany.com
```

### 4. نشر على Railway.app (أسرع طريقة)
```bash
# 1. ثبّت Railway CLI
npm install -g @railway/cli

# 2. تسجيل دخول
railway login

# 3. نشر
railway init
railway up
```

### 5. نشر على Render.com (مجاني للبداية)
أنشئ `render.yaml` في جذر المشروع:
```yaml
services:
  - type: web
    name: ccms
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn main:app
    envVars:
      - key: FLASK_ENV
        value: production
```

---

## 🔒 نقاط أمان مهمة للإنتاج

```python
# في main.py — قبل النشر
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-in-production')
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
```

```bash
# متغيرات البيئة المطلوبة
export SECRET_KEY="your-super-secret-key-here"
export FLASK_ENV=production
```

---

## 📦 متطلبات النشر

```
flask>=3.0
reportlab>=4.0
openpyxl>=3.1
Pillow>=10.0
gunicorn>=21.0
```

---

## 🌐 نطاق مخصص + SSL
بعد إعداد Nginx:
1. اشترِ نطاقاً من Namecheap أو GoDaddy
2. أضف A Record يشير لـ IP الخادم
3. نفّذ: `sudo certbot --nginx -d yourdomain.com`
