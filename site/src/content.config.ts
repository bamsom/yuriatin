import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

// The `reviews` collection is the exported projection of the canon store.
// Frontmatter here MUST match what backend/engine/export.py emits.
const reviews = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/reviews' }),
  schema: z.object({
    title: z.string(),
    company: z.string(),
    companySlug: z.string(),
    work: z.string(),
    workSlug: z.string(),
    dancers: z.array(z.string()).default([]),
    verdict: z.enum(['rave', 'admiring', 'mixed', 'cool', 'pan']),
    rating: z.number().min(0).max(5),
    isoYear: z.number().int(),
    isoWeek: z.number().int(),
    week: z.string(),
    pubDate: z.coerce.date(),
    // Single URL field for binary assets so they can later move to external
    // hosting with only a base-URL change. Null when there's no audio yet.
    audioUrl: z.string().url().nullable().optional(),
  }),
});

export const collections = { reviews };
