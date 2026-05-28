// Compute the kinship label between two people in the JS graph.
// Reads (via injected ctx, falling back to globals): PEOPLE, PARENTS, CHILDREN, RELATIVES, FAMILIES.

function gendered(sex, mLabel, fLabel, neutralLabel) {
  if (sex === 'M') return mLabel;
  if (sex === 'F') return fLabel;
  return neutralLabel;
}

function greatPrefix(greatCount) {
  if (greatCount <= 0) return '';
  if (greatCount === 1) return 'Great-';
  return `${greatCount}× Great-`;
}

const ORDINALS = ['1st','2nd','3rd','4th','5th','6th','7th','8th','9th','10th','11th'];
function ordinal(n) { return ORDINALS[n - 1] || `${n}th`; }

// Determine whether a sibling/cousin-line path represents a full relationship.
// Full ↔ both legs descend through the same parent-couple at the MRCA generation.
// Half ↔ only the MRCA is shared at that generation (other parents differ or unknown).
function isFullRelationship(path, ctx) {
  if (path.a === 0 || path.b === 0) return true; // direct lineal — half- doesn't apply
  const otherParentInFam = (childXref, mrca) => {
    if (!childXref) return null;
    const [father, mother] = ctx.PARENTS[childXref] || [null, null];
    if (father === mrca) return mother;
    if (mother === mrca) return father;
    return null;
  };
  const opViewer = otherParentInFam(path.viewerLeg, path.mrca);
  const opOther  = otherParentInFam(path.otherLeg, path.mrca);
  return opViewer !== null && opViewer === opOther;
}

// BFS up via PARENTS. Returns Map<ancestorXref, Array<{depth, viaParentXref}>>.
// viaParentXref = the immediate child of the ancestor on the path back toward `start`.
// Includes start itself at depth 0 (viaParentXref=null).
function bfsUp(start, parents, maxDepth) {
  const result = new Map();
  result.set(start, [{ depth: 0, viaParentXref: null }]);
  const queue = [{ xref: start, depth: 0 }];
  while (queue.length) {
    const { xref, depth } = queue.shift();
    if (depth >= maxDepth) continue;
    const [father, mother] = parents[xref] || [null, null];
    for (const parentXref of [father, mother]) {
      if (!parentXref) continue;
      const newPath = { depth: depth + 1, viaParentXref: xref };
      const existing = result.get(parentXref);
      if (existing) existing.push(newPath);
      else result.set(parentXref, [newPath]);
      queue.push({ xref: parentXref, depth: depth + 1 });
    }
  }
  return result;
}

// BFS down via CHILDREN. Returns Map<descendantXref, Array<{depth, viaChildXref}>>.
// viaChildXref = the MRCA-side direct child on the path toward descendant.
// Includes start itself at depth 0 (viaChildXref=null).
function bfsDown(start, children, maxDepth) {
  const result = new Map();
  result.set(start, [{ depth: 0, viaChildXref: null }]);
  const queue = [{ xref: start, depth: 0, viaChild: null }];
  while (queue.length) {
    const { xref, depth, viaChild } = queue.shift();
    if (depth >= maxDepth) continue;
    for (const childXref of children[xref] || []) {
      const childViaChild = depth === 0 ? childXref : viaChild;
      const newPath = { depth: depth + 1, viaChildXref: childViaChild };
      const existing = result.get(childXref);
      if (existing) existing.push(newPath);
      else result.set(childXref, [newPath]);
      queue.push({ xref: childXref, depth: depth + 1, viaChild: childViaChild });
    }
  }
  return result;
}

