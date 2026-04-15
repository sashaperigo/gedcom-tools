"""
review_html.py — Local web server for interactive merge review.

Serves an HTML GUI at http://localhost:PORT/ showing proposed matches
side-by-side, accepting decisions via a JSON API, and auto-saving
progress to a session file after every decision.

Usage (from cli.py):
    from gedcom_merge.review_html import run_web_review
    decisions = run_web_review(source_result, indi_result, fam_result,
                               file_a, file_b, session, session_path)
"""

from __future__ import annotations
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from gedcom_merge.model import (
    GedcomFile, Individual, Source,
    SourceMatchResult, IndividualMatchResult, FamilyMatchResult,
    MergeDecisions,
)
from gedcom_merge.session import SessionState, save_session
from gedcom_merge.writer import _format_date
from gedcom_merge.match_individuals import (
    _estimate_birth_year,
    _build_surname_index,
    _score_pair,
)
from gedcom_merge.match_sources import _score_pair as _score_source_pair


# ---------------------------------------------------------------------------
# Data serialization helpers
# ---------------------------------------------------------------------------

def _fmt_date_str(d) -> str:
    if d is None:
        return ''
    return _format_date(d) or ''


def _indi_detail(ind: Individual | None, file: GedcomFile) -> dict:
    if ind is None:
        return {}
    names = [{'full': n.full, 'type': n.name_type or 'primary'} for n in ind.names]
    birth_ev = next((e for e in ind.events if e.tag == 'BIRT'), None)
    death_ev = next((e for e in ind.events if e.tag == 'DEAT'), None)
    buri_ev  = next((e for e in ind.events if e.tag == 'BURI'), None)

    parents: list[str] = []
    for famc in ind.family_child[:1]:
        fam = file.families.get(famc)
        if fam:
            for px in [fam.husband_xref, fam.wife_xref]:
                if px:
                    p = file.individuals.get(px)
                    if p:
                        parents.append(p.display_name)

    spouses: list[str] = []
    for fams in ind.family_spouse[:3]:
        fam = file.families.get(fams)
        if fam:
            for sx in [fam.husband_xref, fam.wife_xref]:
                if sx and sx != ind.xref:
                    s = file.individuals.get(sx)
                    if s:
                        spouses.append(s.display_name)
    spouses.sort()

    siblings: list[str] = []
    for famc in ind.family_child[:1]:
        fam = file.families.get(famc)
        if fam:
            for sib_xref in fam.child_xrefs:
                if sib_xref != ind.xref:
                    sib = file.individuals.get(sib_xref)
                    if sib:
                        siblings.append(sib.display_name)
    siblings.sort()
    siblings = siblings[:6]

    children: list[str] = []
    for fams in ind.family_spouse[:3]:
        fam = file.families.get(fams)
        if fam:
            for chil_xref in fam.child_xrefs:
                child = file.individuals.get(chil_xref)
                if child:
                    children.append(child.display_name)
    children.sort()
    children = children[:8]

    citation_count = len(ind.citations) + sum(len(e.citations) for e in ind.events)

    # Estimated birth year when none is recorded
    has_birth = birth_ev and birth_ev.date and birth_ev.date.year
    birth_date_calc = ''
    birth_date_calc_basis = ''
    if not has_birth:
        est_year = _estimate_birth_year(ind, file)
        if est_year:
            birth_date_calc = 'est. ~' + str(est_year)
            # Determine basis label for the tooltip
            basis_parts = []
            for fams in ind.family_spouse[:1]:
                fam = file.families.get(fams)
                if fam:
                    for sx in [fam.husband_xref, fam.wife_xref]:
                        if sx and sx != ind.xref:
                            sp = file.individuals.get(sx)
                            if sp:
                                sp_birt = next((e for e in sp.events if e.tag == 'BIRT'), None)
                                if sp_birt and sp_birt.date and sp_birt.date.year:
                                    basis_parts.append('spouse ' + sp.display_name)
            for famc in ind.family_child[:1]:
                fam = file.families.get(famc)
                if fam:
                    for px in [fam.husband_xref, fam.wife_xref]:
                        if not px:
                            continue
                        parent = file.individuals.get(px)
                        if parent:
                            p_birt = next((e for e in parent.events if e.tag == 'BIRT'), None)
                            if p_birt and p_birt.date and p_birt.date.year:
                                basis_parts.append('parent ' + parent.display_name)
                                break
            for fams in ind.family_spouse[:2]:
                fam = file.families.get(fams)
                if fam:
                    for chil_xref in fam.child_xrefs[:1]:
                        child_ind = file.individuals.get(chil_xref)
                        if child_ind:
                            c_birt = next((e for e in child_ind.events if e.tag == 'BIRT'), None)
                            if c_birt and c_birt.date and c_birt.date.year:
                                basis_parts.append('child ' + child_ind.display_name)
                                break
            birth_date_calc_basis = 'from ' + ' & '.join(basis_parts) if basis_parts else ''

    return {
        'xref': ind.xref,
        'display_name': ind.display_name,
        'names': names,
        'sex': ind.sex or '',
        'birth_date': _fmt_date_str(birth_ev.date) if birth_ev else '',
        'birth_place': (birth_ev.place or '') if birth_ev else '',
        'birth_date_calc': birth_date_calc,
        'birth_date_calc_basis': birth_date_calc_basis,
        'death_date': _fmt_date_str(death_ev.date) if death_ev else '',
        'death_place': (death_ev.place or '') if death_ev else '',
        'burial_date': _fmt_date_str(buri_ev.date) if buri_ev else '',
        'burial_place': (buri_ev.place or '') if buri_ev else '',
        'parents': parents,
        'spouses': spouses,
        'siblings': siblings,
        'children': children,
        'citation_count': citation_count,
        'fams_count': len(ind.family_spouse),
    }


def _src_detail(src: Source | None) -> dict:
    if src is None:
        return {}
    return {
        'xref': src.xref,
        'title': src.title,
        'author': src.author or '',
        'publisher': src.publisher or '',
        'repo': src.repository_xref or '',
        'notes_count': len(src.notes),
    }


def _build_review_data(
    source_result: SourceMatchResult,
    indi_result: IndividualMatchResult,
    fam_result: FamilyMatchResult,
    file_a: GedcomFile,
    file_b: GedcomFile,
) -> dict:
    """Serialize all match data to a JSON-serializable dict."""

    def _indi_match_item(m) -> dict:
        return {
            'xref_a': m.xref_a,
            'xref_b': m.xref_b,
            'score': round(m.score, 3),
            'score_components': m.score_components,
            'detail_a': _indi_detail(file_a.individuals.get(m.xref_a), file_a),
            'detail_b': _indi_detail(file_b.individuals.get(m.xref_b), file_b),
        }

    def _src_match_item(m) -> dict:
        return {
            'xref_a': m.xref_a,
            'xref_b': m.xref_b,
            'score': round(m.score, 3),
            'detail_a': _src_detail(file_a.sources.get(m.xref_a)),
            'detail_b': _src_detail(file_b.sources.get(m.xref_b)),
        }

    return {
        'file_a_name': file_a.path or 'File A',
        'file_b_name': file_b.path or 'File B',
        'auto': {
            'sources': [_src_match_item(m) for m in source_result.auto_matches],
            'individuals': [_indi_match_item(m) for m in indi_result.auto_matches],
            'families': [
                {'xref_a': m.xref_a, 'xref_b': m.xref_b}
                for m in fam_result.matches
            ],
        },
        'candidates': {
            'sources': [_src_match_item(m) for m in source_result.candidates],
            'individuals': [_indi_match_item(m) for m in indi_result.candidates],
        },
        'unmatched': {
            'sources': [_src_detail(file_b.sources.get(x)) | {'xref_b': x}
                        for x in source_result.unmatched_b],
            'individuals': [
                _indi_detail(file_b.individuals.get(x), file_b) | {'xref_b': x}
                for x in indi_result.unmatched_b
            ],
            'families': [{'xref_b': x} for x in fam_result.unmatched_b],
        },
    }


