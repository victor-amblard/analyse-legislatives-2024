import { defineCollection } from 'astro:content';
import { z } from 'zod';
import { glob } from 'astro/loaders';

/**
 * Le writeup est lu DEPUIS LA RACINE DU DÉPÔT plutôt que recopié dans
 * `src/content/`. C'est le point important : `writeup.md` reste la seule source
 * de vérité, éditable depuis l'IDE comme avant, et le site n'en est qu'un rendu.
 * Une copie divergerait au premier oubli.
 */
const posts = defineCollection({
  loader: glob({ pattern: 'writeup*.md', base: '../' }),
  schema: z.object({
    title: z.string(),
    description: z.string().optional(),
    date: z.coerce.date().optional(),
    author: z.string().optional(),
    lang: z.enum(['fr', 'en']),
  }),
});

export const collections = { posts };
