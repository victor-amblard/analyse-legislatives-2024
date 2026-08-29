import { visit } from 'unist-util-visit';

/**
 * Enveloppe chaque <table> dans un conteneur défilant.
 *
 * Sans cela, un tableau plus large que la fenêtre fait défiler la PAGE
 * horizontalement au lieu du seul tableau — les tableaux de résultats font 8
 * colonnes et contiennent du LaTeX, donc le cas est la règle et non l'exception
 * sur mobile.
 */
export default function rehypeWrapTables() {
  return (tree) => {
    visit(tree, 'element', (node, index, parent) => {
      if (node.tagName !== 'table' || !parent || index === undefined) return;
      if (parent.type === 'element' && parent.properties?.className?.includes?.('table-scroll')) {
        return;
      }
      parent.children[index] = {
        type: 'element',
        tagName: 'div',
        properties: { className: ['table-scroll'], tabIndex: 0, role: 'region' },
        children: [node],
      };
    });
  };
}
