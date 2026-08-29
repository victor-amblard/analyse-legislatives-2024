/**
 * Duplique les notes Markdown standard dans la marge, sans modifier leur source.
 *
 * Le rendu de notes de bas de page reste intact pour les écrans étroits et les
 * lecteurs sans CSS. Sur grand écran, une copie sémantique est insérée après le
 * paragraphe qui porte l'appel ; le CSS la fait flotter dans la marge droite.
 */

function clone(node) {
  return structuredClone(node);
}

function isElement(node, tagName) {
  return node?.type === 'element' && (!tagName || node.tagName === tagName);
}

function footnoteIdFromReference(node) {
  if (!isElement(node, 'a') || !node.properties?.dataFootnoteRef) return null;
  const href = String(node.properties.href ?? '');
  const prefix = '#user-content-fn-';
  return href.startsWith(prefix) ? href.slice(prefix.length) : null;
}

function findReferences(node, found = []) {
  const id = footnoteIdFromReference(node);
  if (id) found.push({ id, node });
  for (const child of node.children ?? []) findReferences(child, found);
  return found;
}

function withoutBacklinks(node) {
  const classes = node?.properties?.className ?? [];
  const ariaLabel = String(node?.properties?.ariaLabel ?? '');
  if (
    isElement(node, 'a') &&
    (Object.hasOwn(node.properties ?? {}, 'dataFootnoteBackref') ||
      classes.includes('data-footnote-backref') ||
      String(node.properties?.href ?? '').startsWith('#user-content-fnref-') ||
      ariaLabel.startsWith('Back to reference'))
  ) return null;
  const copy = clone(node);
  if (copy.children) {
    copy.children = copy.children.map(withoutBacklinks).filter(Boolean);
  }
  return copy;
}

function inlineDefinitionChildren(definition) {
  const result = [];
  for (const child of definition.children ?? []) {
    const clean = withoutBacklinks(child);
    if (!clean) continue;
    // Une note ordinaire est un <p>. Retirer seulement cette enveloppe évite
    // un bloc imbriqué dans la note marginale tout en préservant emphases/liens.
    if (isElement(clean, 'p')) result.push(...(clean.children ?? []));
    else result.push(clean);
  }
  return result;
}

function collectDefinitions(node, definitions = new Map()) {
  if (isElement(node, 'li')) {
    const id = String(node.properties?.id ?? '');
    const prefix = 'user-content-fn-';
    if (id.startsWith(prefix)) definitions.set(id.slice(prefix.length), node);
  }
  for (const child of node.children ?? []) collectDefinitions(child, definitions);
  return definitions;
}

function sidenote(id, number, definition, occurrence) {
  return {
    type: 'element',
    tagName: 'aside',
    properties: {
      className: ['sidenote'],
      id: `sidenote-${id}-${occurrence}`,
      role: 'note',
      ariaLabel: `Note ${number}`,
    },
    children: [
      {
        type: 'element',
        tagName: 'span',
        properties: { className: ['sidenote-number'], ariaHidden: 'true' },
        children: [{ type: 'text', value: number }],
      },
      { type: 'text', value: ' ' },
      ...inlineDefinitionChildren(definition),
    ],
  };
}

function decorateReference(reference, number) {
  const classes = reference.properties.className ?? [];
  reference.properties.className = [...classes, 'footnote-ref-mobile'];
  return {
    type: 'element',
    tagName: 'span',
    properties: { className: ['margin-note-ref'], ariaHidden: 'true' },
    children: [{ type: 'text', value: number }],
  };
}

function transformContainer(node, definitions, occurrences) {
  if (!node.children) return;
  const children = [];
  for (const child of node.children) {
    transformContainer(child, definitions, occurrences);
    children.push(child);
    if (!isElement(child, 'p')) continue;

    for (const { id, node: reference } of findReferences(child)) {
      const definition = definitions.get(id);
      if (!definition) continue;
      const number = String(reference.children?.[0]?.value ?? '');
      const parent = findParent(child, reference);
      if (parent?.children) parent.children.push(decorateReference(reference, number));
      const occurrence = (occurrences.get(id) ?? 0) + 1;
      occurrences.set(id, occurrence);
      children.push(sidenote(id, number, definition, occurrence));
    }
  }
  node.children = children;
}

function findParent(root, target) {
  for (const child of root.children ?? []) {
    if (child === target) return root;
    const found = findParent(child, target);
    if (found) return found;
  }
  return null;
}

export default function rehypeSidenotes() {
  return (tree) => {
    const definitions = collectDefinitions(tree);
    if (!definitions.size) return;
    transformContainer(tree, definitions, new Map());
  };
}
