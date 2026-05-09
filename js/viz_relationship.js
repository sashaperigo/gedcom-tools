// Compute the kinship label between two people in the JS graph.
// Reads (via injected ctx, falling back to globals): PEOPLE, PARENTS, CHILDREN, RELATIVES, FAMILIES.

const MAX_DEPTH = 11;

function gendered(sex, mLabel, fLabel, neutralLabel) {
  if (sex === 'M') return mLabel;
  if (sex === 'F') return fLabel;
  return neutralLabel;
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

function formatBloodLabel(a, b, otherSex) {
  if (a === 0 && b === 0) return 'Self';
  if (b === 0 && a === 1) {
    return gendered(otherSex, 'Father', 'Mother', 'Parent');
  }
  return null;
}

function computeRelationship(viewerXref, otherXref, ctx) {
  if (otherXref === viewerXref) {
    return { label: 'Self', debug: { a: 0, b: 0 } };
  }
  const ancestors = bfsUp(viewerXref, ctx.PARENTS, MAX_DEPTH);
  if (ancestors.has(otherXref)) {
    const path = ancestors.get(otherXref)[0];
    const otherSex = (ctx.PEOPLE[otherXref] || {}).sex || null;
    const label = formatBloodLabel(path.depth, 0, otherSex);
    if (label) return { label, debug: { a: path.depth, b: 0 } };
  }
  return null;
}

if (typeof module !== 'undefined') {
  module.exports = { computeRelationship, bfsUp, formatBloodLabel, gendered };
}