function formatBloodLabel(a, b, otherSex, isHalf) {
  const halfPrefix = isHalf ? 'Half-' : '';
  if (a === 0 && b === 0) return 'Self';

  // Direct ancestors (b=0)
  if (b === 0 && a >= 1) {
    if (a === 1) return gendered(otherSex, 'Father', 'Mother', 'Parent');
    if (a === 2) return gendered(otherSex, 'Grandfather', 'Grandmother', 'Grandparent');
    return greatPrefix(a - 2) + gendered(otherSex, 'Grandfather', 'Grandmother', 'Grandparent');
  }

  // Direct descendants (a=0)
  if (a === 0 && b >= 1) {
    if (b === 1) return gendered(otherSex, 'Son', 'Daughter', 'Child');
    if (b === 2) return gendered(otherSex, 'Grandson', 'Granddaughter', 'Grandchild');
    return greatPrefix(b - 2) + gendered(otherSex, 'Grandson', 'Granddaughter', 'Grandchild');
  }

  // Sibling line (a=1, b=1)
  if (a === 1 && b === 1) {
    return halfPrefix + gendered(otherSex, 'Brother', 'Sister', 'Sibling');
  }

  // Aunt/Uncle line (a≥2, b=1). FamilySearch convention: Uncle (a=2),
  // Granduncle (a=3, sibling of grandparent), Great-Granduncle (a=4),
  // N× Great-Granduncle (a≥5). Mirrors the sibling's depth, not the nibling's.
  if (b === 1 && a >= 2) {
    if (a === 2) return halfPrefix + gendered(otherSex, 'Uncle', 'Aunt', 'Aunt or Uncle');
    const term = gendered(otherSex, 'Granduncle', 'Grandaunt', 'Grandaunt or Granduncle');
    return halfPrefix + greatPrefix(a - 3) + term;
  }

  // Niece/Nephew line (a=1, b≥2). Mirror of aunt/uncle: Niece/Nephew (b=2),
  // Grandniece/Grandnephew (b=3), Great-Grandniece (b=4), N× Great-Grandniece (b≥5).
  if (a === 1 && b >= 2) {
    if (b === 2) return halfPrefix + gendered(otherSex, 'Nephew', 'Niece', 'Niece or Nephew');
    const term = gendered(otherSex, 'Grandnephew', 'Grandniece', 'Grandniece or Grandnephew');
    return halfPrefix + greatPrefix(b - 3) + term;
  }

  // Cousins (a≥2 AND b≥2)
  if (a >= 2 && b >= 2) {
    const cousinNum = Math.min(a, b) - 1;
    const removed = Math.abs(a - b);
    const removedPart = removed > 0 ? ` ${removed}× Removed` : '';
    return halfPrefix + ordinal(cousinNum) + ' Cousin' + removedPart;
  }

  return null;
}

// Find all blood paths from viewer to other.
// Each path: { a, b, mrca, viewerLeg, otherLeg }
//   viewerLeg = MRCA's child on viewer's path (=== viewer if a===1; null if a===0)
//   otherLeg  = MRCA's child on other's path  (=== other  if b===1; null if b===0)
function findBloodPaths(viewer, other, ctx) {
  const ancestors = bfsUp(viewer, ctx.PARENTS, Infinity);
  const paths = [];
  for (const [ancestorXref, viewerPaths] of ancestors) {
    const descendants = bfsDown(ancestorXref, ctx.CHILDREN, Infinity);
    const otherPaths = descendants.get(other);
    if (!otherPaths) continue;
    for (const vp of viewerPaths) {
      for (const op of otherPaths) {
        paths.push({
          a: vp.depth,
          b: op.depth,
          mrca: ancestorXref,
          viewerLeg: vp.viaParentXref,
          otherLeg: op.viaChildXref,
        });
      }
    }
  }
  return paths;
}

// Pick the closest path: minimize a+b, tiebreak on smaller min(a,b).
function pickClosestPath(paths) {
  let best = null;
  for (const p of paths) {
    if (!best) { best = p; continue; }
    const sumP = p.a + p.b, sumB = best.a + best.b;
    if (sumP < sumB) { best = p; continue; }
    if (sumP === sumB && Math.min(p.a, p.b) < Math.min(best.a, best.b)) best = p;
  }
  return best;
}

// Lazy index of godparent links from PEOPLE[x].events[*].asso on BAPM/CHR.
// byChild: Map<childXref, Array<{xref: godparentXref, rela}>>
// byParent: Map<godparentXref, Array<{xref: childXref, rela}>>
function getGodparentIndex(ctx) {
  if (ctx._godparentIndex) return ctx._godparentIndex;
  const byChild = new Map();
  const byParent = new Map();
  for (const [xref, info] of Object.entries(ctx.PEOPLE || {})) {
    for (const ev of (info && info.events) || []) {
      if (ev.tag !== 'BAPM' && ev.tag !== 'CHR') continue;
      for (const a of ev.asso || []) {
        if (!a || !a.xref) continue;
        const entry = { xref: a.xref, rela: a.rela };
        if (!byChild.has(xref)) byChild.set(xref, []);
        byChild.get(xref).push(entry);
        if (!byParent.has(a.xref)) byParent.set(a.xref, []);
        byParent.get(a.xref).push({ xref, rela: a.rela });
      }
    }
  }
  ctx._godparentIndex = { byChild, byParent };
  return ctx._godparentIndex;
}

