"""
محرك الذكاء الاصطناعي — المرحلة الثانية
يستخدم Claude API للتصنيف والتحليل واقتراح الردود
"""
import json, os, urllib.request, urllib.error
from models import get_db, new_id, now

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"  # سريع واقتصادي للتحليل

def _call_claude(system_prompt, user_prompt, api_key, max_tokens=1000):
    """استدعاء Claude API"""
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}]
    }).encode('utf-8')

    req = urllib.request.Request(
        CLAUDE_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data['content'][0]['text'], data.get('usage', {}).get('input_tokens', 0) + data.get('usage', {}).get('output_tokens', 0)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        raise Exception(f"API Error {e.code}: {error_body}")

def analyze_correspondence(corr_id, company_id, api_key):
    """تحليل مراسلة كاملة بالذكاء الاصطناعي"""
    conn = get_db()
    corr = conn.execute("""
        SELECT c.*, p.name as proj_name 
        FROM correspondence c
        LEFT JOIN projects p ON c.project_id = p.id
        WHERE c.id = ? AND c.company_id = ?
    """, (corr_id, company_id)).fetchone()
    
    if not corr:
        conn.close()
        raise Exception("المراسلة غير موجودة")

    subject = corr['subject'] or ''
    body    = corr['body'] or ''
    party   = corr['party'] or ''
    corr_type = {'out':'صادر','in':'وارد','internal':'داخلي'}.get(corr['type'],'')

    system = """أنت محلل مراسلات إداري خبير في شركات المقاولات السعودية.
مهمتك تحليل المراسلات الإدارية وإرجاع JSON فقط بالشكل التالي (لا تضف أي نص خارج JSON):
{
  "category": "تصنيف رئيسي واحد من: مالي | تقني | قانوني | إداري | موارد_بشرية | مشتريات | مشاريع | عام",
  "subcategory": "تصنيف فرعي مختصر",
  "priority": "urgent | high | normal | low",
  "sentiment": "positive | neutral | negative | urgent",
  "summary": "ملخص بجملة أو جملتين بالعربية",
  "keywords": ["كلمة1", "كلمة2", "كلمة3"],
  "action_items": ["إجراء1", "إجراء2"],
  "suggested_reply": "مسودة رد مناسبة ومهنية بالعربية (فقرة واحدة)"
}"""

    user = f"""المراسلة:
النوع: {corr_type}
الجهة: {party}
الموضوع: {subject}
المحتوى: {body[:1500]}"""

    text, tokens = _call_claude(system, user, api_key, max_tokens=800)
    
    # Parse JSON
    text = text.strip()
    if text.startswith('```'):
        text = text.split('```')[1]
        if text.startswith('json'):
            text = text[4:]
    result = json.loads(text.strip())

    # Save to database
    existing = conn.execute("SELECT id FROM ai_analysis WHERE correspondence_id=?", (corr_id,)).fetchone()
    if existing:
        conn.execute("""UPDATE ai_analysis SET
            ai_category=?, ai_subcategory=?, ai_priority=?, ai_sentiment=?,
            ai_summary=?, ai_suggested_reply=?, ai_keywords=?, ai_action_items=?,
            ai_confidence=0.9, tokens_used=?, updated_at=?
            WHERE correspondence_id=?""",
            (result.get('category'), result.get('subcategory'), result.get('priority'),
             result.get('sentiment'), result.get('summary'), result.get('suggested_reply'),
             json.dumps(result.get('keywords',[])), json.dumps(result.get('action_items',[])),
             tokens, now(), corr_id))
    else:
        conn.execute("""INSERT INTO ai_analysis
            (id, correspondence_id, ai_category, ai_subcategory, ai_priority, ai_sentiment,
             ai_summary, ai_suggested_reply, ai_keywords, ai_action_items,
             ai_confidence, tokens_used, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,0.9,?,?)""",
            (new_id(), corr_id, result.get('category'), result.get('subcategory'),
             result.get('priority'), result.get('sentiment'), result.get('summary'),
             result.get('suggested_reply'), json.dumps(result.get('keywords',[])),
             json.dumps(result.get('action_items',[])), tokens, now()))

    conn.commit()
    conn.close()
    return result

def get_ai_stats(company_id, api_key):
    """إحصاءات ذكية للشركة"""
    conn = get_db()
    # Get recent unanalyzed correspondence
    items = conn.execute("""
        SELECT c.subject, c.body, c.type, c.party, c.date, c.priority,
               p.name as proj_name
        FROM correspondence c
        LEFT JOIN projects p ON c.project_id = p.id
        LEFT JOIN ai_analysis a ON c.id = a.correspondence_id
        WHERE c.company_id = ? AND c.is_deleted = 0
        AND c.date >= date('now', '-30 days')
        ORDER BY c.date DESC LIMIT 50
    """, (company_id,)).fetchall()
    conn.close()

    if not items:
        return {"error": "لا توجد بيانات كافية للتحليل"}

    # Build summary for AI
    summary_text = "\n".join([
        f"- [{r['type']}] {r['subject'][:80]} | الجهة: {r['party'][:40]}"
        for r in items
    ])

    system = """أنت مستشار إداري خبير. حلّل هذه المراسلات وأرجع JSON فقط:
{
  "top_issues": ["مشكلة1", "مشكلة2", "مشكلة3"],
  "workload_assessment": "تقييم عبء العمل بجملة",
  "recommendations": ["توصية1", "توصية2"],
  "risk_areas": ["مجال خطر1"],
  "positive_trends": ["اتجاه إيجابي1"]
}"""

    user = f"راسلات آخر 30 يوماً ({len(items)} معاملة):\n{summary_text}"
    text, _ = _call_claude(system, user, api_key, max_tokens=600)
    
    text = text.strip()
    if text.startswith('```'):
        text = text.split('```')[1]
        if text.startswith('json'):
            text = text[4:]
    return json.loads(text.strip())