# ---------------------------------------------------------------------------
# HTML template (plain string — no f-string, to avoid JS ${} conflicts)
# Two placeholders: %%DATA_JSON%% and %%SESSION_PATH%%
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>GEDCOM Merge Review</title>
<style>
:root {
  --bg:#0f1117; --surface:#1a1d27; --surface2:#252836; --border:#2e3147;
  --accent:#4f8ef7; --accent2:#7c5fe6; --green:#34c46a; --red:#e05252;
  --yellow:#f5a623; --text:#e2e4ef; --text2:#8b90a8; --text3:#5a5f7d;
  --radius:8px;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:var(--bg);color:var(--text);font-size:14px;line-height:1.5}
#app{display:flex;flex-direction:column;height:100vh;overflow:hidden}

/* Header */
header{background:var(--surface);border-bottom:1px solid var(--border);
       padding:12px 20px;display:flex;align-items:center;gap:12px;flex-shrink:0}
header h1{font-size:15px;font-weight:600}
.file-labels{display:flex;gap:10px;font-size:12px}
.file-labels span{padding:2px 8px;border-radius:4px}
.label-a{background:rgba(79,142,247,.15);color:var(--accent)}
.label-b{background:rgba(124,95,230,.15);color:var(--accent2)}
.progress-bar{flex:1;height:6px;background:var(--border);border-radius:3px;overflow:hidden}
.progress-fill{height:100%;background:linear-gradient(90deg,var(--accent),var(--green));transition:width .3s}
.progress-text{font-size:12px;color:var(--text2);white-space:nowrap}
#save-ind{font-size:12px;color:var(--text3);transition:color .3s}
#save-ind.saving{color:var(--yellow)} #save-ind.saved{color:var(--green)}

/* Nav */
nav{background:var(--surface);border-bottom:1px solid var(--border);
    display:flex;flex-shrink:0}
nav button{background:none;border:none;color:var(--text2);cursor:pointer;
           padding:10px 18px;font-size:13px;border-bottom:2px solid transparent;
           transition:color .15s}
nav button:hover{color:var(--text)}
nav button.active{color:var(--accent);border-bottom-color:var(--accent);font-weight:500}
.badge{background:var(--surface2);color:var(--text2);font-size:11px;
       padding:1px 6px;border-radius:10px;margin-left:4px}

/* Main */
main{flex:1;overflow-y:auto;padding:20px}

/* Cards */
.card{background:var(--surface);border:1px solid var(--border);
      border-radius:var(--radius);margin-bottom:14px;overflow:hidden}
.card-header{padding:12px 16px;border-bottom:1px solid var(--border);
             display:flex;align-items:center;gap:10px;flex-wrap:wrap}

/* Score badge */
.score{font-size:12px;font-weight:600;padding:2px 8px;border-radius:12px}
.score-hi{background:rgba(52,196,106,.15);color:var(--green)}
.score-md{background:rgba(245,166,35,.15);color:var(--yellow)}
.score-lo{background:rgba(224,82,82,.15);color:var(--red)}

/* Comparison table */
.cmp{width:100%;border-collapse:collapse}
.cmp th{padding:8px 12px;font-size:11px;text-transform:uppercase;
        letter-spacing:.06em;text-align:left;font-weight:600}
.cmp th.a{color:var(--accent)} .cmp th.b{color:var(--accent2)}
.cmp td{padding:6px 12px;border-top:1px solid var(--border);vertical-align:top}
.cmp td.lbl{font-size:11px;text-transform:uppercase;color:var(--text3);
            white-space:nowrap;width:80px}
.cmp .diff-cell{background:rgba(245,166,35,.08);border-left:2px solid var(--yellow)}
.empty{color:var(--text3);font-style:italic}
.name-primary{font-size:15px;font-weight:600}
.name-aka{font-size:12px;color:var(--text2)}

/* Score breakdown */
.score-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:4px;
            padding:10px 14px;border-top:1px solid var(--border)}
.sc-item{text-align:center}
.sc-lbl{font-size:10px;color:var(--text3);text-transform:uppercase}
.sc-val{font-size:13px;font-weight:600}

/* Action bar */
.actions{padding:12px 16px;border-top:1px solid var(--border);
         display:flex;align-items:center;gap:8px;background:var(--surface2)}
.btn{padding:7px 18px;border-radius:6px;border:none;cursor:pointer;
     font-size:13px;font-weight:500;transition:opacity .15s,transform .1s}
.btn:hover{opacity:.85} .btn:active{transform:scale(.97)}
.btn-merge{background:var(--green);color:#fff}
.btn-add{background:var(--accent);color:#fff}
.btn-skip{background:var(--surface);color:var(--text2);border:1px solid var(--border)}
.btn-approve{background:var(--green);color:#fff;padding:9px 24px;font-size:14px}
.btn-finish{background:var(--accent2);color:#fff;padding:9px 20px;font-size:13px;margin-left:auto}
.hint{font-size:11px;color:var(--text3);margin-left:auto}
kbd{background:var(--surface2);border:1px solid var(--border);border-radius:3px;
    padding:1px 5px;font-size:10px;font-family:monospace;color:var(--text2)}

/* Decided states */
.decided{padding:8px 16px;font-size:12px;display:flex;align-items:center;gap:8px}
.d-merge{background:rgba(52,196,106,.08);color:var(--green)}
.d-skip{background:rgba(90,95,125,.1);color:var(--text2)}
.d-add{background:rgba(79,142,247,.08);color:var(--accent)}

/* Empty state */
.empty-state{text-align:center;padding:60px 20px;color:var(--text3)}
.empty-state .icon{font-size:40px;margin-bottom:10px}

/* Back-to-top button */
#back-top{position:fixed;bottom:24px;right:24px;background:var(--surface2);
          border:1px solid var(--border);color:var(--text2);border-radius:50%;
          width:40px;height:40px;font-size:18px;cursor:pointer;display:none;
          align-items:center;justify-content:center;z-index:50;
          box-shadow:0 2px 8px rgba(0,0,0,.4);transition:opacity .2s}
#back-top.show{display:flex} #back-top:hover{color:var(--text);border-color:var(--accent)}

/* Finish overlay */
#overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);
         align-items:center;justify-content:center;z-index:100}
#overlay.on{display:flex}
.finish-card{background:var(--surface);border:1px solid var(--border);
             border-radius:12px;padding:32px;max-width:440px;text-align:center}
.finish-card h2{font-size:20px;margin-bottom:10px}
.finish-card p{color:var(--text2);margin-bottom:20px}
.fstats{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:20px}
.fstat{background:var(--surface2);border-radius:8px;padding:12px}
.fstat .n{font-size:24px;font-weight:700;color:var(--accent)}
.fstat .l{font-size:11px;color:var(--text3);text-transform:uppercase}
</style>
</head>
<body>
<div id="app">
  <header>
    <h1>GEDCOM Merge Review</h1>
    <div class="file-labels">
      <span class="label-a" id="lbl-a"></span>
      <span class="label-b" id="lbl-b"></span>
    </div>
    <div class="progress-bar"><div class="progress-fill" id="pfill" style="width:0%"></div></div>
    <div class="progress-text" id="ptxt">0 / 0 decided</div>
    <div id="save-ind">&#9679; saved</div>
    <button class="btn btn-finish" onclick="showFinish()">Finish Review &rarr;</button>
  </header>
  <nav>
    <button class="active" onclick="tab('auto')" id="t-auto">Auto-matches<span class="badge" id="b-auto">0</span></button>
    <button onclick="tab('cand')" id="t-cand">Candidates<span class="badge" id="b-cand">0</span></button>
    <button onclick="tab('unmat')" id="t-unmat">Unmatched<span class="badge" id="b-unmat">0</span></button>
  </nav>
  <main id="main"></main>
</div>
<button id="back-top" title="Back to top" onclick="document.getElementById('main').scrollTo({top:0,behavior:'smooth'})">&#8679;</button>
<div id="overlay">
  <div class="finish-card">
    <h2>Review Complete</h2>
    <p>Click below to send your decisions to the merge process.</p>
    <div class="fstats">
      <div class="fstat"><div class="n" id="fs-merged">0</div><div class="l">Merged</div></div>
      <div class="fstat"><div class="n" id="fs-added">0</div><div class="l">Added</div></div>
      <div class="fstat"><div class="n" id="fs-skipped">0</div><div class="l">Skipped</div></div>
    </div>
    <button class="btn btn-approve" onclick="finish()" style="width:100%">Finish &amp; Run Merge</button>
    <br><br>
    <button class="btn btn-skip" onclick="document.getElementById('overlay').classList.remove('on')">Cancel</button>
  </div>
</div>

<script>
/* ─── Bootstrap data injected by server ─────────────────────────── */
const DATA = %%DATA_JSON%%;
const SESSION_PATH = %%SESSION_PATH%%;

/* ─── Mutable decisions state ────────────────────────────────────── */
const D = {
  source_map: {}, indi_map: {}, family_map: {},
  source_disposition: {}, indi_disposition: {}, family_disposition: {},
  auto_approved: false
};

let currentTab = 'auto';
let saveTimer = null;

/* ─── Init ───────────────────────────────────────────────────────── */
window.addEventListener('DOMContentLoaded', () => {
  document.getElementById('lbl-a').textContent = DATA.file_a_name;
  document.getElementById('lbl-b').textContent = DATA.file_b_name;
  updateBadges();
  loadState().then(() => render());
  document.getElementById('main').addEventListener('scroll', function() {
    document.getElementById('back-top').classList.toggle('show', this.scrollTop > 300);
  });
});

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT') return;
  if (e.key === 'm') document.querySelector('.btn-merge') && document.querySelector('.btn-merge').click();
  if (e.key === 's') document.querySelector('.btn-skip-u') && document.querySelector('.btn-skip-u').click();
  if (e.key === 'a') document.querySelector('.btn-add-u') && document.querySelector('.btn-add-u').click();
});

