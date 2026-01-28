import re
import time
from typing import Dict, List, Tuple, Optional, Any
from flask import Flask, request, jsonify, render_template_string


MAX_TRACE_STEPS = 350
MAX_INPUT_CHARS_PER_SENTENCE = 5000
MAX_SENTENCES = 30

app = Flask(__name__)

def normalize(text: str) -> str:
    text = text.lower().strip()
    text = text.replace("–", " ").replace("—", " ").replace("-", " ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def normalize_with_map(original: str) -> Tuple[str, List[int]]:
    """
    Normalisasi mirip normalize(), tapi juga mengembalikan mapping:
    map_norm[i] = indeks karakter di original yang menghasilkan norm[i]
    """
    s = original.strip()
    out_chars: List[str] = []
    out_map: List[int] = []

    prev_space = False
    for i, ch in enumerate(s):
        c = ch.lower()
        if c in ["–", "—", "-"]:
            c = " "

        if c.isalnum():
            out_chars.append(c)
            out_map.append(i)
            prev_space = False
        else:
            if not prev_space and len(out_chars) > 0:
                out_chars.append(" ")
                out_map.append(i)
                prev_space = True

    while out_chars and out_chars[0] == " ":
        out_chars.pop(0); out_map.pop(0)
    while out_chars and out_chars[-1] == " ":
        out_chars.pop(); out_map.pop()

    return "".join(out_chars), out_map

def escape_html(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&#39;"))

def highlight_span(original: str, start: int, end: int) -> str:
    """
    Return HTML aman: original di-escape, bagian [start:end] diberi <mark class='hl'>.
    """
    start = max(0, min(start, len(original)))
    end = max(0, min(end, len(original)))
    if end <= start:
        return escape_html(original)

    left = escape_html(original[:start])
    mid = escape_html(original[start:end])
    right = escape_html(original[end:])
    return f"{left}<mark class='hl'>{mid}</mark>{right}"

def naive_search(text: str, pattern: str) -> int:
    n, m = len(text), len(pattern)
    if m == 0:
        return 0
    if m > n:
        return -1
    for i in range(n - m + 1):
        if text[i:i+m] == pattern:
            return i
    return -1

def naive_search_count(text: str, pattern: str) -> Tuple[int, int]:
    n, m = len(text), len(pattern)
    if m == 0:
        return 0, 0
    if m > n:
        return -1, 0
    comps = 0
    for i in range(n - m + 1):
        match = True
        for j in range(m):
            comps += 1
            if text[i+j] != pattern[j]:
                match = False
                break
        if match:
            return i, comps
    return -1, comps

def naive_search_trace(text: str, pattern: str) -> Tuple[int, List[str], int]:
    trace: List[str] = []
    n, m = len(text), len(pattern)
    if m == 0:
        trace.append("[Naive] Pattern kosong → ditemukan di indeks 0")
        return 0, trace, 0
    if m > n:
        trace.append("[Naive] Pattern lebih panjang dari text → tidak mungkin ketemu")
        return -1, trace, 0

    steps = 0
    comps = 0
    trace.append("[NAIVE TRACE] Pergeseran satu-per-satu")
    for i in range(n - m + 1):
        trace.append(f"Shift i={i} | bandingkan text[{i}:{i+m}] dengan pattern")
        match = True
        for j in range(m):
            steps += 1
            comps += 1
            trace.append(f"  Compare j={j}: T[{i+j}]='{text[i+j]}' vs P[{j}]='{pattern[j]}'")
            if steps >= MAX_TRACE_STEPS:
                trace.append("...trace dihentikan (batas langkah)")
                return -2, trace, comps
            if text[i+j] != pattern[j]:
                trace.append("  ✗ mismatch → geser 1")
                match = False
                break
        if match:
            trace.append("  ✓ semua karakter cocok → FOUND")
            return i, trace, comps
    trace.append("→ pattern tidak ditemukan")
    return -1, trace, comps

def kmp_build_lps(pattern: str) -> List[int]:
    m = len(pattern)
    lps = [0] * m
    length = 0
    i = 1
    while i < m:
        if pattern[i] == pattern[length]:
            length += 1
            lps[i] = length
            i += 1
        else:
            if length != 0:
                length = lps[length - 1]
            else:
                lps[i] = 0
                i += 1
    return lps

def kmp_search(text: str, pattern: str) -> int:
    n, m = len(text), len(pattern)
    if m == 0:
        return 0
    if m > n:
        return -1

    lps = kmp_build_lps(pattern)
    i = j = 0
    while i < n:
        if text[i] == pattern[j]:
            i += 1
            j += 1
            if j == m:
                return i - j
        else:
            if j != 0:
                j = lps[j - 1]  # wajib LPS[j-1]
            else:
                i += 1
    return -1

def kmp_search_count(text: str, pattern: str) -> Tuple[int, int, List[int]]:
    n, m = len(text), len(pattern)
    if m == 0:
        return 0, 0, []
    if m > n:
        return -1, 0, kmp_build_lps(pattern)

    lps = kmp_build_lps(pattern)
    i = j = 0
    comps = 0
    while i < n:
        comps += 1
        if text[i] == pattern[j]:
            i += 1
            j += 1
            if j == m:
                return i - j, comps, lps
        else:
            if j != 0:
                j = lps[j - 1]
            else:
                i += 1
    return -1, comps, lps

def kmp_search_trace(text: str, pattern: str) -> Tuple[int, List[str], int, List[int]]:
    trace: List[str] = []
    n, m = len(text), len(pattern)
    if m == 0:
        trace.append("[KMP] Pattern kosong → ditemukan di indeks 0")
        return 0, trace, 0, []
    if m > n:
        trace.append("[KMP] Pattern lebih panjang dari text → tidak mungkin ketemu")
        return -1, trace, 0, kmp_build_lps(pattern)

    # Build LPS with trace
    lps = [0] * m
    length = 0
    i = 1
    trace.append("[KMP] Tahap 1: Bangun Tabel LPS")
    trace.append(f"Pattern: '{pattern}'")
    steps = 0
    while i < m:
        trace.append(f" i={i}, length={length} | P[i]='{pattern[i]}' vs P[length]='{pattern[length]}'")
        if pattern[i] == pattern[length]:
            length += 1
            lps[i] = length
            trace.append(f"  ✓ match → LPS[{i}]={length}, i++")
            i += 1
        else:
            if length != 0:
                trace.append(f"  ✗ mismatch → length = LPS[{length-1}] = {lps[length-1]}")
                length = lps[length - 1]
            else:
                lps[i] = 0
                trace.append(f"  ✗ mismatch & length==0 → LPS[{i}]=0, i++")
                i += 1
        steps += 1
        if steps >= MAX_TRACE_STEPS:
            trace.append("...trace dihentikan (batas langkah)")
            return -2, trace, 0, lps

    trace.append(f"LPS Table: {lps}")

    trace.append("[KMP] Tahap 2: Proses Pencarian (i tidak pernah mundur)")
    i = j = 0
    comps = 0
    step2 = 0
    while i < n:
        step2 += 1
        if step2 >= MAX_TRACE_STEPS:
            trace.append("...trace dihentikan (batas langkah)")
            return -2, trace, comps, lps

        comps += 1
        trace.append(f" Step {step2}: i={i}, j={j} | T[i]='{text[i]}' vs P[j]='{pattern[j]}'")
        if text[i] == pattern[j]:
            i += 1
            j += 1
            trace.append(f"  ✓ match → i={i}, j={j}")
            if j == m:
                pos = i - j
                trace.append(f"  ✓ FOUND pada posisi {pos}")
                trace.append(f"  → set j = LPS[{j-1}] = {lps[j-1]}")
                return pos, trace, comps, lps
        else:
            trace.append("  ✗ mismatch")
            if j != 0:
                old_j = j
                j = lps[j - 1]
                trace.append(f"  → geser j: {old_j} → {j} (pakai LPS[{old_j-1}])")
            else:
                i += 1
                trace.append(f"  → j==0, geser i: i → {i}")

    trace.append("→ pattern tidak ditemukan")
    return -1, trace, comps, lps

# ============================================================
# 3) BOYER–MOORE (BAD CHARACTER) (FAST + TRACE + COUNT + LAST)
# ============================================================
def bm_build_last(pattern: str) -> Dict[str, int]:
    last = {}
    for idx, ch in enumerate(pattern):
        last[ch] = idx
    return last

def bm_search(text: str, pattern: str) -> int:
    n, m = len(text), len(pattern)
    if m == 0:
        return 0
    if m > n:
        return -1

    last = bm_build_last(pattern)
    s = 0
    while s <= n - m:
        j = m - 1
        while j >= 0 and pattern[j] == text[s + j]:
            j -= 1
        if j < 0:
            return s
        bad_char = text[s + j]
        lo = last.get(bad_char, -1)
        shift = max(1, j - lo)
        s += shift
    return -1

def bm_search_count(text: str, pattern: str) -> Tuple[int, int, Dict[str, int]]:
    n, m = len(text), len(pattern)
    if m == 0:
        return 0, 0, {}
    if m > n:
        return -1, 0, bm_build_last(pattern)

    last = bm_build_last(pattern)
    s = 0
    comps = 0
    while s <= n - m:
        j = m - 1
        while j >= 0:
            comps += 1
            if pattern[j] == text[s + j]:
                j -= 1
            else:
                break
        if j < 0:
            return s, comps, last
        bad_char = text[s + j]
        lo = last.get(bad_char, -1)
        shift = max(1, j - lo)
        s += shift
    return -1, comps, last

def bm_search_trace(text: str, pattern: str) -> Tuple[int, List[str], int, Dict[str, int]]:
    trace: List[str] = []
    n, m = len(text), len(pattern)
    if m == 0:
        trace.append("[BM] Pattern kosong → ditemukan di indeks 0")
        return 0, trace, 0, {}
    if m > n:
        trace.append("[BM] Pattern lebih panjang dari text → tidak mungkin ketemu")
        return -1, trace, 0, bm_build_last(pattern)

    last = bm_build_last(pattern)
    trace.append("[BOYER–MOORE TRACE] Bad Character Rule (bandingkan dari kanan)")
    trace.append(f"Last Table: {last}")

    s = 0
    steps = 0
    comps = 0
    while s <= n - m:
        j = m - 1
        trace.append(f"Alignment shift s={s} | mulai dari kanan (j={j})")

        while j >= 0 and pattern[j] == text[s + j]:
            comps += 1
            trace.append(f"  ✓ match j={j}: P='{pattern[j]}' == T='{text[s+j]}'")
            j -= 1
            steps += 1
            if steps >= MAX_TRACE_STEPS:
                trace.append("...trace dihentikan (batas langkah)")
                return -2, trace, comps, last

        if j < 0:
            trace.append("  ✓ semua cocok → FOUND")
            return s, trace, comps, last

        comps += 1
        bad_char = text[s + j]
        lo = last.get(bad_char, -1)
        shift = max(1, j - lo)
        trace.append(f"  ✗ mismatch j={j}: P='{pattern[j]}' != T='{bad_char}'")
        trace.append(f"  bad_char='{bad_char}', last_occurrence={lo} → shift={shift}")
        s += shift

        steps += 1
        if steps >= MAX_TRACE_STEPS:
            trace.append("...trace dihentikan (batas langkah)")
            return -2, trace, comps, last

    trace.append("→ pattern tidak ditemukan")
    return -1, trace, comps, last

# ============================================================
# RUNNER + HIGHLIGHT + EXPLAIN (UNTUK MENU PROSES)
# ============================================================
def method_label(method: str) -> str:
    return {"naive": "Naive String Matching", "kmp": "Knuth–Morris–Pratt (KMP)", "bm": "Boyer–Moore (Bad Character)"}\
        .get(method, "Unknown")

def method_explain(method: str) -> str:
    if method == "naive":
        return "Naive menggeser pattern satu-per-satu dan membandingkan karakter dari kiri. Sederhana tetapi bisa lebih lambat pada teks panjang."
    if method == "kmp":
        return "KMP membangun tabel LPS untuk menghindari perbandingan ulang saat mismatch. i tidak mundur; pencarian lebih efisien."
    if method == "bm":
        return "Boyer–Moore membandingkan dari kanan ke kiri dan dapat melompat jauh dengan aturan bad character. Umumnya cepat pada teks natural."
    return "Metode tidak dikenal."

def run_one_pair(method: str, sA: str, sB: str, analysis_mode: bool) -> Dict[str, Any]:
    origA, origB = sA, sB

    normA, mapA = normalize_with_map(origA)
    normB, mapB = normalize_with_map(origB)

    # Tentukan TEXT (lebih panjang) dan PATTERN (lebih pendek)
    if len(normA) >= len(normB):
        text_norm, pattern_norm = normA, normB
        text_orig, pattern_orig = origA, origB
        text_map = mapA
        text_source = "A"
        pattern_source = "B"
    else:
        text_norm, pattern_norm = normB, normA
        text_orig, pattern_orig = origB, origA
        text_map = mapB
        text_source = "B"
        pattern_source = "A"

    t0 = time.perf_counter()
    trace: Optional[List[str]] = None
    comps = 0
    lps: Optional[List[int]] = None
    last_table: Optional[Dict[str, int]] = None

    if analysis_mode:
        if method == "naive":
            idx, trace, comps = naive_search_trace(text_norm, pattern_norm)
        elif method == "kmp":
            idx, trace, comps, lps = kmp_search_trace(text_norm, pattern_norm)
        elif method == "bm":
            idx, trace, comps, last_table = bm_search_trace(text_norm, pattern_norm)
        else:
            idx, trace = -1, ["Metode tidak dikenal"]
    else:
        if method == "naive":
            idx, comps = naive_search_count(text_norm, pattern_norm)
        elif method == "kmp":
            idx, comps, lps = kmp_search_count(text_norm, pattern_norm)
        elif method == "bm":
            idx, comps, last_table = bm_search_count(text_norm, pattern_norm)
        else:
            idx = -1

    t_ms = (time.perf_counter() - t0) * 1000
    status = "DUPLIKAT" if idx >= 0 else "TIDAK DUPLIKAT"

    # Highlight HTML
    a_hl = escape_html(origA)
    b_hl = escape_html(origB)
    match_info = None
    match_snippet_norm = ""

    if idx >= 0 and len(pattern_norm) > 0:
        m = len(pattern_norm)
        start_orig = text_map[idx]
        end_orig = text_map[idx + m - 1] + 1
        match_snippet_norm = text_norm[idx:idx+m]

        text_hl = highlight_span(text_orig, start_orig, end_orig)
        pattern_hl = f"<mark class='hl'>{escape_html(pattern_orig)}</mark>"

        if text_source == "A":
            a_hl = text_hl
            b_hl = pattern_hl
            match_info = {"container": "A", "start": start_orig, "end": end_orig}
        else:
            b_hl = text_hl
            a_hl = pattern_hl
            match_info = {"container": "B", "start": start_orig, "end": end_orig}

    explain = {
        "metode": method_label(method),
        "metode_ringkas": method_explain(method),
        "aturan_duplikasi": "Duplikat jika PATTERN ditemukan sebagai substring di dalam TEXT setelah normalisasi.",
        "normA": normA,
        "normB": normB,
        "text_source": text_source,
        "pattern_source": pattern_source,
        "text_norm": text_norm,
        "pattern_norm": pattern_norm,
        "found_idx": idx,
        "match_norm": match_snippet_norm,
        "comparisons": comps,
        "lps": lps,
        "last_table": last_table
    }

    return {
        "idx": idx,
        "time_ms": round(t_ms, 3),
        "status": status,
        "trace": trace,
        "a_hl": a_hl,
        "b_hl": b_hl,
        "match_info": match_info,
        "explain": explain
    }

# ============================================================
# WEB UI (SIDEBAR AKTIF + MENU PROSES DETAIL)
# ============================================================
HTML = r"""
<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Pendeteksi Duplikasi Kalimat Akademik</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap" rel="stylesheet">
  <style>
    :root{
      --bg:#f6f7ff;
      --ink:#111827;
      --muted:#6b7280;
      --stroke:#e6e8f3;
      --primary:#6c5ce7;
      --primary2:#7c3aed;
      --shadow: 0 18px 50px rgba(17,24,39,.10);
      --shadow2: 0 10px 26px rgba(17,24,39,.08);
    }
    *{box-sizing:border-box}
    html{scroll-behavior:smooth}
    body{
      margin:0;
      font-family:Inter,system-ui,Segoe UI,Roboto,Arial;
      color:var(--ink);
      background:
        radial-gradient(900px 550px at 18% 0%, rgba(108,92,231,.22), transparent 60%),
        radial-gradient(700px 420px at 88% 8%, rgba(124,58,237,.14), transparent 60%),
        radial-gradient(800px 520px at 50% 110%, rgba(99,102,241,.14), transparent 60%),
        var(--bg);
    }

    .app{
      display:grid;
      grid-template-columns: 260px 1fr;
      gap:18px;
      padding:18px;
      min-height:100vh;
    }
    @media(max-width:860px){
      .app{grid-template-columns: 1fr;}
      .side{display:none;}
    }

    /* Sidebar */
    .side{
      background: linear-gradient(180deg, rgba(108,92,231,.14), rgba(255,255,255,.55));
      border:1px solid rgba(255,255,255,.55);
      border-radius: 22px;
      box-shadow: var(--shadow);
      padding:16px 14px;
      position:sticky;
      top:18px;
      height: calc(100vh - 36px);
      overflow:auto;
      backdrop-filter: blur(10px);
    }
    .brand{
      display:flex;align-items:center;gap:10px;
      padding:10px 10px 14px;
      border-bottom:1px solid rgba(108,92,231,.10);
      margin-bottom:12px;
    }
    .logo{
      width:40px;height:40px;border-radius:14px;
      background: linear-gradient(135deg, var(--primary), var(--primary2));
      box-shadow: 0 12px 30px rgba(108,92,231,.28);
      display:grid;place-items:center;color:white;font-weight:900;
    }
    .brand .t1{font-weight:900}
    .brand .t2{font-size:12px;color:var(--muted);margin-top:2px}

    .nav{display:flex;flex-direction:column;gap:10px;margin-top:10px}
    .navBtn{
      display:flex;align-items:center;gap:10px;
      padding:12px 12px;border-radius:16px;
      background:rgba(255,255,255,.70);
      border:1px solid rgba(108,92,231,.10);
      box-shadow: 0 10px 22px rgba(17,24,39,.05);
      font-weight:900;font-size:13px;
      cursor:pointer;
      user-select:none;
      transition:.15s ease;
    }
    .navBtn:hover{transform:translateY(-1px)}
    .navBtn.active{
      border-color: rgba(108,92,231,.24);
      background: linear-gradient(135deg, rgba(108,92,231,.16), rgba(255,255,255,.72));
    }
    .ico{
      width:34px;height:34px;border-radius:12px;
      background: rgba(108,92,231,.10);
      display:grid;place-items:center;
      color: var(--primary);
      font-weight:900;
      flex:0 0 auto;
    }

    .note{
      margin-top:14px;
      background: rgba(255,255,255,.75);
      border:1px solid var(--stroke);
      border-radius: 18px;
      padding:12px;
      box-shadow: var(--shadow2);
    }
    .note .h{font-weight:950;font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.25px}
    .note .b{margin-top:8px;font-weight:950}
    .note .p{margin-top:8px;color:var(--muted);font-weight:650;font-size:12px;line-height:1.45}

    /* Main */
    .main{display:flex;flex-direction:column;gap:16px}
    .topbar{
      display:flex;align-items:flex-start;justify-content:space-between;gap:12px;
      padding:16px 16px;
      background: rgba(255,255,255,.78);
      border:1px solid rgba(255,255,255,.78);
      border-radius:22px;
      box-shadow: var(--shadow2);
      backdrop-filter: blur(10px);
    }
    .title{font-size:16px;font-weight:950;margin:0}
    .subtitle{margin-top:4px;font-size:12px;color:var(--muted);font-weight:650;line-height:1.4}

    .chips{display:flex;gap:10px;flex-wrap:wrap;justify-content:flex-end}
    .chip{
      padding:9px 12px;border-radius:999px;
      background: rgba(255,255,255,.85);
      border:1px solid var(--stroke);
      font-weight:900;font-size:12px;
      box-shadow: 0 10px 22px rgba(17,24,39,.05);
      display:flex;align-items:center;gap:8px;
      white-space:nowrap;
    }
    .chip select{
      border:none;outline:none;background:transparent;
      font-weight:950;color:var(--primary);
      cursor:pointer;
    }

    .grid{
      display:grid;
      grid-template-columns: 1.2fr .8fr;
      gap:16px;
    }
    @media(max-width:1100px){ .grid{grid-template-columns:1fr;} }

    .card{
      background: rgba(255,255,255,.80);
      border:1px solid rgba(255,255,255,.80);
      border-radius: 22px;
      box-shadow: var(--shadow2);
      padding:16px;
      backdrop-filter: blur(10px);
    }
    .card h2{
      margin:0 0 10px;
      font-size:13px;
      font-weight:950;
      color:#2b2f3a;
      letter-spacing:.25px;
      text-transform:uppercase;
    }
    textarea{
      width:100%;
      min-height:280px;
      resize:vertical;
      background: linear-gradient(180deg, rgba(108,92,231,.05), rgba(255,255,255,.55));
      border:1px solid rgba(108,92,231,.12);
      border-radius: 18px;
      padding:14px;
      outline:none;
      font-weight:650;
      color:#1f2937;
      line-height:1.55;
    }
    textarea:focus{
      border-color: rgba(108,92,231,.35);
      box-shadow: 0 0 0 5px rgba(108,92,231,.10);
    }
    .actions{
      display:flex;gap:10px;flex-wrap:wrap;
      margin-top:12px;
      align-items:center;
      justify-content:space-between;
    }
    .btn{
      border:none;cursor:pointer;
      border-radius:16px;
      padding:11px 14px;
      font-weight:950;
      color:white;
      background: linear-gradient(135deg, var(--primary), var(--primary2));
      box-shadow: 0 18px 42px rgba(108,92,231,.30);
      display:inline-flex;align-items:center;gap:10px;
    }
    .btn2{
      border:1px solid var(--stroke);
      background: rgba(255,255,255,.92);
      border-radius:16px;
      padding:11px 14px;
      font-weight:950;
      cursor:pointer;
      display:inline-flex;align-items:center;gap:10px;
      box-shadow: 0 10px 22px rgba(17,24,39,.05);
    }
    .btn:active,.btn2:active{transform:translateY(1px)}
    .btn[disabled]{opacity:.65;cursor:not-allowed;transform:none}

    /* KPI */
    .kpi{
      display:grid;grid-template-columns:repeat(4,1fr);
      gap:10px;margin-top:12px;
    }
    @media(max-width:700px){ .kpi{grid-template-columns:repeat(2,1fr)} }
    .kbox{
      border-radius:18px;
      border:1px solid rgba(108,92,231,.12);
      background: linear-gradient(180deg, rgba(108,92,231,.08), rgba(255,255,255,.75));
      padding:12px;
    }
    .kbox .v{font-weight:950;font-size:18px}
    .kbox .l{margin-top:2px;font-size:12px;color:var(--muted);font-weight:700}

    /* Proses bar (global) */
    .process{
      margin-top:12px;
      padding:12px;
      border-radius:18px;
      border:1px solid rgba(108,92,231,.12);
      background: rgba(255,255,255,.78);
      box-shadow: var(--shadow2);
    }
    .ptitle{font-weight:950;font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.25px}
    .psteps{margin-top:10px;display:flex;gap:8px;flex-wrap:wrap}
    .pstep{
      padding:8px 10px;border-radius:999px;
      border:1px solid var(--stroke);
      background: rgba(108,92,231,.05);
      font-weight:900;font-size:12px;color:#2b2f3a;
    }
    .pstep.on{
      border-color: rgba(108,92,231,.25);
      background: rgba(108,92,231,.14);
      color: var(--primary);
    }
    .pstep.done{
      border-color: rgba(16,185,129,.22);
      background: rgba(16,185,129,.10);
      color:#059669;
    }

    /* Results */
    .hint{font-size:12px;color:var(--muted);font-weight:650;line-height:1.45}
    table{
      width:100%;
      border-collapse:separate;border-spacing:0;
      overflow:hidden;border-radius:18px;
      border:1px solid var(--stroke);
      background: rgba(255,255,255,.92);
      box-shadow: 0 12px 30px rgba(17,24,39,.06);
    }
    th,td{
      padding:11px 10px;border-bottom:1px solid var(--stroke);
      vertical-align:top;
      font-size:13px;
    }
    th{
      font-size:12px;color:var(--muted);
      font-weight:950;text-transform:uppercase;letter-spacing:.25px;
      background: rgba(108,92,231,.06);
    }
    tr:last-child td{border-bottom:none}

    .tag{
      display:inline-flex;align-items:center;gap:8px;
      padding:7px 10px;border-radius:999px;
      font-weight:950;font-size:12px;
      border:1px solid transparent;
      white-space:nowrap;
    }
    .tagDup{background:rgba(16,185,129,.10);color:#059669;border-color:rgba(16,185,129,.22)}
    .tagNo{background:rgba(225,29,72,.08);color:#e11d48;border-color:rgba(225,29,72,.18)}

    /* Highlight */
    .hl{
      background: linear-gradient(135deg, rgba(108,92,231,.22), rgba(124,58,237,.14));
      border: 1px solid rgba(108,92,231,.25);
      color: #1f2937;
      padding: 0 3px;
      border-radius: 6px;
      font-weight: 950;
    }

    /* Trace */
    .trace{
      background: rgba(17,24,39,.05);
      border:1px solid rgba(17,24,39,.08);
      border-radius:18px;
      padding:12px;
      white-space:pre-wrap;
      line-height:1.5;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      font-size:12px;
      max-height:260px;
      overflow:auto;
    }

    .mini{
      padding:12px 12px;
      border-radius:18px;
      border:1px solid rgba(108,92,231,.10);
      background: linear-gradient(135deg, rgba(108,92,231,.10), rgba(255,255,255,.80));
      box-shadow: 0 12px 30px rgba(17,24,39,.06);
    }
    .mini .t{font-weight:950}
    .mini .p{margin-top:6px;color:var(--muted);font-weight:650;font-size:12px;line-height:1.45}

    /* PROSES DETAIL (Accordion) */
    .acc{display:flex;flex-direction:column;gap:10px}
    .accItem{
      border:1px solid rgba(108,92,231,.10);
      background: rgba(255,255,255,.86);
      border-radius:18px;
      box-shadow: 0 12px 26px rgba(17,24,39,.05);
      overflow:hidden;
    }
    .accHead{
      display:flex;align-items:center;justify-content:space-between;gap:10px;
      padding:12px 14px;
      cursor:pointer;
      user-select:none;
      font-weight:950;
    }
    .accHead .left{display:flex;align-items:center;gap:10px}
    .pill{
      padding:6px 10px;border-radius:999px;font-size:12px;font-weight:950;
      border:1px solid rgba(108,92,231,.14);
      background: rgba(108,92,231,.06);
      color: var(--primary);
      white-space:nowrap;
    }
    .accBody{
      display:none;
      padding:12px 14px 14px;
      border-top:1px solid rgba(108,92,231,.10);
    }
    .kv{
      display:grid;
      grid-template-columns: 150px 1fr;
      gap:8px 12px;
      margin:10px 0;
      font-size:13px;
    }
    .kv .k{color:var(--muted);font-weight:900}
    .kv .v{font-weight:650}
    .codebox{
      margin-top:10px;
      background: rgba(17,24,39,.05);
      border:1px solid rgba(17,24,39,.08);
      border-radius:16px;
      padding:10px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      font-size:12px;
      white-space:pre-wrap;
    }
    .grid2{
      display:grid;
      grid-template-columns: 1fr 1fr;
      gap:12px;
    }
    @media(max-width:900px){ .grid2{grid-template-columns:1fr;} }
  </style>
</head>
<body>
  <div class="app">
    <!-- Sidebar -->
    <aside class="side">
      <div class="brand">
        <div class="logo">SM</div>
        <div>
          <div class="t1">String Matching</div>
          <div class="t2">Aplikasi Akademik</div>
        </div>
      </div>

      <div class="nav">
        <div class="navBtn active" id="nav_dashboard" onclick="goTo('dashboard','nav_dashboard')">
          <div class="ico">⌂</div> Dashboard
        </div>
        <div class="navBtn" id="nav_check" onclick="goTo('check','nav_check')">
          <div class="ico">≡</div> Pemeriksaan Kalimat
        </div>
        <div class="navBtn" id="nav_results" onclick="goTo('results','nav_results')">
          <div class="ico">✓</div> Hasil & Highlight
        </div>
        <div class="navBtn" id="nav_process" onclick="goTo('process','nav_process')">
          <div class="ico">🧠</div> Proses (Detail)
        </div>
      </div>

      <div class="note">
        <div class="h">Aturan Duplikasi</div>
        <div class="b">Substring (Setelah Normalisasi)</div>
        <div class="p">
          Duplikat jika kalimat yang lebih pendek (PATTERN) ditemukan sebagai <b>substring</b> di kalimat lebih panjang (TEXT).
          Metode hanya memengaruhi cara pencarian & efisiensi, bukan hasil akhir.
        </div>
      </div>
    </aside>

    <!-- Main -->
    <main class="main">
      <!-- Dashboard -->
      <div class="topbar" id="dashboard">
        <div>
          <div class="title">Pendeteksi Duplikasi Kalimat pada Tugas Akademik menggunakan String Matching</div>
          <div class="subtitle">
            1 baris = 1 kalimat → pilih metode → sistem membandingkan semua pasangan dan menampilkan bukti substring yang sama (highlight) + penjelasan proses detail.
          </div>
        </div>
        <div class="chips">
          <div class="chip">Metode:
            <select id="method">
              <option value="naive">Naive</option>
              <option value="kmp">KMP</option>
              <option value="bm">Boyer–Moore</option>
            </select>
          </div>
          <div class="chip">Mode:
            <select id="mode">
              <option value="fast">Cepat</option>
              <option value="trace">Analisis (Trace)</option>
            </select>
          </div>
        </div>
      </div>

      <div class="grid">
        <!-- Pemeriksaan -->
        <section class="card" id="check">
          <h2>Input Kalimat</h2>
          <textarea id="sentences" placeholder="Contoh:
Penelitian ini menggunakan metode KMP untuk pencocokan string.
Metode KMP untuk pencocokan string.
Hasil menunjukkan peningkatan akurasi secara signifikan."></textarea>

          <div class="actions">
            <div style="display:flex;gap:10px;flex-wrap:wrap">
              <button class="btn2" onclick="fillDemo()">Isi Contoh</button>
              <button class="btn2" onclick="clearAll()">Bersihkan</button>
            </div>
            <button class="btn" id="runBtn" onclick="run()">▶ Jalankan Pemeriksaan</button>
          </div>

          <!-- Proses Global -->
          <div id="processBox" class="process" style="display:none">
            <div class="ptitle">Proses Global</div>
            <div class="psteps">
              <div class="pstep" id="p1">1) Validasi</div>
              <div class="pstep" id="p2">2) Normalisasi</div>
              <div class="pstep" id="p3">3) Pairwise</div>
              <div class="pstep" id="p4">4) Matching</div>
              <div class="pstep" id="p5">5) Output</div>
            </div>
          </div>

          <div class="kpi">
            <div class="kbox"><div class="v" id="k_n">0</div><div class="l">Jumlah Kalimat</div></div>
            <div class="kbox"><div class="v" id="k_pairs">0</div><div class="l">Total Pasangan</div></div>
            <div class="kbox"><div class="v" id="k_dup">0</div><div class="l">Duplikat</div></div>
            <div class="kbox"><div class="v" id="k_time">0.000</div><div class="l">Total Waktu (ms)</div></div>
          </div>
        </section>

        <!-- Petunjuk -->
        <section class="card">
          <h2>Petunjuk & Interpretasi</h2>
          <div class="mini">
            <div class="t">Normalisasi</div>
            <div class="p">Lowercase, tanda baca diabaikan, spasi dirapikan. Deteksi berbasis substring pada teks hasil normalisasi.</div>
          </div>
          <div style="height:10px"></div>
          <div class="mini">
            <div class="t">Mengapa Duplikat?</div>
            <div class="p">Jika PATTERN ditemukan di TEXT, sistem mengembalikan indeks posisi + highlight bukti substring.</div>
          </div>
          <div style="height:10px"></div>
          <div class="mini">
            <div class="t">Menu Proses (Detail)</div>
            <div class="p">Menampilkan langkah per pasangan: normalisasi A/B, pemilihan TEXT/PATTERN, hasil matching, alasan duplikat/tidak, plus info khas metode (LPS/Last table).</div>
          </div>
        </section>
      </div>

      <!-- Results -->
      <section class="card" id="results">
        <h2>Hasil Pairwise + Highlight</h2>
        <div id="resultArea" class="hint">Belum ada hasil.</div>
      </section>

      <!-- PROSES DETAIL -->
      <section class="card" id="process">
        <h2>Proses (Detail) — Mengapa Duplikat / Tidak Duplikat?</h2>
        <div id="processArea" class="hint">
          Jalankan pemeriksaan terlebih dahulu. Setelah itu, bagian ini akan menampilkan proses detail per pasangan sesuai metode yang dipilih.
        </div>
      </section>

    </main>
  </div>

<script>
function setActiveNav(navId){
  ["nav_dashboard","nav_check","nav_results","nav_process"].forEach(id=>{
    const el = document.getElementById(id);
    if(el) el.classList.remove("active");
  });
  const target = document.getElementById(navId);
  if(target) target.classList.add("active");
}
function goTo(sectionId, navId){
  if(navId) setActiveNav(navId);
  const el = document.getElementById(sectionId);
  if(el) el.scrollIntoView({behavior:"smooth", block:"start"});
}

function splitSentences(raw){
  // FIX penting: newline harus "\n" (bukan "\\n")
  return raw.split("\n").map(s => s.trim()).filter(s => s.length > 0);
}

function fillDemo(){
  document.getElementById("sentences").value =
`Penelitian ini menggunakan metode KMP untuk pencocokan string.
Metode KMP untuk pencocokan string.
Hasil menunjukkan peningkatan akurasi secara signifikan.
Pada penelitian ini, akurasi meningkat secara signifikan.`;
}
function clearAll(){
  document.getElementById("sentences").value = "";
  document.getElementById("resultArea").innerHTML = "Belum ada hasil.";
  document.getElementById("processArea").innerHTML = "Jalankan pemeriksaan terlebih dahulu. Setelah itu, bagian ini akan menampilkan proses detail per pasangan sesuai metode yang dipilih.";
  document.getElementById("k_n").textContent = 0;
  document.getElementById("k_pairs").textContent = 0;
  document.getElementById("k_dup").textContent = 0;
  document.getElementById("k_time").textContent = "0.000";
  showProcess(false);
  for(let i=1;i<=5;i++) setStep(i,"");
  goTo("dashboard","nav_dashboard");
}

function esc(s){
  return (s ?? "").toString()
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;");
}

function setStep(n, state){
  const el = document.getElementById("p"+n);
  if(!el) return;
  el.classList.remove("on","done");
  if(state) el.classList.add(state);
}
function showProcess(show=true){
  const box = document.getElementById("processBox");
  if(box) box.style.display = show ? "block" : "none";
}

function toggleAcc(id){
  const body = document.getElementById(id);
  if(!body) return;
  body.style.display = (body.style.display === "none" || body.style.display === "") ? "block" : "none";
}

function formatJSON(obj){
  try{
    return JSON.stringify(obj, null, 2);
  }catch(e){
    return String(obj);
  }
}

function buildProcessDetail(data){
  const area = document.getElementById("processArea");
  if(!data || !data.ok){
    area.innerHTML = "Tidak ada data proses.";
    return;
  }

  // Panel ringkas di atas
  let header = `
    <div class="mini">
      <div class="t">Ringkasan Proses</div>
      <div class="p">
        <b>Metode:</b> ${esc(data.summary.method_label)}<br/>
        <b>Mode:</b> ${esc(data.summary.mode)}<br/>
        <b>Aturan:</b> Duplikat jika <b>PATTERN</b> ditemukan sebagai substring dalam <b>TEXT</b> setelah normalisasi.
      </div>
    </div>
    <div style="height:10px"></div>
  `;

  let acc = `<div class="acc">`;

  data.results.forEach((r, idx) => {
    const ex = r.explain || {};
    const statusPill = (r.status === "DUPLIKAT")
      ? `<span class="tag tagDup">✓ DUPLIKAT</span>`
      : `<span class="tag tagNo">✗ TIDAK DUPLIKAT</span>`;

    const title = `Pasangan (${r.i1}, ${r.i2})`;
    const accBodyId = `accBody_${idx}`;

    // Method-specific info
    let extra = "";
    if (data.summary.method === "kmp"){
      extra = `
        <div class="kv">
          <div class="k">Info KMP</div>
          <div class="v">KMP memakai tabel LPS untuk menghindari perbandingan ulang saat mismatch.</div>
          <div class="k">LPS</div>
          <div class="v"><span class="pill">${esc((ex.lps||[]).join(", "))}</span></div>
        </div>
      `;
    } else if (data.summary.method === "bm"){
      extra = `
        <div class="kv">
          <div class="k">Info BM</div>
          <div class="v">BM memakai tabel last occurrence (bad character) untuk menentukan lompatan shift.</div>
          <div class="k">Last Table</div>
          <div class="v"><div class="codebox">${esc(formatJSON(ex.last_table||{}))}</div></div>
        </div>
      `;
    } else {
      extra = `
        <div class="kv">
          <div class="k">Info Naive</div>
          <div class="v">Naive menggeser pattern satu-per-satu dan membandingkan dari kiri.</div>
        </div>
      `;
    }

    // Alasan keputusan
    let alasan = "";
    if (r.status === "DUPLIKAT"){
      alasan = `PATTERN ditemukan pada TEXT (indeks ${esc(r.idx)}). Substring bukti di-highlight.`;
    } else {
      alasan = `Tidak ditemukan substring identik setelah semua pergeseran/shift diperiksa oleh metode ${esc(data.summary.method_label)}.`;
    }

    acc += `
      <div class="accItem">
        <div class="accHead" onclick="toggleAcc('${accBodyId}')">
          <div class="left">
            <span class="pill">${esc(title)}</span>
            ${statusPill}
          </div>
          <div class="pill">${esc(r.time_ms)} ms • ${esc(ex.comparisons ?? 0)} comps</div>
        </div>

        <div class="accBody" id="${accBodyId}" style="display:none">
          <div class="kv">
            <div class="k">Metode</div>
            <div class="v"><b>${esc(ex.metode || data.summary.method_label)}</b> — ${esc(ex.metode_ringkas || "")}</div>

            <div class="k">Aturan</div>
            <div class="v">${esc(ex.aturan_duplikasi || "")}</div>

            <div class="k">Kalimat A</div>
            <div class="v">${esc(r.a)}</div>

            <div class="k">Kalimat B</div>
            <div class="v">${esc(r.b)}</div>
          </div>

          <div class="grid2">
            <div>
              <div class="pill">Normalisasi A</div>
              <div class="codebox">${esc(ex.normA || "")}</div>
            </div>
            <div>
              <div class="pill">Normalisasi B</div>
              <div class="codebox">${esc(ex.normB || "")}</div>
            </div>
          </div>

          <div style="height:10px"></div>

          <div class="kv">
            <div class="k">TEXT</div>
            <div class="v">Sumber: <b>${esc(ex.text_source || "")}</b></div>
            <div class="k">PATTERN</div>
            <div class="v">Sumber: <b>${esc(ex.pattern_source || "")}</b></div>
          </div>

          <div class="grid2">
            <div>
              <div class="pill">TEXT (normalized)</div>
              <div class="codebox">${esc(ex.text_norm || "")}</div>
            </div>
            <div>
              <div class="pill">PATTERN (normalized)</div>
              <div class="codebox">${esc(ex.pattern_norm || "")}</div>
            </div>
          </div>

          ${extra}

          <div class="kv">
            <div class="k">Keputusan</div>
            <div class="v">${statusPill} — ${esc(alasan)}</div>
          </div>

          <div class="grid2">
            <div>
              <div class="pill">Bukti (Highlight) — Kalimat A</div>
              <div class="codebox" style="font-family:Inter,system-ui">${r.a_hl}</div>
            </div>
            <div>
              <div class="pill">Bukti (Highlight) — Kalimat B</div>
              <div class="codebox" style="font-family:Inter,system-ui">${r.b_hl}</div>
            </div>
          </div>

          ${data.summary.mode === "trace" ? `
            <div style="height:10px"></div>
            <div class="pill">Trace (Algoritma)</div>
            <div class="trace">${esc((r.trace || []).join("\\n"))}</div>
          ` : ``}
        </div>
      </div>
    `;
  });

  acc += `</div>`;
  area.innerHTML = header + acc;
}

async function run(){
  const runBtn = document.getElementById("runBtn");
  runBtn.disabled = true;

  showProcess(true);
  for(let i=1;i<=5;i++) setStep(i,"");
  setStep(1,"on");

  const raw = document.getElementById("sentences").value;
  const sents = splitSentences(raw);

  setStep(1,"done"); setStep(2,"on");

  const method = document.getElementById("method").value;
  const mode = document.getElementById("mode").value;

  const resArea = document.getElementById("resultArea");
  const procArea = document.getElementById("processArea");
  resArea.innerHTML = "Memproses...";
  procArea.innerHTML = "Memproses detail...";

  // tampilkan hasil dulu biar terlihat output
  goTo("results","nav_results");

  try{
    setStep(2,"done"); setStep(3,"on");
    const resp = await fetch("/api/check", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({sentences: sents, method, mode})
    });

    const data = await resp.json();
    if(!data.ok){
      showProcess(false);
      resArea.innerHTML = `<span style="color:#e11d48;font-weight:950">Error:</span> ${esc(data.error)}`;
      procArea.innerHTML = `<span style="color:#e11d48;font-weight:950">Error:</span> ${esc(data.error)}`;
      runBtn.disabled = false;
      return;
    }

    setStep(3,"done"); setStep(4,"on");

    document.getElementById("k_n").textContent = data.summary.n;
    document.getElementById("k_pairs").textContent = data.summary.total_pairs;
    document.getElementById("k_dup").textContent = data.summary.dup_count;
    document.getElementById("k_time").textContent = data.summary.total_time_ms.toFixed(3);

    // hasil tabel ringkas
    let html = `
    <table>
      <thead>
        <tr>
          <th>Pasangan</th>
          <th>Kalimat A (highlight)</th>
          <th>Kalimat B (highlight)</th>
          <th>Status</th>
          <th>Idx</th>
          <th>Waktu (ms)</th>
          <th>Comparisons</th>
        </tr>
      </thead>
      <tbody>
    `;

    data.results.forEach((r) => {
      const tag = r.status === "DUPLIKAT"
        ? `<span class="tag tagDup">✓ DUPLIKAT</span>`
        : `<span class="tag tagNo">✗ TIDAK</span>`;

      html += `
        <tr>
          <td><b>(${r.i1}, ${r.i2})</b></td>
          <td>${r.a_hl}</td>
          <td>${r.b_hl}</td>
          <td>${tag}</td>
          <td>${esc(String(r.idx))}</td>
          <td>${esc(String(r.time_ms))}</td>
          <td>${esc(String((r.explain||{}).comparisons ?? 0))}</td>
        </tr>
      `;
    });

    html += "</tbody></table>";
    resArea.innerHTML = html;

    setStep(4,"done"); setStep(5,"done");

    // build proses detail
    buildProcessDetail(data);

    // auto scroll ke proses (detail) biar dosen lihat "mengapa"
    goTo("process","nav_process");

  } catch(e){
    showProcess(false);
    resArea.innerHTML = `<span style="color:#e11d48;font-weight:950">Error:</span> Gagal memproses. ${esc(String(e))}`;
    procArea.innerHTML = `<span style="color:#e11d48;font-weight:950">Error:</span> Gagal memproses. ${esc(String(e))}`;
  } finally {
    runBtn.disabled = false;
  }
}
</script>
</body>
</html>
"""

@app.get("/")
def home():
    return render_template_string(HTML)

@app.post("/api/check")
def api_check():
    data = request.get_json(force=True, silent=True) or {}
    sentences = data.get("sentences", [])
    method = data.get("method", "naive")
    mode = data.get("mode", "fast")

    if not isinstance(sentences, list) or len(sentences) < 2:
        return jsonify(ok=False, error="Masukkan minimal 2 kalimat."), 400
    if len(sentences) > MAX_SENTENCES:
        return jsonify(ok=False, error=f"Maksimal {MAX_SENTENCES} kalimat."), 400

    clean_sentences = []
    for s in sentences:
        if not isinstance(s, str):
            return jsonify(ok=False, error="Semua input harus berupa teks."), 400
        s = s.strip()
        if len(s) == 0:
            continue
        if len(s) > MAX_INPUT_CHARS_PER_SENTENCE:
            return jsonify(ok=False, error=f"Satu kalimat terlalu panjang (>{MAX_INPUT_CHARS_PER_SENTENCE} karakter)."), 400
        clean_sentences.append(s)

    if len(clean_sentences) < 2:
        return jsonify(ok=False, error="Masukkan minimal 2 kalimat yang tidak kosong."), 400

    analysis_mode = (mode == "trace")

    n = len(clean_sentences)
    total_pairs = n * (n - 1) // 2
    results = []
    dup_count = 0
    total_time = 0.0

    for i in range(n):
        for j in range(i + 1, n):
            out = run_one_pair(method, clean_sentences[i], clean_sentences[j], analysis_mode)
            total_time += out["time_ms"]
            if out["idx"] >= 0:
                dup_count += 1

            results.append({
                "i1": i + 1,
                "i2": j + 1,
                "a": clean_sentences[i],
                "b": clean_sentences[j],
                "a_hl": out["a_hl"],
                "b_hl": out["b_hl"],
                "status": out["status"],
                "idx": out["idx"],
                "time_ms": out["time_ms"],
                "trace": out["trace"] if analysis_mode else None,
                "explain": out["explain"]
            })

    return jsonify(
        ok=True,
        summary={
            "n": n,
            "total_pairs": total_pairs,
            "dup_count": dup_count,
            "no_dup": total_pairs - dup_count,
            "total_time_ms": round(total_time, 3),
            "avg_time_ms": round(total_time / total_pairs, 3),
            "method": method,
            "method_label": method_label(method),
            "mode": "trace" if analysis_mode else "fast"
        },
        results=results
    )

if __name__ == "__main__":
    # Jalankan: python app.py
    # Buka: http://127.0.0.1:5000
    app.run(host="127.0.0.1", port=5000, debug=True)    