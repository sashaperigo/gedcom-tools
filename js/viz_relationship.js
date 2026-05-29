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
      return { label: _godparentLabel(entry.rela, otherSex), edges: 1,
               path: { nodes: [other, viewer], edges: ['godparent'], mrcaIndex: null } };
    }
  }
  // viewer is other's godparent → other is viewer's godchild
  for (const entry of idx.byChild.get(other) || []) {
    if (entry.xref === viewer) {
      return { label: _godchildLabel(otherSex), edges: 1,
               path: { nodes: [other, viewer], edges: ['godchild'], mrcaIndex: null } };
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

// Returns {label, edges, path} for an atomic affinity (no "of" composition) between viewer and other.
// Edges counts graph hops on the kinship graph (parent/child/spouse).
function findAtomicAffinity(viewer, other, ctx) {
  const viewerSpouses = getSpousesOf(viewer, ctx);
  const viewerParents = (ctx.PARENTS[viewer] || [null, null]).filter(Boolean);
  const otherSex = (ctx.PEOPLE[other] || {}).sex || null;

  // Tier 1: spouse of viewer (1 edge)
  if (viewerSpouses.includes(other)) {
    const ex = _isDivorced(viewer, other, ctx);
    return { label: _spouseVerb(otherSex, ex), edges: 1,
             path: { nodes: [other, viewer], edges: [ex ? 'ex-spouse' : 'spouse'], mrcaIndex: null } };
  }

  // Tier 2: step-parent (up + across, 2 edges)
  for (const par of viewerParents) {
    if (getSpousesOf(par, ctx).includes(other) && !viewerParents.includes(other)) {
      const ex = _isDivorced(other, par, ctx);
      const path = { nodes: [other, par, viewer], edges: [ex ? 'ex-spouse' : 'spouse', 'descent-up'], mrcaIndex: null };
      if (_isFormerOrPredeceasedStep(other, par, viewer, ctx)) {
        const parSex     = (ctx.PEOPLE[par]   || {}).sex || null;
        const spouseVerb = _spouseVerb(otherSex, ex);
        const parLabel   = gendered(parSex,   'Father', 'Mother', 'Parent');
        return { label: `${spouseVerb} of ${parLabel}`, edges: 2, path };
      }
      return { label: gendered(otherSex, 'Step-Father', 'Step-Mother', 'Step-Parent'), edges: 2, path };
    }
  }

  // Tier 2: step-child (across + down, 2 edges)
  const viewerChildren = ctx.CHILDREN[viewer] || [];
  for (const sp of viewerSpouses) {
    const spChildren = ctx.CHILDREN[sp] || [];
    if (spChildren.includes(other) && !viewerChildren.includes(other)) {
      const ex = _isDivorced(viewer, sp, ctx);
      const path = { nodes: [other, sp, viewer], edges: ['descent-down', ex ? 'ex-spouse' : 'spouse'], mrcaIndex: null };
      if (_isFormerOrPredeceasedStep(viewer, sp, other, ctx)) {
        const spSex      = (ctx.PEOPLE[sp]    || {}).sex || null;
        const childLabel = gendered(otherSex, 'Son', 'Daughter', 'Child');
        const spouseVerb = _spouseVerb(spSex, ex);
        return { label: `${childLabel} of ${spouseVerb}`, edges: 2, path };
      }
      return { label: gendered(otherSex, 'Step-Son', 'Step-Daughter', 'Step-Child'), edges: 2, path };
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
          const ex = _isDivorced(stepPar, par, ctx);
          return { label: gendered(otherSex, 'Step-Brother', 'Step-Sister', 'Step-Sibling'), edges: 3,
                   path: { nodes: [other, stepPar, par, viewer],
                           edges: ['descent-down', ex ? 'ex-spouse' : 'spouse', 'descent-up'], mrcaIndex: null } };
        }
      }
    }
  }

  // Tier 3a: parent-in-law (across + up, 2 edges)
  for (const sp of viewerSpouses) {
    const spParents = ctx.PARENTS[sp] || [null, null];
    if (spParents.includes(other)) {
      const ex = _isDivorced(viewer, sp, ctx);
      return { label: gendered(otherSex, 'Father-in-law', 'Mother-in-law', 'Parent-in-law'), edges: 2,
               path: { nodes: [other, sp, viewer], edges: ['descent-up', ex ? 'ex-spouse' : 'spouse'], mrcaIndex: null } };
    }
  }

  // Tier 3b: sibling-in-law via spouse's sibling (across + up + down, 3 edges)
  for (const sp of viewerSpouses) {
    const spParents = ctx.PARENTS[sp] || [null, null];
    for (const p of spParents) {
      if (!p) continue;
      const siblings = (ctx.CHILDREN[p] || []).filter(c => c !== sp);
      if (siblings.includes(other)) {
        const ex = _isDivorced(viewer, sp, ctx);
        return { label: gendered(otherSex, 'Brother-in-law', 'Sister-in-law', 'Sibling-in-law'), edges: 3,
                 path: { nodes: [other, p, sp, viewer],
                         edges: ['descent-down', 'descent-up', ex ? 'ex-spouse' : 'spouse'], mrcaIndex: null } };
      }
    }
  }

  // Tier 3c: sibling-in-law via sibling's spouse (up + down + across, 3 edges)
  for (const par of viewerParents) {
    for (const sib of (ctx.CHILDREN[par] || [])) {
      if (sib === viewer) continue;
      if (getSpousesOf(sib, ctx).includes(other)) {
        const ex = _isDivorced(sib, other, ctx);
        return { label: gendered(otherSex, 'Brother-in-law', 'Sister-in-law', 'Sibling-in-law'), edges: 3,
                 path: { nodes: [other, sib, par, viewer],
                         edges: [ex ? 'ex-spouse' : 'spouse', 'descent-down', 'descent-up'], mrcaIndex: null } };
      }
    }
  }

  // Tier 3d: child-in-law (down + across, 2 edges)
  for (const child of viewerChildren) {
    if (getSpousesOf(child, ctx).includes(other)) {
      const ex = _isDivorced(child, other, ctx);
      return { label: gendered(otherSex, 'Son-in-law', 'Daughter-in-law', 'Child-in-law'), edges: 2,
               path: { nodes: [other, child, viewer], edges: [ex ? 'ex-spouse' : 'spouse', 'descent-down'], mrcaIndex: null } };
    }
  }

  // Tier 5: godparent / godchild (already returns {label, edges, path}).
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
      const spec = _bloodPathSpec(viewer, other, path, ctx);
      if (label && spec) best = _betterCand(best, { label, edges: path.a + path.b, ofs: 0, path: spec });
    }
  }

  // Atomic affinity
  const atomic = findAtomicAffinity(viewer, other, ctx);
  if (atomic) best = _betterCand(best, { label: atomic.label, edges: atomic.edges, ofs: 0, path: atomic.path || null });

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
    const leftSpec = _bloodPathSpec(viewer, zXref, path, ctx); // [Z, …, viewer]
    let composedPath = null;
    if (leftSpec && subAtomic.path) {
      composedPath = {
        nodes: subAtomic.path.nodes.concat(leftSpec.nodes.slice(1)),   // other … Z … viewer (Z shared, dropped once)
        edges: subAtomic.path.edges.concat(leftSpec.edges),
        mrcaIndex: (subAtomic.path.nodes.length - 1) + leftSpec.mrcaIndex,
      };
    }
    const cand = {
      label: `${subAtomic.label} of ${leftLabel}`,
      edges: leftEdges + subAtomic.edges,
      ofs: 1,
      leftEdges,
      path: composedPath,
    };
    best = _betterCand(best, cand);
  }

  // Split via spouse of viewer
  for (const sp of getSpousesOf(viewer, ctx)) {
    if (sp === other || newSeen.has(sp)) continue;
    if (best && 1 >= best.edges) continue;
    const sub = _bestRel(sp, other, ctx, newSeen, depthLeft - 1);
    if (!sub) continue;
    const ex = _isDivorced(viewer, sp, ctx);
    const spouseWord = ex ? 'Ex-Spouse' : 'Spouse';
    const cand = {
      label: `${sub.label} of ${spouseWord}`,
      edges: 1 + sub.edges,
      ofs: sub.ofs + 1,
      leftEdges: 1,
      path: sub.path ? {
        nodes: sub.path.nodes.concat([viewer]),               // other … sp → you
        edges: sub.path.edges.concat([ex ? 'ex-spouse' : 'spouse']),
        mrcaIndex: sub.path.mrcaIndex,
      } : null,
    };
    best = _betterCand(best, cand);
  }

  return best;
}

