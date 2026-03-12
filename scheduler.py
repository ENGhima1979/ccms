"""
scheduler.py — المجدول التلقائي لـ CCMS
--------------------------------------
- تنبيهات SLA عند اقتراب الموعد
- تنبيهات انتهاء المواعيد النهائية
- تنبيهات خطوات سير العمل المتأخرة
- تقرير يومي للمديرين
يعمل في background thread داخل Flask
"""

import datetime
import logging
from helpers import create_notification

logger = logging.getLogger(__name__)


def check_sla_alerts(app):
    """فحص المراسلات التي تقترب من SLA وأرسل تنبيهات"""
    with app.app_context():
        try:
            from main import get_db
            conn = get_db()
            now  = datetime.datetime.now()

            # المراسلات الواردة المنتظرة للرد منذ أكثر من 48 ساعة
            rows = conn.execute("""
                SELECT c.*, u.id as owner_id, u.full_name as owner_name,
                       co.name as company_name
                FROM correspondence c
                JOIN users u ON c.created_by = u.id
                JOIN companies co ON c.company_id = co.id
                WHERE c.type = 'in'
                  AND c.reply_status = 'pending'
                  AND c.is_deleted = 0
                  AND c.archived = 0
                  AND c.date IS NOT NULL
            """).fetchall()

            alerted = 0
            for r in rows:
                try:
                    corr_date = datetime.datetime.fromisoformat(r['date'][:10])
                    age_hours = (now - corr_date).total_seconds() / 3600

                    # تنبيه عند 48 ساعة (تحذير) و 72 ساعة (تجاوز)
                    if 47 <= age_hours <= 49:
                        create_notification(
                            r['owner_id'], 'sla',
                            f'⚠️ اقتراب SLA: {r["ref_num"]}',
                            f'المراسلة لم يُرد عليها منذ 48 ساعة',
                            f'/correspondence/{r["id"]}', conn)
                        alerted += 1
                    elif 71 <= age_hours <= 73:
                        create_notification(
                            r['owner_id'], 'sla',
                            f'🔴 تجاوز SLA: {r["ref_num"]}',
                            f'المراسلة تجاوزت 72 ساعة بدون رد — يتطلب إجراء فوري',
                            f'/correspondence/{r["id"]}', conn)
                        alerted += 1
                except Exception:
                    pass

            conn.commit()
            conn.close()
            if alerted:
                logger.info(f'[Scheduler] SLA alerts sent: {alerted}')
        except Exception as e:
            logger.error(f'[Scheduler] SLA check failed: {e}')


def check_deadline_alerts(app):
    """تنبيهات المواعيد النهائية القادمة خلال 24 ساعة"""
    with app.app_context():
        try:
            from main import get_db
            conn = get_db()
            now     = datetime.datetime.now()
            in_24h  = (now + datetime.timedelta(hours=24)).strftime('%Y-%m-%d')
            today   = now.strftime('%Y-%m-%d')

            rows = conn.execute("""
                SELECT c.*, u.id as owner_id
                FROM correspondence c
                JOIN users u ON c.created_by = u.id
                WHERE c.due_date IS NOT NULL
                  AND c.due_date BETWEEN ? AND ?
                  AND c.status NOT IN ('approved','closed','archived')
                  AND c.is_deleted = 0
            """, (today, in_24h)).fetchall()

            for r in rows:
                create_notification(
                    r['owner_id'], 'deadline',
                    f'📅 موعد نهائي غداً: {r["ref_num"]}',
                    f'الموعد النهائي: {r["due_date"]} | {r["subject"][:60]}',
                    f'/correspondence/{r["id"]}', conn)

            # مواعيد تجاوزت اليوم
            overdue = conn.execute("""
                SELECT c.*, u.id as owner_id
                FROM correspondence c
                JOIN users u ON c.created_by = u.id
                WHERE c.due_date < ?
                  AND c.status NOT IN ('approved','closed','archived')
                  AND c.is_deleted = 0
            """, (today,)).fetchall()

            for r in overdue:
                create_notification(
                    r['owner_id'], 'deadline',
                    f'🚨 تجاوز الموعد النهائي: {r["ref_num"]}',
                    f'كان موعده {r["due_date"]} — يتطلب إجراء فوري',
                    f'/correspondence/{r["id"]}', conn)

            conn.commit()
            conn.close()
            logger.info(f'[Scheduler] Deadline check done: {len(rows)} upcoming, {len(overdue)} overdue')
        except Exception as e:
            logger.error(f'[Scheduler] Deadline check failed: {e}')