function _godparentLabel(rela, otherSex) {
  // `rela` is the RELA text on the ASSO record — "Godfather"/"Godmother"/"Godparent".
  // Prefer it over `otherSex` since it's the most specific signal.
  if (rela === 'Godfather') return 'Godfather';
  if (rela === 'Godmother') return 'Godmother';
  return gendered(otherSex, 'Godfather', 'Godmother', 'Godparent');
}

function _godchildLabel(otherSex) {
  return gendered(otherSex, 'Godson', 'Goddaughter', 'Godchild');
}

// Returns {label, edges: 1} if there's a direct godparent or godchild relation
// between viewer and other, else null.
function findGodparentAtomic(viewer, other, ctx) {
  const idx = getGodparentIndex(ctx);
  const otherSex = (ctx.PEOPLE[other] || {}).sex || null;

  // other is viewer's godparent
  for (const entry of idx.byChild.get(viewer) || []) {
    if (entry.xref === other) {
      return { label: _godparentLabel(entry.rela, otherSex), edges: 1 };
    }
  }
  // viewer is other's godparent → other is viewer's godchild
  for (const entry of idx.byChild.get(other) || []) {
    if (entry.xref === viewer) {
      return { label: _godchildLabel(otherSex), edges: 1 };
    }
  }
  return null;
}

function getSpousesOf(xref, ctx) {
  const rel = ctx.RELATIVES[xref];
  if (rel && Array.isArray(rel.spouses)) return rel.spouses;
  // Fallback: scan FAMILIES for the partner of xref
  const spouses = [];
  for (const fam of Object.values(ctx.FAMILIES || {})) {
    if (fam.husb === xref && fam.wife) spouses.push(fam.wife);
    if (fam.wife === xref && fam.husb) spouses.push(fam.husb);
  }
  return spouses;
}

function _findSpouseFamily(a, b, ctx) {
  for (const fam of Object.values(ctx.FAMILIES || {})) {
    if ((fam.husb === a && fam.wife === b) || (fam.husb === b && fam.wife === a)) return fam;
  }
  return null;
}

function _isDivorced(a, b, ctx) {
  const fam = _findSpouseFamily(a, b, ctx);
  return !!(fam && fam.divorced);
}

function _spouseVerb(otherSex, divorced) {
  const verb = gendered(otherSex, 'Husband', 'Wife', 'Spouse');
  return divorced ? `Ex-${verb}` : verb;
}

function _findChildFamily(parentXref, childXref, ctx) {
  for (const fam of Object.values(ctx.FAMILIES || {})) {
    if ((fam.husb === parentXref || fam.wife === parentXref)
        && (fam.chil || []).includes(childXref)) return fam;
  }
  return null;
}

// True iff we have positive date evidence that `spouse` and `child` never overlapped
// as a real step-relation through their shared person `bioParent`. Either:
//   (1) spouse↔bioParent marriage predates bioParent's marriage that produced child, or
//   (2) spouse died before child was born.
// Missing dates ⇒ false (keep the existing "Step-" label).
function _isFormerOrPredeceasedStep(spouse, bioParent, child, ctx) {
  const stepFam  = _findSpouseFamily(spouse, bioParent, ctx);
  const childFam = _findChildFamily(bioParent, child, ctx);
  if (stepFam && childFam
      && stepFam.marr_year != null && childFam.marr_year != null
      && stepFam.marr_year < childFam.marr_year) return true;

  const spouseDeath = (ctx.PEOPLE[spouse] || {}).death_year;
  const childBirth  = (ctx.PEOPLE[child]  || {}).birth_year;
  if (spouseDeath != null && childBirth != null && spouseDeath < childBirth) return true;

  return false;
}