/* ─── State sync with server ─────────────────────────────────────── */
async function loadState() {
  try {
    const r = await fetch('/api/state');
    const saved = await r.json();
    if (saved.decisions) Object.assign(D, saved.decisions);
    updateProgress();
  } catch(_) {}
}

function scheduleSave() {
  const el = document.getElementById('save-ind');
  el.textContent = '\u25cf saving\u2026'; el.className = 'saving';
  clearTimeout(saveTimer);
  saveTimer = setTimeout(doSave, 700);
}

async function doSave() {
  try {
    await fetch('/api/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(D)
    });
    const el = document.getElementById('save-ind');
    el.textContent = '\u25cf saved'; el.className = 'saved';
    setTimeout(() => { el.textContent = '\u25cf saved'; el.className = ''; }, 2000);
  } catch(_) {}
}

/* ─── Progress ───────────────────────────────────────────────────── */
function totalDecidable() {
  return DATA.auto.individuals.length + DATA.auto.sources.length +
         DATA.auto.families.length + DATA.candidates.individuals.length +
         DATA.candidates.sources.length + DATA.unmatched.individuals.length +
         DATA.unmatched.sources.length + DATA.unmatched.families.length;
}
function decidedCount() {
  return Object.keys(D.indi_map).length + Object.keys(D.source_map).length +
         Object.keys(D.family_map).length + Object.keys(D.indi_disposition).length +
         Object.keys(D.source_disposition).length + Object.keys(D.family_disposition).length;
}
function updateProgress() {
  const total = totalDecidable(), done = decidedCount();
  const pct = total ? Math.round(done/total*100) : 0;
  document.getElementById('pfill').style.width = pct + '%';
  document.getElementById('ptxt').textContent = done + ' / ' + total + ' decided';
}
function updateBadges() {
  document.getElementById('b-auto').textContent =
    DATA.auto.individuals.length + DATA.auto.sources.length + DATA.auto.families.length;
  document.getElementById('b-cand').textContent =
    DATA.candidates.individuals.length + DATA.candidates.sources.length;
  document.getElementById('b-unmat').textContent =
    DATA.unmatched.individuals.length + DATA.unmatched.sources.length + DATA.unmatched.families.length;
}

/* ─── Tab switching ──────────────────────────────────────────────── */
function tab(name) {
  currentTab = name;
  ['auto','cand','unmat'].forEach(t => {
    document.getElementById('t-' + t).classList.toggle('active', t === name);
  });
  render();
}
function render() {
  const m = document.getElementById('main');
  if (currentTab === 'auto')   m.innerHTML = renderAuto();
  else if (currentTab === 'cand')  m.innerHTML = renderCandidates();
  else m.innerHTML = renderUnmatched();
}

/* ─── Decision helpers ───────────────────────────────────────────── */
function decide(type, xref_b, action, xref_a) {
  if (type === 'indi') {
    if (action === 'merge') {
      D.indi_map[xref_b] = xref_a; delete D.indi_disposition[xref_b];
      // Once a File A person is matched, remove all other candidates pointing to them
      DATA.candidates.individuals.forEach(function(m) {
        if (m.xref_a === xref_a && m.xref_b !== xref_b) {
          delete D.indi_map[m.xref_b];
          D.indi_disposition[m.xref_b] = 'skip';
        }
      });
    } else { delete D.indi_map[xref_b]; D.indi_disposition[xref_b] = action; }
  } else if (type === 'source') {
    if (action === 'merge') {
      D.source_map[xref_b] = xref_a; delete D.source_disposition[xref_b];
      DATA.candidates.sources.forEach(function(m) {
        if (m.xref_a === xref_a && m.xref_b !== xref_b) {
          delete D.source_map[m.xref_b];
          D.source_disposition[m.xref_b] = 'skip';
        }
      });
    } else { delete D.source_map[xref_b]; D.source_disposition[xref_b] = action; }
  } else if (type === 'fam') {
    if (action === 'merge') {
      D.family_map[xref_b] = xref_a; delete D.family_disposition[xref_b];
      DATA.candidates.families.forEach(function(m) {
        if (m.xref_a === xref_a && m.xref_b !== xref_b) {
          delete D.family_map[m.xref_b];
          D.family_disposition[m.xref_b] = 'skip';
        }
      });
    } else { delete D.family_map[xref_b]; D.family_disposition[xref_b] = action; }
  }
  scheduleSave(); updateProgress(); render();
}
function undecide(type, xref_b) {
  if (type === 'indi') { delete D.indi_map[xref_b]; delete D.indi_disposition[xref_b]; }
  else if (type === 'source') { delete D.source_map[xref_b]; delete D.source_disposition[xref_b]; }
  else if (type === 'fam') { delete D.family_map[xref_b]; delete D.family_disposition[xref_b]; }
  scheduleSave(); updateProgress(); render();
}

