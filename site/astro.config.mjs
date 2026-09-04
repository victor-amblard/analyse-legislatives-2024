// @ts-check
import { defineConfig } from 'astro/config';
import { unified } from '@astrojs/markdown-remark';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import rehypeSlug from 'rehype-slug';
import rehypeAutolinkHeadings from 'rehype-autolink-headings';
import rehypeWrapTables from './src/plugins/rehype-wrap-tables.mjs';
import rehypeSidenotes from './src/plugins/rehype-sidenotes.mjs';
import rehypeBasePath from './src/plugins/rehype-base-path.mjs';

const base = '/analyse-legislatives-2024';

export default defineConfig({
  site: 'https://victor-amblard.github.io',
  base,
  markdown: {
    // Astro 7 utilise Sätteri par défaut ; on revient explicitement au
    // processeur remark/rehype, seul à accepter les plugins ci-dessous.
    // `markdown.remarkPlugins` / `markdown.rehypePlugins` au niveau racine sont
    // dépréciés depuis la v7 : ils se passent maintenant à `unified({...})`.
    processor: unified({
      // remark-math : LaTeX en ligne ($\sqrt{n}$) et en bloc.
      remarkPlugins: [remarkMath],
      // rehype-katex le rend en HTML ; rehypeWrapTables confine le débordement
      // horizontal des tableaux larges au tableau plutôt qu'à la page.
      rehypePlugins: [
        rehypeKatex,
        rehypeSidenotes,
        // Ancres : chaque titre devient adressable (#the-results), ce qui rend
        // le sommaire et les liens « voir plus bas » réellement cliquables.
        rehypeSlug,
        [
          rehypeAutolinkHeadings,
          {
            behavior: 'append',
            properties: { className: ['heading-anchor'], ariaHidden: 'true', tabIndex: -1 },
            content: { type: 'text', value: '#' },
          },
        ],
        rehypeWrapTables,
        [rehypeBasePath, { base }],
      ],
    }),
    shikiConfig: { theme: 'github-dark', wrap: false },
  },
});
