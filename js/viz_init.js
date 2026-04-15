// Initialisation, root-switching, and browser event listener wiring.

// Pan / zoom state (module-level so applyTransform can read them)
let tx = 0, ty = 0, scale = 1;
let didDrag = false;

// Build Ahnentafel map {key: xref} from PARENTS starting at rootXref
function buildAhnentafel(rootXref) {
  const result = {};
  const queue = [[rootXref, 1]];
  while (queue.length) {
    const [xref, k] = queue.shift();
    if (!xref || !PARENTS[xref]) continue;
    result[k] = xref;
    const [fatherXref, motherXref] = PARENTS[xref];
    if (fatherXref) queue.push([fatherXref, 2 * k]);
    if (motherXref) queue.push([motherXref, 2 * k + 1]);
  }
  return result;
}

function changeRoot(xref) {
  if (!xref || !PEOPLE[xref]) return;
  currentTree = buildAhnentafel(xref);
  visibleKeys.clear();
  _posCache.clear();
  _relPosCache.clear();
  expandedRelatives.clear();
  expandedRelatives.add(1);
  expandedChildrenOf.clear();
  for (let g = 0; g <= 2; g++) {
    const start = Math.pow(2, g);
    const end   = Math.pow(2, g + 1);
    for (let k = start; k < end; k++) {
      if (k in currentTree) visibleKeys.add(k);
    }
  }
  render();
  fitAndCenter();
  showDetail(xref);
}

document.getElementById('detail-close').addEventListener('click', closeDetail);
document.getElementById('detail-set-root-btn').addEventListener('click', () => {
  if (_openDetailKey) changeRoot(_openDetailKey);
});

document.getElementById('home-btn').addEventListener('click', () => {
  changeRoot(ROOT_XREF);
});

function init() {
  // Show generations 0-2 initially
  for (let g = 0; g <= 2; g++) {
    const start = Math.pow(2, g);
    const end   = Math.pow(2, g + 1);
    for (let k = start; k < end; k++) {
      if (k in currentTree) visibleKeys.add(k);
    }
  }

  const vp   = document.getElementById('viewport');
  const hdr  = document.querySelector('header');
  const topH = hdr.offsetHeight;
  vp.style.height = (window.innerHeight - topH) + 'px';
  document.documentElement.style.setProperty('--header-h', topH + 'px');

  render();
  fitAndCenter();
  if (new URLSearchParams(window.location.search).get('open') === '1') showDetail(currentTree[1]);
}

// ---- Pinch-to-zoom + two-finger pan (trackpad wheel events) ----
document.getElementById('tree').addEventListener('wheel', (e) => {
  e.preventDefault();
  const svg  = document.getElementById('tree');
  const rect = svg.getBoundingClientRect();
  if (e.ctrlKey) {
    // Pinch gesture: zoom towards cursor
    const factor   = 1 - e.deltaY * 0.005;
    const newScale = Math.max(0.08, Math.min(6, scale * factor));
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    tx = mx - (mx - tx) * (newScale / scale);
    ty = my - (my - ty) * (newScale / scale);
    scale = newScale;
  } else {
    // Two-finger scroll: pan
    tx -= e.deltaX;
    ty -= e.deltaY;
  }
  applyTransform();
}, { passive: false });

// ---- Mouse drag pan ----
let dragging = false, dragX0 = 0, dragY0 = 0, tx0 = 0, ty0 = 0;

document.getElementById('tree').addEventListener('mousedown', (e) => {
  if (e.button !== 0) return;
  dragging = true; didDrag = false;
  dragX0 = e.clientX; dragY0 = e.clientY; tx0 = tx; ty0 = ty;
  document.getElementById('viewport').classList.add('dragging');
});
window.addEventListener('mousemove', (e) => {
  if (!dragging) return;
  if (Math.hypot(e.clientX - dragX0, e.clientY - dragY0) > 4) didDrag = true;
  tx = tx0 + e.clientX - dragX0;
  ty = ty0 + e.clientY - dragY0;
  applyTransform();
});
window.addEventListener('mouseup', () => {
  dragging = false;
  document.getElementById('viewport').classList.remove('dragging');
});

window.addEventListener('load', init);
window.addEventListener('resize', () => {
  const vp   = document.getElementById('viewport');
  const hdr  = document.querySelector('header');
  vp.style.height = (window.innerHeight - hdr.offsetHeight) + 'px';
  if (_openDetailKey !== null) vp.style.marginRight = '480px';
});