/* ─── Batch operations ───────────────────────────────────────────── */
function approveAll() {
  DATA.auto.individuals.forEach(m => { D.indi_map[m.xref_b] = m.xref_a; delete D.indi_disposition[m.xref_b]; });
  DATA.auto.sources.forEach(m => { D.source_map[m.xref_b] = m.xref_a; delete D.source_disposition[m.xref_b]; });
  DATA.auto.families.forEach(m => { D.family_map[m.xref_b] = m.xref_a; delete D.family_disposition[m.xref_b]; });
  D.auto_approved = true;
  scheduleSave(); updateProgress(); render();
}
function approveRemaining() {
  DATA.auto.individuals.forEach(m => {
    if (D.indi_disposition[m.xref_b] !== 'skip') { D.indi_map[m.xref_b] = m.xref_a; delete D.indi_disposition[m.xref_b]; }
  });
  DATA.auto.sources.forEach(m => {
    if (D.source_disposition[m.xref_b] !== 'skip') { D.source_map[m.xref_b] = m.xref_a; delete D.source_disposition[m.xref_b]; }
  });
  DATA.auto.families.forEach(m => {
    if (D.family_disposition[m.xref_b] !== 'skip') { D.family_map[m.xref_b] = m.xref_a; delete D.family_disposition[m.xref_b]; }
  });
  scheduleSave(); updateProgress(); render();
}
function unapproveAll() {
  DATA.auto.individuals.forEach(m => { delete D.indi_map[m.xref_b]; });
  DATA.auto.sources.forEach(m => { delete D.source_map[m.xref_b]; });
  DATA.auto.families.forEach(m => { delete D.family_map[m.xref_b]; });
  D.auto_approved = false;
  scheduleSave(); updateProgress(); render();
}
function addAllUnmatched() {
  DATA.unmatched.individuals.forEach(d => D.indi_disposition[d.xref_b] = 'add');
  DATA.unmatched.sources.forEach(d => D.source_disposition[d.xref_b] = 'add');
  DATA.unmatched.families.forEach(d => D.family_disposition[d.xref_b] = 'add');
  scheduleSave(); updateProgress(); render();
}
function skipAllUnmatched() {
  DATA.unmatched.individuals.forEach(d => D.indi_disposition[d.xref_b] = 'skip');
  DATA.unmatched.sources.forEach(d => D.source_disposition[d.xref_b] = 'skip');
  DATA.unmatched.families.forEach(d => D.family_disposition[d.xref_b] = 'skip');
  scheduleSave(); updateProgress(); render();
}

/* ─── Render helpers ─────────────────────────────────────────────── */
function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
                      .replace(/"/g,'&quot;');
}
function scoreCls(s) { return s>=.85?'score-hi':s>=.65?'score-md':'score-lo'; }

function indiHeader(da, db, score) {
  var ba = [da.birth_date||da.birth_date_calc, da.birth_place].filter(Boolean).join(' \u00b7 ');
  var bb = [db.birth_date||db.birth_date_calc, db.birth_place].filter(Boolean).join(' \u00b7 ');
  return '<span class="score ' + scoreCls(score) + '">' + Math.round(score*100) + '% match</span> ' +
    '<strong>' + esc(da.display_name||'?') + '</strong>' +
    (ba ? ' <span style="color:var(--text2);font-size:12px;">' + esc(ba) + '</span>' : '') +
    ' <span style="color:var(--text3);">&harr;</span> ' +
    '<strong>' + esc(db.display_name||'?') + '</strong>' +
    (bb ? ' <span style="color:var(--text2);font-size:12px;">' + esc(bb) + '</span>' : '');
}

function srcHeader(da, db, score) {
  var ta = (da.title||'').substring(0,55) + ((da.title||'').length>55?'\u2026':'');
  var tb = (db.title||'').substring(0,55) + ((db.title||'').length>55?'\u2026':'');
  return '<span class="score ' + scoreCls(score) + '">' + Math.round(score*100) + '% match</span> ' +
    '<em>' + esc(ta) + '</em> <span style="color:var(--text3);">&harr;</span> <em>' + esc(tb) + '</em>';
}

function cmpRow(label, va, vb) {
  var diff = va && vb && va !== vb;
  var dc = diff ? ' diff-cell' : '';
  return '<tr><td class="lbl">' + label + '</td>' +
    '<td class="' + dc + '">' + (va ? esc(va) : '<span class="empty">&mdash;</span>') + '</td>' +
    '<td class="' + dc + '">' + (vb ? esc(vb) : '<span class="empty">&mdash;</span>') + '</td></tr>';
}

function namesHtml(names) {
  if (!names || !names.length) return '<span class="empty">&mdash;</span>';
  return names.map(function(n, i) {
    return '<div class="' + (i===0?'name-primary':'name-aka') + '">' + esc(n.full) +
      (n.type && n.type !== 'primary' ? ' <span style="font-size:11px;color:var(--text3);">' + esc(n.type) + '</span>' : '') + '</div>';
  }).join('');
}

function bornCell(d) {
  var parts = [d.birth_date, d.birth_place].filter(Boolean);
  if (parts.length) return esc(parts.join(' \u00b7 '));
  if (d.birth_date_calc) {
    var tip = d.birth_date_calc_basis ? ' title="' + esc(d.birth_date_calc_basis) + '"' : '';
    return '<span style="color:var(--yellow);font-style:italic;"' + tip + '>' + esc(d.birth_date_calc) + '</span>';
  }
  return '<span class="empty">&mdash;</span>';
}

function indiTable(da, db, comps) {
  var bornA = bornCell(da), bornB = bornCell(db);
  var bornDiff = (da.birth_date||da.birth_date_calc) && (db.birth_date||db.birth_date_calc) &&
                 (da.birth_date||da.birth_date_calc) !== (db.birth_date||db.birth_date_calc);
  var bornDc = bornDiff ? ' diff-cell' : '';

  var rows = [
    '<tr><td class="lbl">Name</td><td>' + namesHtml(da.names) + '</td><td>' + namesHtml(db.names) + '</td></tr>',
    cmpRow('Sex', da.sex, db.sex),
    '<tr><td class="lbl">Born</td><td class="' + bornDc + '">' + bornA + '</td><td class="' + bornDc + '">' + bornB + '</td></tr>',
    cmpRow('Died', [da.death_date, da.death_place].filter(Boolean).join(' \u00b7 '),
                   [db.death_date, db.death_place].filter(Boolean).join(' \u00b7 ')),
    cmpRow('Buried', [da.burial_date, da.burial_place].filter(Boolean).join(' \u00b7 '),
                     [db.burial_date, db.burial_place].filter(Boolean).join(' \u00b7 ')),
    cmpRow('Parents', (da.parents||[]).join(' & '), (db.parents||[]).join(' & ')),
    cmpRow('Siblings', (da.siblings||[]).join(', '), (db.siblings||[]).join(', ')),
    cmpRow('Children', (da.children||[]).join(', '), (db.children||[]).join(', ')),
    cmpRow('Spouse(s)', (da.spouses||[]).join(', '), (db.spouses||[]).join(', ')),
    cmpRow('Sources', da.citation_count ? da.citation_count + ' citations' : '',
                      db.citation_count ? db.citation_count + ' citations' : '')
  ].join('');

  var scoreBreakdown = '';
  if (comps && Object.keys(comps).length) {
    scoreBreakdown = '<div class="score-grid">' + Object.entries(comps).map(function(kv) {
      var v = kv[1], cls = v>=.8 ? 'var(--green)' : v>=.5 ? 'var(--yellow)' : 'var(--red)';
      return '<div class="sc-item"><div class="sc-lbl">' + esc(kv[0]) + '</div>' +
        '<div class="sc-val" style="color:' + cls + '">' + Math.round(v*100) + '%</div></div>';
    }).join('') + '</div>';
  }

  return '<table class="cmp"><thead><tr><th></th>' +
    '<th class="a">File A &nbsp;<span style="color:var(--text3);font-weight:400;font-size:10px;">' + esc(da.xref||'') + '</span></th>' +
    '<th class="b">File B &nbsp;<span style="color:var(--text3);font-weight:400;font-size:10px;">' + esc(db.xref||'') + '</span></th>' +
    '</tr></thead><tbody>' + rows + '</tbody></table>' + scoreBreakdown;
}

function srcTable(da, db) {
  return '<table class="cmp"><thead><tr><th></th><th class="a">File A</th><th class="b">File B</th></tr></thead><tbody>' +
    cmpRow('Title', da.title, db.title) + cmpRow('Author', da.author, db.author) +
    cmpRow('Publisher', da.publisher, db.publisher) + '</tbody></table>';
}

