# -*- coding: utf-8 -*-
"""
CCMS SaaS Engine — إدارة الخطط والاشتراكات والحدود
"""
import json
from datetime import date, datetime, timedelta
from models import get_db, now, new_id

# ══════════════════════════════════════════════════════
#  تعريف الخطط
# ══════════════════════════════════════════════════════
PLANS = {
    'trial': {
        'name':        'تجريبي',
        'name_en':     'Free Trial',
        'color':       '#546E7A',
        'icon':        '🆓',
        'price_sar':   0,
        'duration_days': 14,
        'limits': {
            'users':          3,
            'correspondences': 50,
            'projects':        2,
            'storage_mb':      100,
            'ai_requests':     10,
            'advanced_reports': False,
            'api_access':       False,
            'custom_workflow':  False,
            'multi_branch':     False,
        },
        'features': ['3 مستخدمين', '50 معاملة', 'مشروعان', '14 يوم مجاناً'],
    },
    'starter': {
        'name':        'ستارتر',
        'name_en':     'Starter',
        'color':       '#00B4D8',
        'icon':        '🚀',
        'price_sar':   299,
        'duration_days': 30,
        'limits': {
            'users':          10,
            'correspondences': 500,
            'projects':        5,
            'storage_mb':      1024,
            'ai_requests':     100,
            'advanced_reports': False,
            'api_access':       False,
            'custom_workflow':  True,
            'multi_branch':     False,
        },
        'features': ['10 مستخدمين', '500 معاملة/شهر', '5 مشاريع', '1 جيجابايت', 'سير عمل مخصص'],
    },
    'business': {
        'name':        'بيزنس',
        'name_en':     'Business',
        'color':       '#06FFA5',
        'icon':        '💼',
        'price_sar':   799,
        'duration_days': 30,
        'limits': {
            'users':          50,
            'correspondences': 5000,
            'projects':        20,
            'storage_mb':      10240,
            'ai_requests':     1000,
            'advanced_reports': True,
            'api_access':       True,
            'custom_workflow':  True,
            'multi_branch':     False,
        },
        'features': ['50 مستخدماً', '5,000 معاملة/شهر', '20 مشروع', '10 جيجابايت', 'AI كامل', 'API', 'تقارير متقدمة'],
        'popular': True,
    },
    'enterprise': {
        'name':        'إنتربرايز',
        'name_en':     'Enterprise',
        'color':       '#FFC107',
        'icon':        '🏢',
        'price_sar':   1999,
        'duration_days': 30,
        'limits': {
            'users':          -1,    # غير محدود
            'correspondences': -1,
            'projects':        -1,
            'storage_mb':      -1,
            'ai_requests':     -1,
            'advanced_reports': True,
            'api_access':       True,
            'custom_workflow':  True,
            'multi_branch':     True,
        },
        'features': ['مستخدمون غير محدودين', 'معاملات غير محدودة', 'تخزين غير محدود', 'جميع المميزات', 'دعم مخصص', 'تعدد الفروع'],
    },
}

# ══════════════════════════════════════════════════════
#  دوال الاشتراك
# ══════════════════════════════════════════════════════

def get_company_subscription(company_id):
    """جلب بيانات اشتراك الشركة كاملة"""
    conn = get_db()
    co = conn.execute("SELECT * FROM companies WHERE id=?", (company_id,)).fetchone()
    conn.close()
    if not co:
        return None

    settings = {}
    try:
        settings = json.loads(co['settings_json']) if co['settings_json'] else {}
    except Exception:
        pass

    sub = settings.get('subscription', {})
    plan_key = sub.get('plan', co['subscription_plan'] or 'trial')
    if plan_key not in PLANS:
        plan_key = 'trial'

    plan = PLANS[plan_key]
    end_date_str = sub.get('end_date', co['subscription_expiry'] or '')

    # حساب الأيام المتبقية
    days_left = None
    is_expired = False
    if end_date_str:
        try:
            end_dt = date.fromisoformat(end_date_str[:10])
            days_left = (end_dt - date.today()).days
            is_expired = days_left < 0
        except Exception:
            pass

    return {
        'plan_key':    plan_key,
        'plan':        plan,
        'end_date':    end_date_str,
        'days_left':   days_left,
        'is_expired':  is_expired,
        'is_active':   bool(co['is_active']) and not is_expired,
        'auto_renew':  sub.get('auto_renew', False),
        'notes':       sub.get('notes', ''),
        'activated_at': sub.get('activated_at', ''),
    }