// Returns {label, edges} for an atomic affinity (no "of" composition) between viewer and other.
// Edges counts graph hops on the kinship graph (parent/child/spouse).
function findAtomicAffinity(viewer, other, ctx) {
  const viewerSpouses = getSpousesOf(viewer, ctx);
  const viewerParents = (ctx.PARENTS[viewer] || [null, null]).filter(Boolean);
  const otherSex = (ctx.PEOPLE[other] || {}).sex || null;

  // Tier 1: spouse of viewer (1 edge)
  if (viewerSpouses.includes(other)) {
    return { label: _spouseVerb(otherSex, _isDivorced(viewer, other, ctx)), edges: 1 };
  }

  // Tier 2: step-parent (up + across, 2 edges)
  for (const par of viewerParents) {
    if (getSpousesOf(par, ctx).includes(other) && !viewerParents.includes(other)) {
      if (_isFormerOrPredeceasedStep(other, par, viewer, ctx)) {
        const parSex     = (ctx.PEOPLE[par]   || {}).sex || null;
        const spouseVerb = _spouseVerb(otherSex, _isDivorced(other, par, ctx));
        const parLabel   = gendered(parSex,   'Father', 'Mother', 'Parent');
        return { label: `${spouseVerb} of ${parLabel}`, edges: 2 };
      }
      return { label: gendered(otherSex, 'Step-Father', 'Step-Mother', 'Step-Parent'), edges: 2 };
    }
  }

  // Tier 2: step-child (across + down, 2 edges)
  const viewerChildren = ctx.CHILDREN[viewer] || [];
  for (const sp of viewerSpouses) {
    const spChildren = ctx.CHILDREN[sp] || [];
    if (spChildren.includes(other) && !viewerChildren.includes(other)) {
      if (_isFormerOrPredeceasedStep(viewer, sp, other, ctx)) {
        const spSex      = (ctx.PEOPLE[sp]    || {}).sex || null;
        const childLabel = gendered(otherSex, 'Son', 'Daughter', 'Child');
        const spouseVerb = _spouseVerb(spSex, _isDivorced(viewer, sp, ctx));
        return { label: `${childLabel} of ${spouseVerb}`, edges: 2 };
      }
      return { label: gendered(otherSex, 'Step-Son', 'Step-Daughter', 'Step-Child'), edges: 2 };
    }
  }

  // Tier 2: step-sibling (up + across + down, 3 edges)
  for (const par of viewerParents) {
    for (const stepPar of getSpousesOf(par, ctx)) {
      if (viewerParents.includes(stepPar)) continue;
      const stepParChildren = ctx.CHILDREN[stepPar] || [];
      if (stepParChildren.includes(other)) {
        const otherParents = (ctx.PARENTS[other] || [null, null]).filter(Boolean);
        const sharesBioParent = otherParents.some(p => viewerParents.includes(p));
        if (!sharesBioParent) {
          return { label: gendered(otherSex, 'Step-Brother', 'Step-Sister', 'Step-Sibling'), edges: 3 };
        }
      }
    }
  }

  // Tier 3a: parent-in-law (across + up, 2 edges)
  for (const sp of viewerSpouses) {
    const spParents = ctx.PARENTS[sp] || [null, null];
    if (spParents.includes(other)) {
      return { label: gendered(otherSex, 'Father-in-law', 'Mother-in-law', 'Parent-in-law'), edges: 2 };
    }
  }

  // Tier 3b: sibling-in-law via spouse's sibling (across + up + down, 3 edges)
  for (const sp of viewerSpouses) {
    const spParents = ctx.PARENTS[sp] || [null, null];
    for (const p of spParents) {
      if (!p) continue;
      const siblings = (ctx.CHILDREN[p] || []).filter(c => c !== sp);
      if (siblings.includes(other)) {
        return { label: gendered(otherSex, 'Brother-in-law', 'Sister-in-law', 'Sibling-in-law'), edges: 3 };
      }
    }
  }

  // Tier 3c: sibling-in-law via sibling's spouse (up + down + across, 3 edges)
  for (const par of viewerParents) {
    for (const sib of (ctx.CHILDREN[par] || [])) {
      if (sib === viewer) continue;
      if (getSpousesOf(sib, ctx).includes(other)) {
        return { label: gendered(otherSex, 'Brother-in-law', 'Sister-in-law', 'Sibling-in-law'), edges: 3 };
      }
    }
  }

  // Tier 3d: child-in-law (down + across, 2 edges)
  for (const child of viewerChildren) {
    if (getSpousesOf(child, ctx).includes(other)) {
      return { label: gendered(otherSex, 'Son-in-law', 'Daughter-in-law', 'Child-in-law'), edges: 2 };
    }
  }

  // Tier 5: godparent / godchild (1 edge). Last so that any kinship affinity takes
  // precedence — the dual-relationship combiner in computeRelationship re-adds
  // godparent on top of kin when both apply.
  const gp = findGodparentAtomic(viewer, other, ctx);
  if (gp) return gp;

  return null;
}