/* ─── Individual card ────────────────────────────────────────────── */
function indiCard(m) {
  var xb = m.xref_b, xa = m.xref_a, da = m.detail_a||{}, db = m.detail_b||{};
  var mergedTo = D.indi_map[xb], disp = D.indi_disposition[xb];
  var decided = mergedTo || disp;

  var actionBar;
  if (mergedTo) {
    actionBar = '<div class="decided d-merge">\u2713 Merged &rarr; ' + esc(xa) +
      ' <button class="btn btn-skip" style="margin-left:8px;font-size:11px;" onclick="undecide(\'indi\',\'' + esc(xb) + '\')">Undo</button></div>';
  } else if (disp) {
    actionBar = '<div class="decided d-' + disp + '">\u2717 ' + disp +
      ' <button class="btn btn-skip" style="margin-left:8px;font-size:11px;" onclick="undecide(\'indi\',\'' + esc(xb) + '\')">Undo</button></div>';
  } else {
    actionBar = '<div class="actions">' +
      '<button class="btn btn-merge btn-skip-u" onclick="decide(\'indi\',\'' + esc(xb) + '\',\'merge\',\'' + esc(xa) + '\')">Merge &mdash; same person</button>' +
      '<button class="btn btn-skip btn-skip-u" onclick="decide(\'indi\',\'' + esc(xb) + '\',\'skip\',null)">Different people</button>' +
      '<span class="hint"><kbd>m</kbd> merge &nbsp; <kbd>s</kbd> skip</span></div>';
  }

  return '<div class="card" style="' + (mergedTo?'border-color:rgba(52,196,106,.3)':decided?'opacity:.7':'') + '">' +
    '<div class="card-header">' + indiHeader(da, db, m.score) + '</div>' +
    indiTable(da, db, m.score_components) + actionBar + '</div>';
}

/* ─── Source card ────────────────────────────────────────────────── */
function srcCard(m) {
  var xb = m.xref_b, xa = m.xref_a, da = m.detail_a||{}, db = m.detail_b||{};
  var mergedTo = D.source_map[xb], disp = D.source_disposition[xb];

  var actionBar;
  if (mergedTo) {
    actionBar = '<div class="decided d-merge">\u2713 Merged' +
      ' <button class="btn btn-skip" style="margin-left:8px;font-size:11px;" onclick="undecide(\'source\',\'' + esc(xb) + '\')">Undo</button></div>';
  } else if (disp) {
    actionBar = '<div class="decided d-' + disp + '">\u2717 ' + disp +
      ' <button class="btn btn-skip" style="margin-left:8px;font-size:11px;" onclick="undecide(\'source\',\'' + esc(xb) + '\')">Undo</button></div>';
  } else {
    actionBar = '<div class="actions">' +
      '<button class="btn btn-merge" onclick="decide(\'source\',\'' + esc(xb) + '\',\'merge\',\'' + esc(xa) + '\')">Merge &mdash; same source</button>' +
      '<button class="btn btn-skip" onclick="decide(\'source\',\'' + esc(xb) + '\',\'skip\',null)">Different sources</button></div>';
  }

  return '<div class="card" style="' + (mergedTo?'border-color:rgba(52,196,106,.3)':'') + '">' +
    '<div class="card-header">' + srcHeader(da, db, m.score) + '</div>' +
    srcTable(da, db) + actionBar + '</div>';
}

/* ─── Unmatched individual ───────────────────────────────────────── */
var _searchCache = {};  // xref_b → results array
var _searchOpen = {};   // xref_b → bool

async function searchMatch(xref_b) {
  _searchOpen[xref_b] = !_searchOpen[xref_b];
  if (_searchOpen[xref_b] && !_searchCache[xref_b]) {
    var el = document.getElementById('srch-' + xref_b.replace(/[@]/g,''));
    if (el) el.innerHTML = '<div style="padding:12px;color:var(--text2);font-size:13px;">Searching\u2026</div>';
    try {
      var r = await fetch('/api/search_match?xref_b=' + encodeURIComponent(xref_b));
      var data = await r.json();
      _searchCache[xref_b] = data.results || [];
    } catch(_) { _searchCache[xref_b] = []; }
  }
  render();
}

function renderSearchPanel(xref_b) {
  if (!_searchOpen[xref_b]) return '';
  var results = _searchCache[xref_b];
  if (!results) {
    return '<div id="srch-' + xref_b.replace(/[@]/g,'') + '" style="border-top:1px solid var(--border);padding:12px;color:var(--text2);font-size:13px;">Searching\u2026</div>';
  }
  if (!results.length) {
    return '<div style="border-top:1px solid var(--border);padding:12px;color:var(--text2);font-size:13px;">No candidates found in File A.</div>';
  }
  var html = '<div style="border-top:1px solid var(--border);padding:12px 16px;background:rgba(0,0,0,.15);">' +
    '<div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text3);margin-bottom:10px;">Top candidates in File A</div>';
  results.forEach(function(m) {
    var da = m.detail_a||{}, db = m.detail_b||{};
    var pct = Math.round(m.score * 100);
    var cls = m.score>=.85?'score-hi':m.score>=.65?'score-md':'score-lo';
    html += '<div style="border:1px solid var(--border);border-radius:6px;margin-bottom:10px;overflow:hidden;">' +
      '<div style="padding:10px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;">' +
      '<span class="score ' + cls + '">' + pct + '% match</span>' +
      '<strong>' + esc(da.display_name||'?') + '</strong>';
    var ba = [da.birth_date||da.birth_date_calc, da.birth_place].filter(Boolean).join(' \u00b7 ');
    if (ba) html += ' <span style="font-size:12px;color:var(--text2);">' + esc(ba) + '</span>';
    html += '</div>' + indiTable(da, db, m.score_components) +
      '<div class="actions" style="padding:8px 14px;">' +
      '<button class="btn btn-merge" onclick="_mergeFromSearch(\'' + esc(xref_b) + '\',\'' + esc(m.xref_a) + '\')">Merge &mdash; same person</button>' +
      '<button class="btn btn-add" style="margin-left:6px;" onclick="_addFromSearch(\'' + esc(xref_b) + '\')">Add as new person</button>' +
      '</div></div>';
  });
  html += '</div>';
  return html;
}

function _mergeFromSearch(xref_b, xref_a) {
  _searchOpen[xref_b] = false;
  decide('indi', xref_b, 'merge', xref_a);
}
function _addFromSearch(xref_b) {
  _searchOpen[xref_b] = false;
  decide('indi', xref_b, 'add', null);
}

