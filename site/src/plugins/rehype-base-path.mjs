import { visit } from 'unist-util-visit';

/** Prefix root-relative public assets when the site is served below a base path. */
export default function rehypeBasePath({ base }) {
  const prefix = base.replace(/\/$/, '');

  return (tree) => {
    visit(tree, (node) => {
      if (node.type === 'raw') {
        node.value = node.value.replace(
          /(["'])\/(figures\/[^"']+|favicon\.(?:svg|ico))\1/g,
          `$1${prefix}/$2$1`,
        );
      }

      if (node.type !== 'element') return;
      for (const property of ['src', 'srcSet', 'href']) {
        const value = node.properties?.[property];
        if (typeof value === 'string' && /^\/(?:figures\/|favicon\.)/.test(value)) {
          node.properties[property] = `${prefix}${value}`;
        }
      }
    });
  };
}