// Depth = how many "of" compositions we'll build. 1 covers all current label cases
// ("Father-in-law of Cousin", "Godmother of Cousin", "Wife of Cousin", etc.). Higher
// values blow up combinatorially on real trees (O(B^depth) where B = blood relatives).
const _MAX_REL_DEPTH = 1;

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
// click-for-details popover. Each entry: { kind, label, path }.
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
    if (label) {
      const spec = _bloodPathSpec(viewerXref, otherXref, path, ctx);
      out.push({ kind: 'blood', label,
                 path: spec ? _stepsToPath(spec.nodes, spec.edges, spec.mrcaIndex, ctx) : null });
    }
  }

  const noGpCtx = Object.create(ctx);
  noGpCtx._godparentIndex = { byChild: new Map(), byParent: new Map() };
  const aff = _bestRel(viewerXref, otherXref, noGpCtx, new Set(), _MAX_REL_DEPTH);
  if (aff && (!out.length || aff.label !== out[0].label)) {
    out.push({ kind: 'affinity', label: aff.label,
               path: aff.path ? _stepsToPath(aff.path.nodes, aff.path.edges, aff.path.mrcaIndex, ctx) : null });
  }

  const gp = findGodparentAtomic(viewerXref, otherXref, ctx);
  if (gp) out.push({ kind: 'godparent', label: gp.label,
                     path: gp.path ? _stepsToPath(gp.path.nodes, gp.path.edges, gp.path.mrcaIndex, ctx) : null });

  return out;
}