function unmatchedIndi(d) {
  var xb = d.xref_b, disp = D.indi_disposition[xb], mergedTo = D.indi_map[xb];
  var meta = [d.birth_date, d.birth_place].filter(Boolean).join(' \u00b7 ');
  var filePill = '<span style="font-size:10px;font-weight:600;letter-spacing:.05em;padding:2px 7px;border-radius:10px;background:rgba(79,142,247,.18);color:#7eb0ff;margin-left:8px;">' + esc(DATA.file_b_name) + '</span>';
  var info = '<div style="font-size:15px;font-weight:600;display:flex;align-items:center;">' + esc(d.display_name||xb) + filePill + '</div>';
  if (meta) info += '<div style="font-size:12px;color:var(--text2);margin-top:3px;">' + esc(meta) + '</div>';
  if (d.parents && d.parents.length) info += '<div style="font-size:12px;color:var(--text2);">Parents: ' + esc(d.parents.join(' & ')) + '</div>';
  if (d.spouses && d.spouses.length) info += '<div style="font-size:12px;color:var(--text2);">Spouse: ' + esc(d.spouses.join(', ')) + '</div>';

  var searchBtn = '<button class="btn" style="margin-left:auto;font-size:12px;background:rgba(79,142,247,.18);color:#7eb0ff;border:1px solid rgba(79,142,247,.35);" onclick="searchMatch(\'' + esc(xb) + '\')">' +
    (_searchOpen[xb] ? '\u25b2 Hide matches' : '\ud83d\udd0d Find match in File A') + '</button>';

  var actionBar;
  if (mergedTo) {
    actionBar = '<div class="decided d-merge">\u2713 Merged \u2192 ' + esc(mergedTo) +
      ' <button class="btn btn-skip" style="margin-left:8px;font-size:11px;" onclick="undecide(\'indi\',\'' + esc(xb) + '\')">Undo</button></div>';
  } else if (disp === 'add') {
    actionBar = '<div class="decided d-add">\u2713 Will be added' +
      ' <button class="btn btn-skip" style="margin-left:8px;font-size:11px;" onclick="undecide(\'indi\',\'' + esc(xb) + '\')">Undo</button></div>';
  } else if (disp === 'skip') {
    actionBar = '<div class="decided d-skip">\u2717 Skipped' +
      ' <button class="btn btn-skip" style="margin-left:8px;font-size:11px;" onclick="undecide(\'indi\',\'' + esc(xb) + '\')">Undo</button></div>';
  } else {
    actionBar = '<div class="actions">' +
      '<button class="btn btn-add btn-add-u" onclick="decide(\'indi\',\'' + esc(xb) + '\',\'add\',null)">Add to merged file</button>' +
      '<button class="btn btn-skip btn-skip-u" onclick="decide(\'indi\',\'' + esc(xb) + '\',\'skip\',null)">Skip</button>' +
      searchBtn +
      '<span class="hint"><kbd>a</kbd> add &nbsp; <kbd>s</kbd> skip</span></div>';
  }

  return '<div class="card" style="' + (mergedTo?'border-color:rgba(52,196,106,.3)':disp==='add'?'border-color:rgba(79,142,247,.3)':disp?'opacity:.65':'') + '">' +
    '<div style="padding:12px 16px;border-bottom:1px solid var(--border);">' + info + '</div>' +
    actionBar + renderSearchPanel(xb) + '</div>';
}

/* ─── Unmatched source ───────────────────────────────────────────── */
var _srcSearchCache = {};
var _srcSearchOpen = {};

async function searchSrcMatch(xref_b) {
  _srcSearchOpen[xref_b] = !_srcSearchOpen[xref_b];
  if (_srcSearchOpen[xref_b] && !_srcSearchCache[xref_b]) {
    try {
      var r = await fetch('/api/search_source?xref_b=' + encodeURIComponent(xref_b));
      var data = await r.json();
      _srcSearchCache[xref_b] = data.results || [];
    } catch(_) { _srcSearchCache[xref_b] = []; }
  }
  render();
}

function renderSrcSearchPanel(xref_b) {
  if (!_srcSearchOpen[xref_b]) return '';
  var results = _srcSearchCache[xref_b];
  if (!results) return '<div style="border-top:1px solid var(--border);padding:12px;color:var(--text2);font-size:13px;">Searching\u2026</div>';
  if (!results.length) return '<div style="border-top:1px solid var(--border);padding:12px;color:var(--text2);font-size:13px;">No candidates found in File A.</div>';
  var html = '<div style="border-top:1px solid var(--border);padding:12px 16px;background:rgba(0,0,0,.15);">' +
    '<div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text3);margin-bottom:10px;">Top candidates in File A</div>';
  results.forEach(function(m) {
    var pct = Math.round(m.score * 100);
    var cls = m.score>=.85?'score-hi':m.score>=.65?'score-md':'score-lo';
    html += '<div style="border:1px solid var(--border);border-radius:6px;margin-bottom:10px;overflow:hidden;">' +
      '<div style="padding:10px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;">' +
      '<span class="score ' + cls + '">' + pct + '% match</span>' +
      '<span style="font-size:13px;font-weight:600;">' + esc(m.title_a||m.xref_a) + '</span>' +
      '</div>' +
      '<div style="padding:8px 14px;font-size:12px;color:var(--text2);">' +
      (m.author_a ? '<div>Author: ' + esc(m.author_a) + '</div>' : '') +
      '</div>' +
      '<div class="actions" style="padding:8px 14px;">' +
      '<button class="btn btn-merge" onclick="_mergeSrcFromSearch(\'' + esc(xref_b) + '\',\'' + esc(m.xref_a) + '\')">Merge \u2014 same source</button>' +
      '<button class="btn btn-add" style="margin-left:6px;" onclick="_addSrcFromSearch(\'' + esc(xref_b) + '\')">Add as new source</button>' +
      '</div></div>';
  });
  html += '</div>';
  return html;
}

function _mergeSrcFromSearch(xb, xa) { _srcSearchOpen[xb] = false; decide('source', xb, 'merge', xa); }
function _addSrcFromSearch(xb) { _srcSearchOpen[xb] = false; decide('source', xb, 'add', null); }

function unmatchedSrc(d) {
  var xb = d.xref_b, disp = D.source_disposition[xb], mergedTo = D.source_map[xb];
  var filePill = '<span style="font-size:10px;font-weight:600;letter-spacing:.05em;padding:2px 7px;border-radius:10px;background:rgba(124,95,230,.18);color:#b39dfa;margin-left:8px;">' + esc(DATA.file_b_name) + '</span>';
  var searchBtn = '<button class="btn" style="margin-left:auto;font-size:12px;background:rgba(79,142,247,.18);color:#7eb0ff;border:1px solid rgba(79,142,247,.35);" onclick="searchSrcMatch(\'' + esc(xb) + '\')">' +
    (_srcSearchOpen[xb] ? '\u25b2 Hide matches' : '\ud83d\udd0d Find match in File A') + '</button>';
  var actionBar;
  if (mergedTo) {
    actionBar = '<div class="decided d-merge">\u2713 Merged \u2192 ' + esc(mergedTo) +
      ' <button class="btn btn-skip" style="margin-left:8px;font-size:11px;" onclick="undecide(\'source\',\'' + esc(xb) + '\')">Undo</button></div>';
  } else if (disp === 'add') {
    actionBar = '<div class="decided d-add">\u2713 Will be added' +
      ' <button class="btn btn-skip" style="margin-left:8px;font-size:11px;" onclick="undecide(\'source\',\'' + esc(xb) + '\')">Undo</button></div>';
  } else if (disp === 'skip') {
    actionBar = '<div class="decided d-skip">\u2717 Skipped' +
      ' <button class="btn btn-skip" style="margin-left:8px;font-size:11px;" onclick="undecide(\'source\',\'' + esc(xb) + '\')">Undo</button></div>';
  } else {
    actionBar = '<div class="actions">' +
      '<button class="btn btn-add" onclick="decide(\'source\',\'' + esc(xb) + '\',\'add\',null)">Add</button>' +
      '<button class="btn btn-skip" onclick="decide(\'source\',\'' + esc(xb) + '\',\'skip\',null)">Skip</button>' +
      searchBtn + '</div>';
  }
  return '<div class="card" style="' + (mergedTo?'border-color:rgba(52,196,106,.3)':disp==='add'?'border-color:rgba(79,142,247,.3)':disp?'opacity:.65':'') + '">' +
    '<div style="padding:12px 16px;border-bottom:1px solid var(--border);">' +
    '<div style="font-size:14px;font-weight:600;display:flex;align-items:center;">' + esc(d.title||xb) + filePill + '</div>' +
    (d.author ? '<div style="font-size:12px;color:var(--text2);margin-top:2px;">' + esc(d.author) + '</div>' : '') + '</div>' +
    actionBar + renderSrcSearchPanel(xb) + '</div>';
}

/* ─── Tab renderers ──────────────────────────────────────────────── */
function section(label, count, id) {
  var idAttr = id ? ' id="' + id + '"' : '';
  return '<div' + idAttr + ' style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;' +
    'color:var(--text3);margin:16px 0 8px;scroll-margin-top:60px;">' + label + ' (' + count + ')</div>';
}

