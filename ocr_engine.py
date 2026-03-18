# -*- coding: utf-8 -*-
"""
ocr_engine.py - محرك OCR عربي احترافي
Claude Vision (95%+) + pytesseract fallback + image preprocessing
"""
import os, json, base64, io, logging
from models import get_db, new_id, now

log = logging.getLogger(__name__)
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"
MAX_SIZE = 4 * 1024 * 1024

# ─── معالجة الصور ───────────────────────────────────────────
def _preprocess(image_bytes):
    try:
        import cv2, numpy as np
        from PIL import Image
        pil = Image.open(io.BytesIO(image_bytes))
        if pil.mode not in ('RGB','L'): pil = pil.convert('RGB')
        w,h = pil.size
        if w<800 or h<600:
            sc = max(800/w,600/h)
            pil = pil.resize((int(w*sc),int(h*sc)), Image.LANCZOS)
        np_img = np.array(pil)
        gray = cv2.cvtColor(np_img, cv2.COLOR_RGB2GRAY) if len(np_img.shape)==3 else np_img
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        denoised = cv2.fastNlMeansDenoising(enhanced, h=10)
        blur = cv2.GaussianBlur(denoised,(0,0),3)
        sharp = cv2.addWeighted(denoised,1.5,blur,-0.5,0)
        sharp = _deskew(sharp)
        _,binary = cv2.threshold(sharp,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
        buf = io.BytesIO()
        Image.fromarray(binary).save(buf,'PNG',optimize=True)
        out = buf.getvalue()
        if len(out) > MAX_SIZE:
            buf = io.BytesIO()
            Image.fromarray(binary).convert('RGB').save(buf,'JPEG',quality=85)
            out = buf.getvalue()
        return out
    except Exception as e:
        log.debug(f"preprocess skip: {e}")
        return image_bytes

def _deskew(gray):
    try:
        import cv2, numpy as np
        coords = np.column_stack(np.where(gray<200))
        if len(coords)<100: return gray
        angle = cv2.minAreaRect(coords)[-1]
        if angle<-45: angle=90+angle
        if abs(angle)<0.5: return gray
        h,w = gray.shape
        M = cv2.getRotationMatrix2D((w//2,h//2),angle,1.0)
        return cv2.warpAffine(gray,M,(w,h),flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE)
    except: return gray

# ─── Claude Vision ───────────────────────────────────────────
def _claude_ocr(img_bytes, api_key, mime="image/png", hint=""):
    import urllib.request
    if len(img_bytes)>MAX_SIZE:
        try:
            from PIL import Image
            buf=io.BytesIO(); img=Image.open(io.BytesIO(img_bytes))
            if img.mode!='RGB': img=img.convert('RGB')
            img.save(buf,'JPEG',quality=80); img_bytes=buf.getvalue(); mime="image/jpeg"
        except: pass
    b64 = base64.standard_b64encode(img_bytes).decode()
    ctx = f"السياق: {hint}\n" if hint else ""
    prompt = f"""{ctx}استخرج كل النص من هذه الصورة بدقة تامة.
التعليمات:
- احتفظ بالتنسيق الأصلي والفقرات والجداول
- النص العربي من اليمين لليسار
- الأرقام والتواريخ كما هي بالضبط
- لا تضف أي تعليقات، فقط النص المستخرج"""
    payload = json.dumps({
        "model": MODEL, "max_tokens": 3000,
        "messages":[{"role":"user","content":[
            {"type":"image","source":{"type":"base64","media_type":mime,"data":b64}},
            {"type":"text","text":prompt}
        ]}]
    }, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(CLAUDE_API_URL, data=payload,
        headers={"Content-Type":"application/json","x-api-key":api_key,"anthropic-version":"2023-06-01"},
        method="POST")
    try:
        with urllib.request.urlopen(req,timeout=45) as r:
            resp=json.loads(r.read())
        text = resp.get("content",[{}])[0].get("text","").strip()
        conf = min(0.97, 0.85+(len(text)/5000)*0.12) if text else 0.0
        return text, conf
    except Exception as e:
        log.warning(f"Claude OCR: {e}"); return "",0.0

# ─── Tesseract ───────────────────────────────────────────────
def _tesseract_ocr(img_bytes):
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes))
        if img.mode not in('RGB','L'): img=img.convert('RGB')
        avail = pytesseract.get_languages()
        lang = 'ara+eng' if 'ara' in avail else 'eng'
        config = '--psm 6 --oem 3 -c preserve_interword_spaces=1'
        text = pytesseract.image_to_string(img, lang=lang, config=config).strip()
        if not text: return "",0.0
        try:
            data = pytesseract.image_to_data(img,lang=lang,output_type=pytesseract.Output.DICT)
            confs = [c for c in data['conf'] if isinstance(c,(int,float)) and c>0]
            conf = round(sum(confs)/len(confs)/100,2) if confs else 0.5
        except: conf=0.5
        return text,conf
    except ImportError: return "",0.0
    except Exception as e: log.warning(f"Tesseract: {e}"); return "",0.0

# ─── PDF ────────────────────────────────────────────────────
def _pdf_extract(pdf_bytes):
    res={"text_pages":[],"image_pages":[],"method":"none"}
    # نص مباشر
    try:
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO(pdf_bytes))
        pages=[]
        for i,p in enumerate(reader.pages[:15]):
            t=(p.extract_text() or "").strip()
            if t: pages.append({"page":i+1,"text":t})
        if pages and sum(len(p["text"].split()) for p in pages)>20:
            res["text_pages"]=pages; res["method"]="pypdf_text"; return res
    except: pass
    # pdf2image
    try:
        from pdf2image import convert_from_bytes
        imgs=convert_from_bytes(pdf_bytes,dpi=200,first_page=1,last_page=10,thread_count=2)
        for i,p in enumerate(imgs):
            buf=io.BytesIO(); p.save(buf,'PNG')
            res["image_pages"].append({"page":i+1,"bytes":buf.getvalue(),"mime":"image/png"})
        if res["image_pages"]: res["method"]="pdf2image"; return res
    except: pass
    # صور مضمّنة
    try:
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO(pdf_bytes))
        for i,p in enumerate(reader.pages[:10]):
            for img in p.images:
                try: res["image_pages"].append({"page":i+1,"bytes":img.data,"mime":"image/jpeg"})
                except: pass
        if res["image_pages"]: res["method"]="pypdf_images"
    except: pass
    return res