def check_limit(company_id, resource):
    """
    تحقق من حد معين
    Returns: (allowed: bool, current: int, limit: int, message: str)
    """
    sub = get_company_subscription(company_id)
    if not sub:
        return False, 0, 0, 'الشركة غير موجودة'

    limit = sub['plan']['limits'].get(resource, 0)
    if limit == -1:
        return True, 0, -1, ''  # غير محدود

    conn = get_db()
    current = 0

    if resource == 'users':
        current = conn.execute(
            "SELECT COUNT(*) as c FROM users WHERE company_id=? AND is_active=1",
            (company_id,)).fetchone()['c']
    elif resource == 'correspondences':
        # عدد المعاملات في الشهر الحالي
        month_start = date.today().replace(day=1).isoformat()
        current = conn.execute(
            "SELECT COUNT(*) as c FROM correspondence WHERE company_id=? AND date>=? AND is_deleted=0",
            (company_id, month_start)).fetchone()['c']
    elif resource == 'projects':
        current = conn.execute(
            "SELECT COUNT(*) as c FROM projects WHERE company_id=? AND is_active=1",
            (company_id,)).fetchone()['c']

    conn.close()

    if isinstance(limit, bool):
        allowed = limit
        return allowed, 0, 0, ('' if allowed else f'هذه الميزة غير متاحة في خطة {sub["plan"]["name"]}')

    allowed = current < limit
    msg = '' if allowed else f'وصلت للحد الأقصى ({limit}) في خطة {sub["plan"]["name"]}'
    return allowed, current, limit, msg


def activate_subscription(company_id, plan_key, duration_days=None, notes=''):
    """تفعيل اشتراك جديد أو تجديد"""
    if plan_key not in PLANS:
        return False, 'خطة غير موجودة'

    plan = PLANS[plan_key]
    days = duration_days or plan['duration_days']
    end_date = (date.today() + timedelta(days=days)).isoformat()

    conn = get_db()
    co = conn.execute("SELECT settings_json FROM companies WHERE id=?", (company_id,)).fetchone()
    if not co:
        conn.close()
        return False, 'الشركة غير موجودة'

    settings = {}
    try:
        settings = json.loads(co['settings_json']) if co['settings_json'] else {}
    except Exception:
        pass

    settings['subscription'] = {
        'plan':         plan_key,
        'end_date':     end_date,
        'activated_at': now(),
        'duration_days': days,
        'notes':        notes,
        'auto_renew':   False,
    }

    conn.execute(
        "UPDATE companies SET settings_json=?, subscription_plan=?, subscription_expiry=?, is_active=1 WHERE id=?",
        (json.dumps(settings, ensure_ascii=False), plan_key, end_date, company_id)
    )

    # تسجيل في سجل الفواتير
    conn.execute("""
        INSERT OR IGNORE INTO billing_log
        (id, company_id, plan, amount_sar, start_date, end_date, notes, created_at)
        VALUES (?,?,?,?,?,?,?,?)""",
        (new_id(), company_id, plan_key, plan['price_sar'],
         date.today().isoformat(), end_date, notes, now()))

    conn.commit()
    conn.close()
    return True, f'تم تفعيل خطة {plan["name"]} حتى {end_date}'


def get_usage_stats(company_id):
    """إحصائيات الاستخدام الحالية"""
    conn = get_db()
    month_start = date.today().replace(day=1).isoformat()

    stats = {
        'users':          conn.execute("SELECT COUNT(*) as c FROM users WHERE company_id=? AND is_active=1", (company_id,)).fetchone()['c'],
        'correspondences': conn.execute("SELECT COUNT(*) as c FROM correspondence WHERE company_id=? AND date>=? AND is_deleted=0", (company_id, month_start)).fetchone()['c'],
        'projects':       conn.execute("SELECT COUNT(*) as c FROM projects WHERE company_id=? AND is_active=1", (company_id,)).fetchone()['c'],
        'total_corr':     conn.execute("SELECT COUNT(*) as c FROM correspondence WHERE company_id=? AND is_deleted=0", (company_id,)).fetchone()['c'],
    }
    conn.close()
    return stats


def get_all_companies_stats():
    """إحصائيات جميع الشركات للـ Super Admin"""
    conn = get_db()
    companies = conn.execute("""
        SELECT c.*,
            (SELECT COUNT(*) FROM users WHERE company_id=c.id AND is_active=1) as user_count,
            (SELECT COUNT(*) FROM correspondence WHERE company_id=c.id AND is_deleted=0) as corr_count,
            (SELECT COUNT(*) FROM projects WHERE company_id=c.id AND is_active=1) as proj_count,
            (SELECT MAX(created_at) FROM correspondence WHERE company_id=c.id) as last_activity
        FROM companies c ORDER BY c.created_at DESC
    """).fetchall()
    conn.close()

    result = []
    for co in companies:
        sub = get_company_subscription(co['id'])
        result.append({
            'co':  dict(co),
            'sub': sub,
        })
    return result