/* Sort a match list so undecided items come first */
function sortUndecidedFirst(list, mapObj, dispObj) {
  return list.slice().sort(function(a, b) {
    var da = !!(mapObj[a.xref_b] || dispObj[a.xref_b]);
    var db = !!(mapObj[b.xref_b] || dispObj[b.xref_b]);
    return da - db;  // false(0) < true(1) → undecided first
  });
}

function jumpNav(sections) {
  return '<div style="display:flex;gap:6px;margin-bottom:12px;">' +
    sections.map(function(s) {
      return '<a href="#' + s.id + '" style="font-size:12px;padding:4px 12px;border:1px solid var(--border);' +
        'border-radius:4px;color:var(--text2);text-decoration:none;background:var(--bg2);">' + s.label + ' \u2193</a>';
    }).join('') + '</div>';
}

function renderAuto() {
  var ai = DATA.auto.individuals, as = DATA.auto.sources, af = DATA.auto.families;
  if (!ai.length && !as.length && !af.length)
    return '<div class="empty-state"><div class="icon">&#10003;</div><p>No auto-matches.</p></div>';

  var allDecided = ai.every(function(m){ return D.indi_map[m.xref_b] || D.indi_disposition[m.xref_b]; }) &&
                   as.every(function(m){ return D.source_map[m.xref_b] || D.source_disposition[m.xref_b]; }) &&
                   af.every(function(m){ return D.family_map[m.xref_b] || D.family_disposition[m.xref_b]; });
  var skippedCount = ai.filter(function(m){ return D.indi_disposition[m.xref_b] === 'skip'; }).length +
                     as.filter(function(m){ return D.source_disposition[m.xref_b] === 'skip'; }).length +
                     af.filter(function(m){ return D.family_disposition[m.xref_b] === 'skip'; }).length;

  var banner = allDecided
    ? '<div class="card" style="border-color:rgba(52,196,106,.3);margin-bottom:16px;">' +
      '<div class="actions decided d-merge" style="background:rgba(52,196,106,.06);">' +
      '\u2713 All ' + (ai.length+as.length+af.length) + ' auto-matches decided' +
      (skippedCount ? ' (' + skippedCount + ' skipped)' : '') +
      ' <button class="btn btn-skip" style="margin-left:auto;font-size:11px;" onclick="unapproveAll()">Undo approvals</button></div></div>'
    : '<div class="card" style="margin-bottom:16px;"><div style="padding:14px 16px;">' +
      '<div style="font-size:15px;font-weight:600;">Auto-matched records</div>' +
      '<div style="font-size:12px;color:var(--text2);margin-top:4px;">' +
      ai.length + ' individuals \u00b7 ' + as.length + ' sources \u00b7 ' + af.length + ' families' +
      ' &mdash; confidence above threshold</div></div>' +
      '<div class="actions">' +
      (skippedCount
        ? '<button class="btn btn-approve" onclick="approveRemaining()">\u2713 Approve Remaining</button>' +
          '<button class="btn btn-skip" style="margin-left:6px;font-size:12px;" onclick="approveAll()">Approve All (override skips)</button>'
        : '<button class="btn btn-approve" onclick="approveAll()">\u2713 Approve All</button>') +
      '<span class="hint">or review individually below</span></div></div>';

  var nav = (ai.length && as.length)
    ? jumpNav([{id:'auto-indi',label:'Individuals'},{id:'auto-src',label:'Sources'}])
    : '';

  var html = banner + nav;
  if (ai.length) html += section('Individuals', ai.length, 'auto-indi') + sortUndecidedFirst(ai, D.indi_map, D.indi_disposition).map(indiCard).join('');
  if (as.length) html += section('Sources', as.length, 'auto-src') + sortUndecidedFirst(as, D.source_map, D.source_disposition).map(srcCard).join('');
  return html;
}

function renderCandidates() {
  var ci = DATA.candidates.individuals, cs = DATA.candidates.sources;
  if (!ci.length && !cs.length)
    return '<div class="empty-state"><div class="icon">&#10003;</div><p>No candidate matches to review.</p></div>';

  var nav = (ci.length && cs.length)
    ? jumpNav([{id:'cand-indi',label:'Individuals'},{id:'cand-src',label:'Sources'}])
    : '';

  var html = nav;
  if (ci.length) html += section('Individuals', ci.length, 'cand-indi') + sortUndecidedFirst(ci, D.indi_map, D.indi_disposition).map(indiCard).join('');
  if (cs.length) html += section('Sources', cs.length, 'cand-src') + sortUndecidedFirst(cs, D.source_map, D.source_disposition).map(srcCard).join('');
  return html;
}

function renderUnmatched() {
  var ui = DATA.unmatched.individuals, us = DATA.unmatched.sources, uf = DATA.unmatched.families;
  if (!ui.length && !us.length && !uf.length)
    return '<div class="empty-state"><div class="icon">&#10003;</div><p>No unmatched records from File B.</p></div>';

  var allDecided = ui.every(function(d){return D.indi_disposition[d.xref_b];}) &&
                   us.every(function(d){return D.source_disposition[d.xref_b];}) &&
                   uf.every(function(d){return D.family_disposition[d.xref_b];});

  var bulk = allDecided ? '' :
    '<div class="card" style="margin-bottom:16px;"><div class="actions">' +
    '<button class="btn btn-add" onclick="addAllUnmatched()">+ Add All</button>' +
    '<button class="btn btn-skip" style="margin-left:6px;" onclick="skipAllUnmatched()">Skip All</button>' +
    '<span class="hint">or decide individually</span></div></div>';

  var nav = (ui.length && us.length)
    ? jumpNav([{id:'unmatched-indi',label:'Individuals'},{id:'unmatched-src',label:'Sources'}])
    : '';
  var html = bulk + nav;
  if (ui.length) html += section('Individuals', ui.length, 'unmatched-indi') + ui.map(unmatchedIndi).join('');
  if (us.length) html += section('Sources', us.length, 'unmatched-src') + us.map(unmatchedSrc).join('');
  if (uf.length) {
    html += section('Families', uf.length) + uf.map(function(d) {
      var xb = d.xref_b, disp = D.family_disposition[xb];
      var bar = disp
        ? '<div class="decided d-' + disp + '">\u2713 ' + disp +
          ' <button class="btn btn-skip" style="margin-left:8px;font-size:11px;" onclick="undecide(\'fam\',\'' + esc(xb) + '\')">Undo</button></div>'
        : '<div class="actions"><button class="btn btn-add" onclick="decide(\'fam\',\'' + esc(xb) + '\',\'add\',null)">Add</button>' +
          '<button class="btn btn-skip" onclick="decide(\'fam\',\'' + esc(xb) + '\',\'skip\',null)">Skip</button></div>';
      return '<div class="card"><div style="padding:10px 14px;border-bottom:1px solid var(--border);">Family ' + esc(xb) + '</div>' + bar + '</div>';
    }).join('');
  }
  return html;
}

/* ─── Finish ─────────────────────────────────────────────────────── */
async function showFinish() {
  await doSave();
  var merged = Object.keys(D.indi_map).length + Object.keys(D.source_map).length + Object.keys(D.family_map).length;
  var added  = Object.values(D.indi_disposition).filter(function(v){return v==='add';}).length +
               Object.values(D.source_disposition).filter(function(v){return v==='add';}).length;
  var skipped= Object.values(D.indi_disposition).filter(function(v){return v==='skip';}).length +
               Object.values(D.source_disposition).filter(function(v){return v==='skip';}).length;
  document.getElementById('fs-merged').textContent = merged;
  document.getElementById('fs-added').textContent = added;
  document.getElementById('fs-skipped').textContent = skipped;
  document.getElementById('overlay').classList.add('on');
}

