"""
Arabic text reshaper for ReportLab PDF generation.
Handles RTL display and letter joining without external dependencies.
"""

# Arabic letter forms: {unicode: (isolated, final, initial, medial)}
ARABIC_LETTERS = {
    '\u0627': ('\uFE8D', '\uFE8E', '\uFE8D', '\uFE8E'),  # ا
    '\u0628': ('\uFE8F', '\uFE90', '\uFE91', '\uFE92'),  # ب
    '\u062A': ('\uFE95', '\uFE96', '\uFE97', '\uFE98'),  # ت
    '\u062B': ('\uFE99', '\uFE9A', '\uFE9B', '\uFE9C'),  # ث
    '\u062C': ('\uFE9D', '\uFE9E', '\uFE9F', '\uFEA0'),  # ج
    '\u062D': ('\uFEA1', '\uFEA2', '\uFEA3', '\uFEA4'),  # ح
    '\u062E': ('\uFEA5', '\uFEA6', '\uFEA7', '\uFEA8'),  # خ
    '\u062F': ('\uFEA9', '\uFEAA', '\uFEA9', '\uFEAA'),  # د
    '\u0630': ('\uFEAB', '\uFEAC', '\uFEAB', '\uFEAC'),  # ذ
    '\u0631': ('\uFEAD', '\uFEAE', '\uFEAD', '\uFEAE'),  # ر
    '\u0632': ('\uFEAF', '\uFEB0', '\uFEAF', '\uFEB0'),  # ز
    '\u0633': ('\uFEB1', '\uFEB2', '\uFEB3', '\uFEB4'),  # س
    '\u0634': ('\uFEB5', '\uFEB6', '\uFEB7', '\uFEB8'),  # ش
    '\u0635': ('\uFEB9', '\uFEBA', '\uFEBB', '\uFEBC'),  # ص
    '\u0636': ('\uFEBD', '\uFEBE', '\uFEBF', '\uFEC0'),  # ض
    '\u0637': ('\uFEC1', '\uFEC2', '\uFEC3', '\uFEC4'),  # ط
    '\u0638': ('\uFEC5', '\uFEC6', '\uFEC7', '\uFEC8'),  # ظ
    '\u0639': ('\uFEC9', '\uFECA', '\uFECB', '\uFECC'),  # ع
    '\u063A': ('\uFECD', '\uFECE', '\uFECF', '\uFED0'),  # غ
    '\u0641': ('\uFED1', '\uFED2', '\uFED3', '\uFED4'),  # ف
    '\u0642': ('\uFED5', '\uFED6', '\uFED7', '\uFED8'),  # ق
    '\u0643': ('\uFED9', '\uFEDA', '\uFEDB', '\uFEDC'),  # ك
    '\u0644': ('\uFEDD', '\uFEDE', '\uFEDF', '\uFEE0'),  # ل
    '\u0645': ('\uFEE1', '\uFEE2', '\uFEE3', '\uFEE4'),  # م
    '\u0646': ('\uFEE5', '\uFEE6', '\uFEE7', '\uFEE8'),  # ن
    '\u0647': ('\uFEE9', '\uFEEA', '\uFEEB', '\uFEEC'),  # ه
    '\u0648': ('\uFEED', '\uFEEE', '\uFEED', '\uFEEE'),  # و
    '\u064A': ('\uFEF1', '\uFEF2', '\uFEF3', '\uFEF4'),  # ي
    '\u0629': ('\uFE93', '\uFE94', '\uFE93', '\uFE94'),  # ة
    '\u0649': ('\uFEEF', '\uFEF0', '\uFEEF', '\uFEF0'),  # ى
    '\u0626': ('\uFE89', '\uFE8A', '\uFE8B', '\uFE8C'),  # ئ
    '\u0624': ('\uFE85', '\uFE86', '\uFE85', '\uFE86'),  # ؤ
    '\u0623': ('\uFE83', '\uFE84', '\uFE83', '\uFE84'),  # أ
    '\u0625': ('\uFE87', '\uFE88', '\uFE87', '\uFE88'),  # إ
    '\u0622': ('\uFE81', '\uFE82', '\uFE81', '\uFE82'),  # آ
    '\u0671': ('\uFB50', '\uFB51', '\uFB50', '\uFB51'),  # ٱ
    '\u0644\u0627': ('\uFEFB', '\uFEFC', '\uFEFB', '\uFEFC'),  # لا (ligature)
}

# Letters that don't connect on the left
NO_LEFT_JOIN = set('\u0627\u062F\u0630\u0631\u0632\u0648\u0622\u0623\u0625\u0624\u0671')

def reshape(text):
    """Convert Arabic text to presentation forms for proper display in PDF."""
    if not text:
        return text
    
    result = []
    words = text.split(' ')
    reshaped_words = []
    
    for word in words:
        chars = list(word)
        n = len(chars)
        reshaped = []
        
        i = 0
        while i < n:
            c = chars[i]
            
            if c not in ARABIC_LETTERS:
                reshaped.append(c)
                i += 1
                continue
            
            # Check left and right neighbors
            prev_connects = (i > 0 and chars[i-1] in ARABIC_LETTERS 
                           and chars[i-1] not in NO_LEFT_JOIN)
            next_connects = (i < n-1 and chars[i+1] in ARABIC_LETTERS)
            
            forms = ARABIC_LETTERS[c]
            # 0=isolated, 1=final, 2=initial, 3=medial
            if prev_connects and next_connects:
                reshaped.append(forms[3])  # medial
            elif prev_connects:
                reshaped.append(forms[1])  # final
            elif next_connects:
                reshaped.append(forms[2])  # initial
            else:
                reshaped.append(forms[0])  # isolated
            i += 1
        
        reshaped_words.append(''.join(reversed(reshaped)))
    
    return ' '.join(reversed(reshaped_words))


def arabic_text(text):
    """Prepare Arabic text for ReportLab: reshape + reverse for RTL."""
    if not text:
        return text
    lines = text.split('\n')
    result = []
    for line in lines:
        if any('\u0600' <= c <= '\u06FF' for c in line):
            result.append(reshape(line))
        else:
            result.append(line)
    return '\n'.join(result)
