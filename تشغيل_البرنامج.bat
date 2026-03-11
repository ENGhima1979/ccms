@echo off
chcp 65001 >nul
title CCMS - نظام إدارة الاتصالات الإدارية
color 0B

echo.
echo  ============================================
echo   نظام إدارة الاتصالات الإدارية - CCMS v2
echo  ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  [خطأ] Python غير مثبت!
    echo  نزله من: https://www.python.org/downloads/
    echo  تاكد من تفعيل "Add Python to PATH"
    pause
    exit
)

echo  [1/3] تثبيت المتطلبات...
pip install flask werkzeug reportlab openpyxl pillow --quiet --exists-action i

echo  [2/3] تهيئة قاعدة البيانات...
if exist instance\ccms.db (
    echo  قاعدة البيانات موجودة - تخطي التهيئة
)

echo  [3/3] تشغيل النظام...
echo.
echo  ============================================
echo   الرابط  : http://localhost:5000
echo   المدير  : admin  /  Admin@2025
echo  ============================================
echo.

python run.py

if errorlevel 1 (
    echo.
    echo  [خطأ] راجع الرسالة اعلاه
    pause
)