// All blood relatives of `viewer`, keyed by xref. Value is the closest path (smallest a+b).
// Lazy-cached on ctx._bloodCache to avoid re-running BFS on every recursive `_bestRel` call.
function findAllBloodRelatives(viewer, ctx) {
  if (!ctx._bloodCache) ctx._bloodCache = new Map();
  const cached = ctx._bloodCache.get(viewer);
  if (cached) return cached;
  const result = new Map();
  const ancestors = bfsUp(viewer, ctx.PARENTS, Infinity);
  for (const [ancestorXref, viewerPaths] of ancestors) {
    const descendants = bfsDown(ancestorXref, ctx.CHILDREN, Infinity);
    for (const [descXref, descPaths] of descendants) {
      if (descXref === viewer) continue;
      for (const vp of viewerPaths) {
        for (const dp of descPaths) {
          const candidate = {
            a: vp.depth, b: dp.depth,
            mrca: ancestorXref,
            viewerLeg: vp.viaParentXref, otherLeg: dp.viaChildXref,
          };
          const existing = result.get(descXref);
          if (!existing || candidate.a + candidate.b < existing.a + existing.b) {
            result.set(descXref, candidate);
          }
        }
      }
    }
  }
  ctx._bloodCache.set(viewer, result);
  return result;
}

// Cost-comparison: prefer fewer edges; tiebreak prefers fewer "of" connectors (more atomic).
function _betterCand(a, b) {
  if (!a) return b;
  if (!b) return a;
  if (a.edges !== b.edges) return a.edges < b.edges ? a : b;
  if (a.ofs !== b.ofs) return a.ofs < b.ofs ? a : b;
  // Tiebreak: prefer splits that push more weight onto the blood-relative on the LEFT
  // of "of" — i.e., describe via the closest blood relative whose path covers most of
  // the distance. E.g., "Husband of Cousin" (left=4) beats "Son-in-law of Aunt" (left=3).
  const aLeft = a.leftEdges || 0;
  const bLeft = b.leftEdges || 0;
  if (aLeft !== bLeft) return aLeft > bLeft ? a : b;
  return a;
}

// Recursive best-relationship search.
// Returns { label, edges, ofs } or null.
// `seen` carries the chain of viewers already used so we don't revisit them.
// `depthLeft` caps how many "of" compositions we'll build.
function _bestRel(viewer, other, ctx, seen, depthLeft) {
  if (seen.has(other)) return null;

  let best = null;

  // Direct blood — use cached findAllBloodRelatives instead of recomputing findBloodPaths.
  if (viewer !== other) {
    const bloodRels = findAllBloodRelatives(viewer, ctx);
    const path = bloodRels.get(other);
    if (path) {
      const otherSex = (ctx.PEOPLE[other] || {}).sex || null;
      const isHalf = !isFullRelationship(path, ctx);
      const label = formatBloodLabel(path.a, path.b, otherSex, isHalf);
      if (label) best = _betterCand(best, { label, edges: path.a + path.b, ofs: 0 });
    }
  }

  // Atomic affinity
  const atomic = findAtomicAffinity(viewer, other, ctx);
  if (atomic) best = _betterCand(best, { label: atomic.label, edges: atomic.edges, ofs: 0 });

  if (depthLeft <= 0) return best;

  const newSeen = new Set(seen);
  newSeen.add(viewer);

  // Split via blood-relative intermediates.
  // For each Z (blood relative of viewer), check only atomic affinity Z→other.
  // We deliberately skip the expensive findAllBloodRelatives(Z) BFS that a full
  // recursive _bestRel(Z, other) would do — iterating that over thousands of Z's
  // freezes the page on real trees, and any composed "<blood-Z-O> of <kin-V-Z>"
  // label would be dominated by a direct V→O blood label that the top of
  // computeRelationship would have already returned.
  const bloodRels = findAllBloodRelatives(viewer, ctx);
  for (const [zXref, path] of bloodRels) {
    if (zXref === other || newSeen.has(zXref)) continue;
    const leftEdges = path.a + path.b;
    if (best && leftEdges >= best.edges) continue;
    const subAtomic = findAtomicAffinity(zXref, other, ctx);
    if (!subAtomic) continue;
    const zSex = (ctx.PEOPLE[zXref] || {}).sex || null;
    const zIsHalf = !isFullRelationship(path, ctx);
    const leftLabel = formatBloodLabel(path.a, path.b, zSex, zIsHalf);
    if (!leftLabel) continue;
    const cand = {
      label: `${subAtomic.label} of ${leftLabel}`,
      edges: leftEdges + subAtomic.edges,
      ofs: 1,
      leftEdges,
    };
    best = _betterCand(best, cand);
  }

  // Split via spouse of viewer
  for (const sp of getSpousesOf(viewer, ctx)) {
    if (sp === other || newSeen.has(sp)) continue;
    if (best && 1 >= best.edges) continue;
    const sub = _bestRel(sp, other, ctx, newSeen, depthLeft - 1);
    if (!sub) continue;
    const spouseWord = _isDivorced(viewer, sp, ctx) ? 'Ex-Spouse' : 'Spouse';
    const cand = {
      label: `${sub.label} of ${spouseWord}`,
      edges: 1 + sub.edges,
      ofs: sub.ofs + 1,
      leftEdges: 1,
    };
    best = _betterCand(best, cand);
  }

  return best;
}

