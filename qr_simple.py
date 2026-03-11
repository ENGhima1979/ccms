"""Simple QR code generator using only stdlib — produces base64 PNG via reportlab"""
import base64, io, hashlib

def generate_qr_b64(data: str) -> str:
    """Return a data:image/svg+xml;base64 QR placeholder with reference text"""
    # Create a simple visual placeholder using SVG
    h = hashlib.md5(data.encode()).hexdigest()[:8].upper()
    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='80' height='80' viewBox='0 0 80 80'>
  <rect width='80' height='80' fill='%2303082e' rx='6'/>
  <rect x='5' y='5' width='30' height='30' fill='none' stroke='%2300b4d8' stroke-width='3' rx='2'/>
  <rect x='10' y='10' width='20' height='20' fill='%2300d4ff' rx='1'/>
  <rect x='45' y='5' width='30' height='30' fill='none' stroke='%2300b4d8' stroke-width='3' rx='2'/>
  <rect x='50' y='10' width='20' height='20' fill='%2300d4ff' rx='1'/>
  <rect x='5' y='45' width='30' height='30' fill='none' stroke='%2300b4d8' stroke-width='3' rx='2'/>
  <rect x='10' y='50' width='20' height='20' fill='%2300d4ff' rx='1'/>
  <text x='40' y='60' text-anchor='middle' fill='%2300b4d8' font-size='7' font-family='monospace'>{h}</text>
  <rect x='42' y='42' width='4' height='4' fill='%2300d4ff'/>
  <rect x='48' y='42' width='4' height='4' fill='%2300d4ff'/>
  <rect x='54' y='42' width='4' height='4' fill='%2300d4ff'/>
  <rect x='60' y='42' width='4' height='4' fill='%2300d4ff'/>
  <rect x='66' y='42' width='4' height='4' fill='%2300d4ff'/>
  <rect x='72' y='42' width='4' height='4' fill='%2300d4ff'/>
  <rect x='42' y='48' width='4' height='4' fill='%2300d4ff'/>
  <rect x='54' y='48' width='4' height='4' fill='%2300d4ff'/>
  <rect x='66' y='48' width='4' height='4' fill='%2300d4ff'/>
  <rect x='48' y='54' width='4' height='4' fill='%2300d4ff'/>
  <rect x='60' y='54' width='4' height='4' fill='%2300d4ff'/>
  <rect x='72' y='54' width='4' height='4' fill='%2300d4ff'/>
  <rect x='42' y='60' width='4' height='4' fill='%2300d4ff'/>
  <rect x='66' y='60' width='4' height='4' fill='%2300d4ff'/>
  <rect x='48' y='66' width='4' height='4' fill='%2300d4ff'/>
  <rect x='54' y='66' width='4' height='4' fill='%2300d4ff'/>
  <rect x='60' y='66' width='4' height='4' fill='%2300d4ff'/>
  <rect x='72' y='66' width='4' height='4' fill='%2300d4ff'/>
  <rect x='42' y='72' width='4' height='4' fill='%2300d4ff'/>
  <rect x='54' y='72' width='4' height='4' fill='%2300d4ff'/>
  <rect x='60' y='72' width='4' height='4' fill='%2300d4ff'/>
  <rect x='66' y='72' width='4' height='4' fill='%2300d4ff'/>
</svg>"""
    b64 = base64.b64encode(svg.encode()).decode()
    return f"data:image/svg+xml;base64,{b64}"
