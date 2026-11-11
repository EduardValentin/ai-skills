export function naturalOrder(a, b) {
  return a.localeCompare(b, undefined, { numeric: true });
}

function adjacency(nodes, edges) {
  const out = new Map(nodes.map((node) => [node, []]));
  for (const [from, to] of edges) {
    if (out.has(from) && out.has(to)) out.get(from).push(to);
  }
  return out;
}

export function stronglyConnected(nodes, edges) {
  const out = adjacency(nodes, edges);
  const index = new Map();
  const low = new Map();
  const stack = [];
  const onStack = new Set();
  const components = [];

  function popComponent(root) {
    const members = [];
    let member;
    do {
      member = stack.pop();
      onStack.delete(member);
      members.push(member);
    } while (member !== root);
    if (members.length > 1) components.push(members.sort(naturalOrder));
  }

  function visit(node) {
    index.set(node, index.size);
    low.set(node, index.get(node));
    stack.push(node);
    onStack.add(node);
    for (const next of out.get(node)) {
      if (!index.has(next)) {
        visit(next);
        low.set(node, Math.min(low.get(node), low.get(next)));
      } else if (onStack.has(next)) {
        low.set(node, Math.min(low.get(node), index.get(next)));
      }
    }
    if (low.get(node) === index.get(node)) popComponent(node);
  }

  for (const node of nodes) {
    if (!index.has(node)) visit(node);
  }
  return components.sort((a, b) => naturalOrder(a[0], b[0]));
}