async function finish() {
  await fetch('/api/finish', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(D)
  });
  document.getElementById('overlay').innerHTML =
    '<div class="finish-card"><h2>\u2713 Done</h2><p>Merge is running in your terminal. You can close this window.</p></div>';
}
</script>
</body>
</html>"""


def _render_html(data_json: str, session_path: str) -> str:
    """Substitute the two placeholders and return the final HTML."""
    return (_HTML_TEMPLATE
            .replace('%%DATA_JSON%%', data_json)
            .replace('%%SESSION_PATH%%', json.dumps(session_path)))


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

class _ReviewHandler(BaseHTTPRequestHandler):
    """Handles review UI requests. Class-level attributes shared across threads."""

    review_data: dict = {}
    decisions: dict = {}
    session: 'SessionState | None' = None
    session_path: str = ''
    done_event: threading.Event = threading.Event()
    final_decisions: dict = {}
    file_a: 'GedcomFile | None' = None
    file_b: 'GedcomFile | None' = None
    _surname_index_a: dict | None = None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ('/', '/index.html'):
            self._html()
        elif path == '/api/state':
            self._json({'decisions': self.__class__.decisions})
        elif path == '/api/search_match':
            from urllib.parse import parse_qs
            qs = parse_qs(parsed.query)
            xref_b = (qs.get('xref_b') or [''])[0]
            self._search_match(xref_b)
        elif path == '/api/search_source':
            from urllib.parse import parse_qs
            qs = parse_qs(parsed.query)
            xref_b = (qs.get('xref_b') or [''])[0]
            self._search_source(xref_b)
        else:
            self.send_error(404)

    def _search_match(self, xref_b: str):
        cls = self.__class__
        file_a, file_b = cls.file_a, cls.file_b
        if not file_a or not file_b or not xref_b:
            self._json({'results': []})
            return

        # Build surname index once and cache it
        if cls._surname_index_a is None:
            cls._surname_index_a = _build_surname_index(file_a)

        ind_b = file_b.individuals.get(xref_b)
        if not ind_b:
            self._json({'results': []})
            return

        # Use current merge decisions as family context
        matched_b_to_a: dict[str, str] = cls.decisions.get('indi_map', {})

        all_xrefs_a = list(file_a.individuals.keys())

        # Always search all of File A for manual searches — exhaustive is better
        # than fast when the user is explicitly looking for a match.
        search_xrefs = set(all_xrefs_a)

        scored: list[tuple[float, str, dict]] = []
        for xref_a in search_xrefs:
            ind_a = file_a.individuals[xref_a]
            score, comps = _score_pair(ind_a, ind_b, matched_b_to_a, file_a, file_b)
            if score > 0.0:
                scored.append((score, xref_a, comps))

        scored.sort(key=lambda t: t[0], reverse=True)
        top3 = scored[:3]

        results = []
        for score, xref_a, comps in top3:
            ind_a = file_a.individuals[xref_a]
            results.append({
                'xref_a': xref_a,
                'score': score,
                'score_components': comps,
                'detail_a': _indi_detail(ind_a, file_a),
                'detail_b': _indi_detail(ind_b, file_b),
            })

        self._json({'results': results})

    def _search_source(self, xref_b: str):
        cls = self.__class__
        file_a, file_b = cls.file_a, cls.file_b
        if not file_a or not file_b or not xref_b:
            self._json({'results': []})
            return

        src_b = file_b.sources.get(xref_b)
        if not src_b:
            self._json({'results': []})
            return

        scored: list[tuple[float, str]] = []
        for xref_a, src_a in file_a.sources.items():
            score = _score_source_pair(src_a, src_b)
            if score > 0.0:
                scored.append((score, xref_a))

        scored.sort(key=lambda t: t[0], reverse=True)
        top3 = scored[:3]

        results = []
        for score, xref_a in top3:
            src_a = file_a.sources[xref_a]
            results.append({
                'xref_a': xref_a,
                'score': score,
                'title_a': src_a.title or '',
                'author_a': src_a.author or '',
                'title_b': src_b.title or '',
                'author_b': src_b.author or '',
            })

        self._json({'results': results})

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if path == '/api/save':
            self._apply(body)
            self._save_session()
            self._json({'ok': True})
        elif path == '/api/finish':
            self._apply(body)
            self._save_session()
            self.__class__.final_decisions = dict(body)
            self._json({'ok': True})
            self.__class__.done_event.set()
        else:
            self.send_error(404)

    def _apply(self, body: dict):
        self.__class__.decisions.update(body)
        s = self.__class__.session
        if s:
            s.source_map = body.get('source_map', {})
            s.indi_map = body.get('indi_map', {})
            s.family_map = body.get('family_map', {})
            s.source_disposition = body.get('source_disposition', {})
            s.indi_disposition = body.get('indi_disposition', {})
            s.family_disposition = body.get('family_disposition', {})
            s.auto_approved = body.get('auto_approved', False)

    def _save_session(self):
        s = self.__class__.session
        sp = self.__class__.session_path
        if s and sp:
            try:
                save_session(sp, s)
            except Exception as e:
                print(f'[review_html] Warning: could not save session: {e}')

    def _html(self):
        data_json = json.dumps(self.__class__.review_data, ensure_ascii=False)
        sp = self.__class__.session_path
        body = _render_html(data_json, sp).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # suppress access logs


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_web_review(
    source_result: SourceMatchResult,
    indi_result: IndividualMatchResult,
    fam_result: FamilyMatchResult,
    file_a: GedcomFile,
    file_b: GedcomFile,
    session: SessionState | None = None,
    session_path: str = '',
    port: int = 8765,
) -> MergeDecisions:
    """
    Launch the web review server, open a browser, and block until the user
    clicks "Finish Review". Returns a MergeDecisions with all decisions.

    If session is provided, pre-populates decisions from it and saves after
    every decision (resume support).
    """
    review_data = _build_review_data(
        source_result, indi_result, fam_result, file_a, file_b
    )

    # Pre-populate from session (for --resume)
    initial: dict = {
        'source_map': {}, 'indi_map': {}, 'family_map': {},
        'source_disposition': {}, 'indi_disposition': {}, 'family_disposition': {},
        'auto_approved': False,
    }
    if session:
        initial['source_map'] = dict(session.source_map)
        initial['indi_map'] = dict(session.indi_map)
        initial['family_map'] = dict(session.family_map)
        initial['source_disposition'] = dict(session.source_disposition)
        initial['indi_disposition'] = dict(session.indi_disposition)
        initial['family_disposition'] = dict(session.family_disposition)
        initial['auto_approved'] = session.auto_approved

    done_event = threading.Event()
    _ReviewHandler.review_data = review_data
    _ReviewHandler.decisions = initial
    _ReviewHandler.session = session
    _ReviewHandler.session_path = session_path
    _ReviewHandler.done_event = done_event
    _ReviewHandler.final_decisions = {}
    _ReviewHandler.file_a = file_a
    _ReviewHandler.file_b = file_b
    _ReviewHandler._surname_index_a = None  # built lazily on first search

    server = HTTPServer(('127.0.0.1', port), _ReviewHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    url = f'http://localhost:{port}/'
    print(f'\n  Opening merge review UI at {url}')
    print(f'  Progress auto-saves to: {session_path or "(no session file)"}')
    print(f'  Close your browser or press Ctrl+C to pause and save.\n')
    webbrowser.open(url)

    try:
        done_event.wait()
    except KeyboardInterrupt:
        print('\nReview paused. Progress saved to session file.')
    finally:
        server.shutdown()

    fd = _ReviewHandler.final_decisions or _ReviewHandler.decisions
    d = MergeDecisions()
    d.source_map = fd.get('source_map', {})
    d.indi_map = fd.get('indi_map', {})
    d.family_map = fd.get('family_map', {})
    d.source_disposition = fd.get('source_disposition', {})
    d.indi_disposition = fd.get('indi_disposition', {})
    d.family_disposition = fd.get('family_disposition', {})
    return d
