// Compute the kinship label between two people in the JS graph.
// Reads (via injected ctx, falling back to globals): PEOPLE, PARENTS, CHILDREN, RELATIVES, FAMILIES.

const MAX_DEPTH = 11;

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

function formatBloodLabel(a, b, otherSex) {
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

  return null;
}

function computeRelationship(viewerXref, otherXref, ctx) {
  if (otherXref === viewerXref) {
    return { label: 'Self', debug: { a: 0, b: 0 } };
  }
  // Direct ancestor?
  const ancestors = bfsUp(viewerXref, ctx.PARENTS, MAX_DEPTH);
  if (ancestors.has(otherXref)) {
    const path = ancestors.get(otherXref)[0];
    const otherSex = (ctx.PEOPLE[otherXref] || {}).sex || null;
    const label = formatBloodLabel(path.depth, 0, otherSex);
    if (label) return { label, debug: { a: path.depth, b: 0 } };
  }
  // Direct descendant?
  const descendants = bfsDown(viewerXref, ctx.CHILDREN, MAX_DEPTH);
  if (descendants.has(otherXref)) {
    const path = descendants.get(otherXref)[0];
    const otherSex = (ctx.PEOPLE[otherXref] || {}).sex || null;
    const label = formatBloodLabel(0, path.depth, otherSex);
    if (label) return { label, debug: { a: 0, b: path.depth } };
  }
  return null;
}

if (typeof module !== 'undefined') {
  module.exports = { computeRelationship, bfsUp, bfsDown, formatBloodLabel, gendered, greatPrefix };
}