# ─── تنظيف النص ─────────────────────────────────────────────
def _clean(text):
    import re
    if not text: return ""
    text=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]','',text)
    text=re.sub(r' {3,}','  ',text)
    text=re.sub(r'\n{4,}','\n\n\n',text)
    return text.strip()

# ─── الدالة الرئيسية ─────────────────────────────────────────
def extract_text_from_file(file_path, api_key="", context_hint=""):
    ext = os.path.splitext(file_path)[1].lower().lstrip('.')
    try:
        with open(file_path,'rb') as f: data=f.read()
    except Exception as e:
        return {"text":"","confidence":0,"engine":"none","error":str(e),"pages":0,"word_count":0}

    results,confs,engine=[],[],""

    if ext=='pdf':
        pdf=_pdf_extract(data)
        if pdf["text_pages"]:
            txt="\n\n".join(f"[صفحة {p['page']}]\n{p['text']}" for p in pdf["text_pages"])
            txt=_clean(txt)
            return {"text":txt,"confidence":0.95,"engine":"pypdf_direct",
                    "pages":len(pdf["text_pages"]),"word_count":len(txt.split()),
                    "page_details":pdf["text_pages"]}
        images=pdf.get("image_pages",[])
    else:
        mime_map={'png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg',
                  'bmp':'image/bmp','tiff':'image/tiff','tif':'image/tiff','webp':'image/webp'}
        images=[{"page":1,"bytes":data,"mime":mime_map.get(ext,'image/jpeg')}]

    if not images:
        return {"text":"","confidence":0,"engine":"none","pages":0,"word_count":0,
                "error":"تعذّر استخراج المحتوى"}

    page_details=[]
    for img in images[:10]:
        raw,mime,pg=img["bytes"],img.get("mime","image/jpeg"),img.get("page",1)
        processed=_preprocess(raw)
        text,conf,eng="",0.0,"none"
        if api_key:
            text,conf=_claude_ocr(processed,api_key,"image/png",context_hint)
            if text: eng="claude_vision"; engine="claude_vision"
        if not text or conf<0.3:
            t2,c2=_tesseract_ocr(processed)
            if t2 and(not text or c2>conf):
                text,conf=t2,c2; eng="tesseract"
                if not engine: engine="tesseract"
        if text:
            cleaned=_clean(text); results.append(cleaned); confs.append(conf)
            page_details.append({"page":pg,"text":cleaned,"confidence":round(conf,2),
                                  "engine":eng,"word_count":len(cleaned.split())})

    if not results:
        return {"text":"","confidence":0,"engine":engine,"pages":len(images),"word_count":0,"page_details":[]}

    full=("\n\n"+"─"*40+"\n\n").join(results)
    return {"text":full,"confidence":round(sum(confs)/len(confs),2),
            "engine":engine,"pages":len(images),"word_count":len(full.split()),
            "page_details":page_details}