// Depth = how many "of" compositions we'll build. 1 covers all current label cases
// ("Father-in-law of Cousin", "Godmother of Cousin", "Wife of Cousin", etc.). Higher
// values blow up combinatorially on real trees (O(B^depth) where B = blood relatives).
const _MAX_REL_DEPTH = 1;

function findAffinityLabel(viewer, other, ctx) {
  const viewerSpouses = getSpousesOf(viewer, ctx);
  const viewerParents = (ctx.PARENTS[viewer] || [null, null]).filter(Boolean);

  // ── Tier 1: spouse of viewer ─────────────────────────────────────
  if (viewerSpouses.includes(other)) {
    const sex = (ctx.PEOPLE[other] || {}).sex || null;
    return _spouseVerb(sex, _isDivorced(viewer, other, ctx));
  }

  // ── Tier 2: step relationships ───────────────────────────────────
  // Step-parent: spouse of viewer's bio parent who is NOT viewer's other bio parent
  for (const par of viewerParents) {
    const parentSpouses = getSpousesOf(par, ctx);
    if (parentSpouses.includes(other) && !viewerParents.includes(other)) {
      const sex = (ctx.PEOPLE[other] || {}).sex || null;
      if (_isFormerOrPredeceasedStep(other, par, viewer, ctx)) {
        const parSex     = (ctx.PEOPLE[par] || {}).sex || null;
        const spouseVerb = _spouseVerb(sex, _isDivorced(other, par, ctx));
        const parLabel   = gendered(parSex, 'Father', 'Mother', 'Parent');
        return `${spouseVerb} of ${parLabel}`;
      }
      return gendered(sex, 'Step-Father', 'Step-Mother', 'Step-Parent');
    }
  }

  // Step-child: child of viewer's spouse who is NOT viewer's bio child
  const viewerChildren = ctx.CHILDREN[viewer] || [];
  for (const sp of viewerSpouses) {
    const spChildren = ctx.CHILDREN[sp] || [];
    if (spChildren.includes(other) && !viewerChildren.includes(other)) {
      const sex = (ctx.PEOPLE[other] || {}).sex || null;
      if (_isFormerOrPredeceasedStep(viewer, sp, other, ctx)) {
        const spSex      = (ctx.PEOPLE[sp] || {}).sex || null;
        const childLabel = gendered(sex,   'Son', 'Daughter', 'Child');
        const spouseVerb = _spouseVerb(spSex, _isDivorced(viewer, sp, ctx));
        return `${childLabel} of ${spouseVerb}`;
      }
      return gendered(sex, 'Step-Son', 'Step-Daughter', 'Step-Child');
    }
  }

  // Step-sibling: child of viewer's step-parent with no shared bio parent
  for (const par of viewerParents) {
    for (const stepPar of getSpousesOf(par, ctx)) {
      if (viewerParents.includes(stepPar)) continue; // bio parent, not step
      const stepParChildren = ctx.CHILDREN[stepPar] || [];
      if (stepParChildren.includes(other)) {
        const otherParents = (ctx.PARENTS[other] || [null, null]).filter(Boolean);
        const sharesBioParent = otherParents.some(p => viewerParents.includes(p));
        if (!sharesBioParent) {
          const sex = (ctx.PEOPLE[other] || {}).sex || null;
          return gendered(sex, 'Step-Brother', 'Step-Sister', 'Step-Sibling');
        }
      }
    }
  }

  // ── Tier 3: specific in-laws ─────────────────────────────────────
  // 3a: parent of viewer's spouse
  for (const sp of viewerSpouses) {
    const spParents = ctx.PARENTS[sp] || [null, null];
    if (spParents.includes(other)) {
      const sex = (ctx.PEOPLE[other] || {}).sex || null;
      return gendered(sex, 'Father-in-law', 'Mother-in-law', 'Parent-in-law');
    }
  }

  // 3b: sibling of viewer's spouse
  for (const sp of viewerSpouses) {
    const spParents = ctx.PARENTS[sp] || [null, null];
    for (const p of spParents) {
      if (!p) continue;
      const siblings = (ctx.CHILDREN[p] || []).filter(c => c !== sp);
      if (siblings.includes(other)) {
        const sex = (ctx.PEOPLE[other] || {}).sex || null;
        return gendered(sex, 'Brother-in-law', 'Sister-in-law', 'Sibling-in-law');
      }
    }
  }

  // 3c: spouse of viewer's sibling
  for (const par of viewerParents) {
    for (const sib of (ctx.CHILDREN[par] || [])) {
      if (sib === viewer) continue;
      if (getSpousesOf(sib, ctx).includes(other)) {
        const sex = (ctx.PEOPLE[other] || {}).sex || null;
        return gendered(sex, 'Brother-in-law', 'Sister-in-law', 'Sibling-in-law');
      }
    }
  }

  // 3d: spouse of viewer's child
  for (const child of viewerChildren) {
    if (getSpousesOf(child, ctx).includes(other)) {
      const sex = (ctx.PEOPLE[other] || {}).sex || null;
      return gendered(sex, 'Son-in-law', 'Daughter-in-law', 'Child-in-law');
    }
  }

  // ── Tier 4: generic affinity templates ───────────────────────────
  // 4a: other is spouse of someone with a blood label
  const otherSpouses = getSpousesOf(other, ctx);
  let bestSpouseTemplate = null;
  let bestSpouseLegLength = Infinity;
  for (const sp of otherSpouses) {
    if (sp === viewer) continue; // already handled by tier 1
    const paths = findBloodPaths(viewer, sp, ctx);
    if (paths.length === 0) continue;
    const path = pickClosestPath(paths);
    const spSex = (ctx.PEOPLE[sp] || {}).sex || null;
    const spIsHalf = !isFullRelationship(path, ctx);
    const spLabel = formatBloodLabel(path.a, path.b, spSex, spIsHalf);
    if (!spLabel) continue;
    const legLen = path.a + path.b;
    if (legLen < bestSpouseLegLength) {
      const otherSex = (ctx.PEOPLE[other] || {}).sex || null;
      const verb = _spouseVerb(otherSex, _isDivorced(sp, other, ctx));
      bestSpouseTemplate = `${verb} of ${spLabel}`;
      bestSpouseLegLength = legLen;
    }
  }
  if (bestSpouseTemplate) return bestSpouseTemplate;

  // 4b: other has a blood label relative to viewer's spouse
  let bestSpouseSideTemplate = null;
  let bestSpouseSideLeg = Infinity;
  for (const sp of viewerSpouses) {
    const paths = findBloodPaths(sp, other, ctx);
    if (paths.length === 0) continue;
    const path = pickClosestPath(paths);
    const otherSex = (ctx.PEOPLE[other] || {}).sex || null;
    const isHalf = !isFullRelationship(path, ctx);
    const label = formatBloodLabel(path.a, path.b, otherSex, isHalf);
    if (!label) continue;
    const legLen = path.a + path.b;
    if (legLen < bestSpouseSideLeg) {
      const spouseWord = _isDivorced(viewer, sp, ctx) ? 'Ex-Spouse' : 'Spouse';
      bestSpouseSideTemplate = `${label} of ${spouseWord}`;
      bestSpouseSideLeg = legLen;
    }
  }
  if (bestSpouseSideTemplate) return bestSpouseSideTemplate;

  return null;
}