// ── Relationship-path reconstruction (for the click-to-expand path modal) ──

// Lowercase kinship step terms used between rows of the relationship chain.
function _childStep(sex)  { return gendered(sex, 'son of',    'daughter of', 'child of'); }
function _parentStep(sex) { return gendered(sex, 'father of', 'mother of',   'parent of'); }
function _spouseStep(sex, ex) { return (ex ? 'ex-' : '') + gendered(sex, 'husband of', 'wife of', 'spouse of'); }
function _godparentStep(sex)  { return gendered(sex, 'godfather of', 'godmother of', 'godparent of'); }
function _godchildStep(sex)   { return gendered(sex, 'godson of', 'goddaughter of', 'godchild of'); }

// Map an edgeKind + the UPPER node's sex to the lowercase chain term.
function _stepTerm(edgeKind, upperSex) {
  switch (edgeKind) {
    case 'descent-down': return _childStep(upperSex);
    case 'descent-up':   return _parentStep(upperSex);
    case 'spouse':       return _spouseStep(upperSex, false);
    case 'ex-spouse':    return _spouseStep(upperSex, true);
    case 'godparent':    return _godparentStep(upperSex);
    case 'godchild':     return _godchildStep(upperSex);
    default:             return null;
  }
}

// Convert a display-order path spec into the render array (other → … → you).
// `nodes` are xrefs top→bottom; `edges[i]` is the edgeKind from nodes[i] (upper)
// to nodes[i+1] (lower); `mrcaIndex` flags a blood apex (or null for none).
function _stepsToPath(nodes, edges, mrcaIndex, ctx) {
  return nodes.map((xref, i) => {
    const sex = (ctx.PEOPLE[xref] || {}).sex || null;
    const edgeKind = i < nodes.length - 1 ? edges[i] : null;
    return {
      xref,
      isOther: i === 0,
      isViewer: i === nodes.length - 1,
      isMrca: i === mrcaIndex,
      relToNext: edgeKind ? _stepTerm(edgeKind, sex) : null,
      edgeKind,
    };
  });
}