# ─── حفظ في DB + FTS ─────────────────────────────────────────
def save_ocr_result(conn, corr_id, attachment_id, company_id, result):
    ocr_id=new_id()
    # إضافة word_count و page_count إذا لم تكن موجودة في الجدول
    try:
        conn.execute("""INSERT OR REPLACE INTO ocr_results
            (id,attachment_id,correspondence_id,company_id,extracted_text,
             confidence,engine,status,word_count,page_count,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (ocr_id,attachment_id,corr_id,company_id,
             result.get("text",""),result.get("confidence",0),result.get("engine","none"),
             "done" if result.get("text") else "failed",
             result.get("word_count",0),result.get("pages",1),now()))
    except Exception:
        # fallback بدون الأعمدة الجديدة
        conn.execute("""INSERT OR REPLACE INTO ocr_results
            (id,attachment_id,correspondence_id,company_id,extracted_text,
             confidence,engine,status,created_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (ocr_id,attachment_id,corr_id,company_id,
             result.get("text",""),result.get("confidence",0),result.get("engine","none"),
             "done" if result.get("text") else "failed",now()))

    # تحديث doc_fts للبحث داخل المستندات
    if result.get("text"):
        try:
            conn.execute("DELETE FROM doc_fts WHERE attachment_id=?", (attachment_id,))
            conn.execute("""INSERT INTO doc_fts(correspondence_id,attachment_id,company_id,content)
                VALUES(?,?,?,?)""", (corr_id,attachment_id,company_id,result["text"]))
        except Exception as e:
            log.debug(f"doc_fts update: {e}")

def get_ocr_result(conn, correspondence_id):
    try:
        return conn.execute("""
            SELECT o.*,a.original_name as filename FROM ocr_results o
            LEFT JOIN attachments a ON o.attachment_id=a.id
            WHERE o.correspondence_id=? ORDER BY o.created_at DESC
        """, (correspondence_id,)).fetchall()
    except Exception:
        return conn.execute(
            "SELECT * FROM ocr_results WHERE correspondence_id=? ORDER BY created_at DESC",
            (correspondence_id,)).fetchall()

def analyze_document_with_ai(text, api_key, task="summary"):
    if not api_key or not text: return {"result":"","task":task}
    import urllib.request
    prompts={"summary":"لخّص هذا المستند بـ 3-5 جمل:",
             "classify":"صنّف هذا المستند (عقد/خطاب/تقرير/فاتورة/مذكرة/أخرى):",
             "extract_dates":"استخرج جميع التواريخ والمواعيد:",
             "extract_entities":"استخرج: أسماء الأشخاص والشركات والأرقام المرجعية:",
             "key_points":"استخرج أهم 5 نقاط:"}
    p=prompts.get(task,prompts["summary"])
    payload=json.dumps({"model":MODEL,"max_tokens":1000,
        "messages":[{"role":"user","content":f"{p}\n\n---\n{text[:3000]}"}]
    },ensure_ascii=False).encode('utf-8')
    req=urllib.request.Request(CLAUDE_API_URL,data=payload,
        headers={"Content-Type":"application/json","x-api-key":api_key,"anthropic-version":"2023-06-01"},
        method="POST")
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            resp=json.loads(r.read())
        return {"result":resp.get("content",[{}])[0].get("text","").strip(),"task":task,"success":True}
    except Exception as e:
        return {"result":"","task":task,"error":str(e)}