function computeRelationship(viewerXref, otherXref, ctx) {
  if (otherXref === viewerXref) {
    return { label: 'Self', debug: { a: 0, b: 0 } };
  }

  // 1. Best kin relationship (blood, then composed affinity via _bestRel).
  // _bestRel's findAtomicAffinity includes godparent as Tier 5, so the godparent
  // label may itself surface here when no other kin relationship exists.
  let kinResult = null;
  const paths = findBloodPaths(viewerXref, otherXref, ctx);
  if (paths.length > 0) {
    const path = pickClosestPath(paths);
    const otherSex = (ctx.PEOPLE[otherXref] || {}).sex || null;
    const isHalf = !isFullRelationship(path, ctx);
    const label = formatBloodLabel(path.a, path.b, otherSex, isHalf);
    if (label !== null) {
      kinResult = { label, ofs: 0, debug: { a: path.a, b: path.b, mrca: path.mrca, half: isHalf } };
    }
  }
  if (!kinResult) {
    const aff = _bestRel(viewerXref, otherXref, ctx, new Set(), _MAX_REL_DEPTH);
    if (aff) kinResult = { label: aff.label, ofs: aff.ofs, debug: { affinity: true, edges: aff.edges, ofs: aff.ofs } };
  }

  // 2. Direct godparent/godchild link (no recursion).
  const gpDirect = findGodparentAtomic(viewerXref, otherXref, ctx);

  // 3. Combine.
  if (!kinResult && !gpDirect) return null;
  if (!gpDirect) return { label: kinResult.label, debug: kinResult.debug };
  if (!kinResult) return { label: gpDirect.label, debug: { godparent: true } };

  // Both exist. Avoid duplicate when _bestRel chose godparent via Tier 5
  // (i.e., kinResult is itself the godparent label).
  if (kinResult.label === gpDirect.label) {
    return { label: gpDirect.label, debug: { godparent: true } };
  }
  // Atomic kin + atomic godparent → combine.
  if (kinResult.ofs === 0) {
    return {
      label: `${kinResult.label} and ${gpDirect.label}`,
      debug: { ...kinResult.debug, godparent: true, combined: true },
    };
  }
  // Composed (distant) kin + atomic godparent → just godparent.
  return { label: gpDirect.label, debug: { godparent: true } };
}