// Walk bfsUp back-pointers from `mrca` (known to sit at depth `dist` from
// `endpoint`) down to `endpoint`, returning [mrca, ..., endpoint] (length dist+1).
// Chains `viaParentXref`, picking at each node the entry whose depth matches the
// step we're on so pedigree-collapse multi-entries don't derail the walk.
function _reconstructLeg(endpoint, mrca, dist, parents) {
  const up = bfsUp(endpoint, parents, dist);
  const chain = [];
  let node = mrca;
  let d = dist;
  while (true) {
    chain.push(node);
    if (d === 0) break;
    const entries = up.get(node) || [];
    const entry = entries.find(e => e.depth === d) || entries[0];
    if (!entry || !entry.viaParentXref) break; // safety: broken back-pointer chain
    node = entry.viaParentXref;
    d -= 1;
  }
  return chain.length === dist + 1 ? chain : null; // null = broken/incomplete leg
}

// Build a display-order blood spec {nodes, edges, mrcaIndex} for viewer↔other,
// given the closest path's {a, b, mrca}. Returns null on a broken back-pointer leg.
function _bloodPathSpec(viewer, other, pathInfo, ctx) {
  const { a, b, mrca } = pathInfo;
  const viewerChain = _reconstructLeg(viewer, mrca, a, ctx.PARENTS); // [mrca, ..., viewer]
  const otherChain  = _reconstructLeg(other,  mrca, b, ctx.PARENTS); // [mrca, ..., other]
  if (!viewerChain || !otherChain) return null;
  const nodes = otherChain.slice().reverse().concat(viewerChain.slice(1)); // other → … → you
  const mrcaIndex = b;
  const edges = nodes.slice(0, -1).map((_, i) => (i < mrcaIndex ? 'descent-down' : 'descent-up'));
  return { nodes, edges, mrcaIndex };
}

// Build the ordered chain of people connecting `otherXref` (top) to
// `viewerXref` ("you", bottom): [other, ..., MRCA, ..., you].
// `precomputedPath` (optional) is the closest {a, b, mrca} the panel already
// computed — supplying it skips the expensive findBloodPaths re-run; the two
// bounded bfsUp walks below are O(a) and O(b). Returns null when no blood path.
function buildRelationshipPath(viewerXref, otherXref, ctx, precomputedPath) {
  let a, b, mrca;
  if (precomputedPath && precomputedPath.mrca != null
      && precomputedPath.a != null && precomputedPath.b != null) {
    ({ a, b, mrca } = precomputedPath);
  } else {
    const paths = findBloodPaths(viewerXref, otherXref, ctx);
    if (paths.length === 0) return null;
    const p = pickClosestPath(paths);
    a = p.a; b = p.b; mrca = p.mrca;
  }
  const spec = _bloodPathSpec(viewerXref, otherXref, { a, b, mrca }, ctx);
  if (!spec) return null;
  return _stepsToPath(spec.nodes, spec.edges, spec.mrcaIndex, ctx);
}

if (typeof module !== 'undefined') {
  module.exports = { computeRelationship, enumerateRelationships, buildRelationshipPath, findBloodPaths, pickClosestPath, bfsUp, bfsDown, formatBloodLabel, gendered, greatPrefix, ordinal, isFullRelationship, getSpousesOf, findGodparentAtomic, getGodparentIndex };
}
