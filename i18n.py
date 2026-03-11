"""
نظام التعريب والترجمة — المرحلة الثالثة
"""
import json, os
from flask import session, request

TRANSLATIONS = {}
SUPPORTED = ['ar', 'en']
DEFAULT = 'ar'

def load_translations():
    base = os.path.join(os.path.dirname(__file__), 'translations')
    for lang in SUPPORTED:
        path = os.path.join(base, f'{lang}.json')
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                TRANSLATIONS[lang] = json.load(f)

def get_lang():
    return session.get('lang', DEFAULT)

def t(key, **kwargs):
    """Translate key to current language"""
    lang = get_lang()
    trans = TRANSLATIONS.get(lang, TRANSLATIONS.get(DEFAULT, {}))
    text = trans.get(key, TRANSLATIONS.get(DEFAULT, {}).get(key, key))
    if kwargs:
        try: text = text.format(**kwargs)
        except: pass
    return text

def is_rtl():
    return get_lang() == 'ar'

def init_i18n(app):
    load_translations()
    
    @app.context_processor
    def inject_i18n():
        lang = get_lang()
        return {
            't': t,
            'lang': lang,
            'is_rtl': lang == 'ar',
            'dir': 'rtl' if lang == 'ar' else 'ltr',
        }
    
    @app.route('/set-lang/<lang>')
    def set_language(lang):
        from flask import redirect, url_for
        if lang in SUPPORTED:
            session['lang'] = lang
        return redirect(request.referrer or url_for('dashboard'))