def check_workflow_alerts(app):
    """تنبيه لخطوات سير العمل المتأخرة أكثر من 24 ساعة"""
    with app.app_context():
        try:
            from main import get_db
            conn  = get_db()
            limit = (datetime.datetime.now() - datetime.timedelta(hours=24)).isoformat()

            stale = conn.execute("""
                SELECT ws.*, c.ref_num, c.subject
                FROM workflow_steps ws
                JOIN correspondence c ON ws.correspondence_id = c.id
                WHERE ws.status = 'pending'
                  AND ws.created_at < ?
                  AND ws.assigned_to IS NOT NULL
                  AND c.is_deleted = 0
            """, (limit,)).fetchall()

            for s in stale:
                create_notification(
                    s['assigned_to'], 'workflow',
                    f'⏰ خطوة متأخرة: {s["ref_num"]}',
                    f'"{s["step_name"]}" في انتظار موافقتك منذ أكثر من 24 ساعة',
                    f'/correspondence/{s["correspondence_id"]}', conn)

            conn.commit()
            conn.close()
            logger.info(f'[Scheduler] Workflow alerts: {len(stale)} stale steps')
        except Exception as e:
            logger.error(f'[Scheduler] Workflow check failed: {e}')


def send_daily_digest(app):
    """ملخص يومي للمديرين (8 صباحاً)"""
    with app.app_context():
        try:
            from main import get_db
            conn  = get_db()
            today = datetime.date.today().isoformat()
            yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

            companies = conn.execute(
                "SELECT * FROM companies WHERE is_active=1").fetchall()

            for co in companies:
                cid = co['id']
                # إحصاء المراسلات الجديدة أمس
                new_count = conn.execute("""
                    SELECT COUNT(*) as c FROM correspondence
                    WHERE company_id=? AND date=? AND is_deleted=0
                """, (cid, yesterday)).fetchone()['c']

                pending_wf = conn.execute("""
                    SELECT COUNT(*) as c FROM workflow_steps ws
                    JOIN correspondence c ON ws.correspondence_id=c.id
                    WHERE c.company_id=? AND ws.status='pending'
                """, (cid,)).fetchone()['c']

                overdue_sla = conn.execute("""
                    SELECT COUNT(*) as c FROM correspondence
                    WHERE company_id=? AND type='in' AND reply_status='pending'
                    AND is_deleted=0 AND date < date('now','-3 days')
                """, (cid,)).fetchone()['c']

                # أرسل للمديرين فقط إذا كانت هناك أرقام مهمة
                if new_count > 0 or pending_wf > 0 or overdue_sla > 0:
                    managers = conn.execute("""
                        SELECT id FROM users
                        WHERE company_id=? AND role IN ('admin','manager') AND is_active=1
                    """, (cid,)).fetchall()

                    for mgr in managers:
                        create_notification(
                            mgr['id'], 'digest',
                            f'📊 ملخص يوم {yesterday}',
                            f'جديدة: {new_count} | بانتظار موافقة: {pending_wf} | متجاوزة SLA: {overdue_sla}',
                            '/reports', conn)

            conn.commit()
            conn.close()
            logger.info('[Scheduler] Daily digest sent')
        except Exception as e:
            logger.error(f'[Scheduler] Daily digest failed: {e}')


def start_scheduler(app):
    """تشغيل المجدول مع Flask"""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        scheduler = BackgroundScheduler(timezone='Asia/Riyadh', daemon=True)

        # فحص SLA كل ساعة
        scheduler.add_job(
            check_sla_alerts, IntervalTrigger(hours=1),
            args=[app], id='sla_check', replace_existing=True)

        # فحص المواعيد كل 6 ساعات
        scheduler.add_job(
            check_deadline_alerts, IntervalTrigger(hours=6),
            args=[app], id='deadline_check', replace_existing=True)

        # فحص سير العمل كل 4 ساعات
        scheduler.add_job(
            check_workflow_alerts, IntervalTrigger(hours=4),
            args=[app], id='workflow_check', replace_existing=True)

        # ملخص يومي الساعة 8 صباحاً بالرياض
        scheduler.add_job(
            send_daily_digest, CronTrigger(hour=8, minute=0),
            args=[app], id='daily_digest', replace_existing=True)

        scheduler.start()
        logger.info('✅ [Scheduler] Started — SLA/Deadline/Workflow/Digest jobs active')
        return scheduler

    except ImportError:
        logger.warning('[Scheduler] APScheduler not installed — alerts disabled')
        return None
    except Exception as e:
        logger.error(f'[Scheduler] Failed to start: {e}')
        return None
