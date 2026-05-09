// Compute the kinship label between two people in the JS graph.
// Reads (via injected ctx, falling back to globals): PEOPLE, PARENTS, CHILDREN, RELATIVES, FAMILIES.

// 11th cousin / 10× great-grandparent (FamilySearch chart cap) requires depth 12 from MRCA.
const MAX_DEPTH = 12;

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

  // Aunt/Uncle line (a≥2, b=1)
  if (b === 1 && a >= 2) {
    const term = gendered(otherSex, 'Uncle', 'Aunt', 'Aunt or Uncle');
    if (a === 2) return halfPrefix + term;
    return halfPrefix + greatPrefix(a - 2) + term;
  }

  // Niece/Nephew line (a=1, b≥2)
  if (a === 1 && b >= 2) {
    const term = gendered(otherSex, 'Nephew', 'Niece', 'Niece or Nephew');
    if (b === 2) return halfPrefix + term;
    return halfPrefix + greatPrefix(b - 2) + term;
  }

  // Cousins (a≥2 AND b≥2)
  if (a >= 2 && b >= 2) {
    const cousinNum = Math.min(a, b) - 1;
    if (cousinNum > 11) return null; // cap (FamilySearch chart bound)
    const removed = Math.abs(a - b);
    const removedPart = removed > 0 ? `, ${removed}× Removed` : '';
    return halfPrefix + ordinal(cousinNum) + ' Cousin' + removedPart;
  }

  return null;
}

// Find all blood paths from viewer to other.
// Each path: { a, b, mrca, viewerLeg, otherLeg }
//   viewerLeg = MRCA's child on viewer's path (=== viewer if a===1; null if a===0)
//   otherLeg  = MRCA's child on other's path  (=== other  if b===1; null if b===0)
function findBloodPaths(viewer, other, ctx) {
  const ancestors = bfsUp(viewer, ctx.PARENTS, MAX_DEPTH);
  const paths = [];
  for (const [ancestorXref, viewerPaths] of ancestors) {
    const descendants = bfsDown(ancestorXref, ctx.CHILDREN, MAX_DEPTH);
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

function findAffinityLabel(viewer, other, ctx) {
  const viewerSpouses = getSpousesOf(viewer, ctx);
  const viewerParents = (ctx.PARENTS[viewer] || [null, null]).filter(Boolean);

  // ── Tier 1: spouse of viewer ─────────────────────────────────────
  if (viewerSpouses.includes(other)) {
    const sex = (ctx.PEOPLE[other] || {}).sex || null;
    return gendered(sex, 'Husband', 'Wife', 'Spouse');
  }

  // ── Tier 2: step relationships ───────────────────────────────────
  // Step-parent: spouse of viewer's bio parent who is NOT viewer's other bio parent
  for (const par of viewerParents) {
    const parentSpouses = getSpousesOf(par, ctx);
    if (parentSpouses.includes(other) && !viewerParents.includes(other)) {
      const sex = (ctx.PEOPLE[other] || {}).sex || null;
      return gendered(sex, 'Step-Father', 'Step-Mother', 'Step-Parent');
    }
  }

  // Step-child: child of viewer's spouse who is NOT viewer's bio child
  const viewerChildren = ctx.CHILDREN[viewer] || [];
  for (const sp of viewerSpouses) {
    const spChildren = ctx.CHILDREN[sp] || [];
    if (spChildren.includes(other) && !viewerChildren.includes(other)) {
      const sex = (ctx.PEOPLE[other] || {}).sex || null;
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
      const verb = gendered(otherSex, 'Husband', 'Wife', 'Spouse');
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
      bestSpouseSideTemplate = `${label} of Spouse`;
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
  const paths = findBloodPaths(viewerXref, otherXref, ctx);
  if (paths.length > 0) {
    const path = pickClosestPath(paths);
    const otherSex = (ctx.PEOPLE[otherXref] || {}).sex || null;
    const isHalf = !isFullRelationship(path, ctx);
    const label = formatBloodLabel(path.a, path.b, otherSex, isHalf);
    if (label !== null) {
      return { label, debug: { a: path.a, b: path.b, mrca: path.mrca, half: isHalf } };
    }
  }
  const affinity = findAffinityLabel(viewerXref, otherXref, ctx);
  if (affinity) return { label: affinity, debug: { affinity: true } };
  return null;
}

if (typeof module !== 'undefined') {
  module.exports = { computeRelationship, findBloodPaths, pickClosestPath, bfsUp, bfsDown, formatBloodLabel, gendered, greatPrefix, ordinal, isFullRelationship, getSpousesOf, findAffinityLabel };
}