// Return every distinct relationship between viewer and other, for the
// click-for-details popover. Each entry: { kind, label, ... }.
// Kinds: 'self', 'blood', 'affinity', 'godparent'.
function enumerateRelationships(viewerXref, otherXref, ctx) {
  if (viewerXref === otherXref) return [{ kind: 'self', label: 'Self' }];
  const out = [];

  const paths = findBloodPaths(viewerXref, otherXref, ctx);
  if (paths.length > 0) {
    const path = pickClosestPath(paths);
    const otherSex = (ctx.PEOPLE[otherXref] || {}).sex || null;
    const isHalf = !isFullRelationship(path, ctx);
    const label = formatBloodLabel(path.a, path.b, otherSex, isHalf);
    if (label) out.push({ kind: 'blood', label, path: { a: path.a, b: path.b, mrca: path.mrca, half: isHalf } });
  }

  // Atomic affinity excluding godparent (we want the kinship in-law/step term, not Tier 5).
  // Re-run the in-law/step tiers explicitly. Simplest: temporarily strip godparent from
  // ctx by checking if findAtomicAffinity's result is the godparent label and, if so,
  // re-deriving via the kin-only path. To keep code small, just call _bestRel with a
  // wrapper that pretends godparent doesn't exist.
  const noGpCtx = Object.create(ctx);
  noGpCtx._godparentIndex = { byChild: new Map(), byParent: new Map() };
  const aff = _bestRel(viewerXref, otherXref, noGpCtx, new Set(), _MAX_REL_DEPTH);
  if (aff && (!out.length || aff.label !== out[0].label)) {
    out.push({ kind: 'affinity', label: aff.label, edges: aff.edges, ofs: aff.ofs });
  }

  const gp = findGodparentAtomic(viewerXref, otherXref, ctx);
  if (gp) out.push({ kind: 'godparent', label: gp.label });

  return out;
}

if (typeof module !== 'undefined') {
  module.exports = { computeRelationship, enumerateRelationships, findBloodPaths, pickClosestPath, bfsUp, bfsDown, formatBloodLabel, gendered, greatPrefix, ordinal, isFullRelationship, getSpousesOf, findAffinityLabel, findGodparentAtomic, getGodparentIndex };
}
