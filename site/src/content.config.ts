import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

// The `reviews` collection is the exported projection of the canon store.
// Frontmatter here MUST match what backend/engine/export.py emits.
//
// Two kinds of entry live here:
//   - 'review'   — a graded verdict on a performance (the default). Carries a
//                  work, a verdict, and a rating.
//   - 'dispatch' — an ungraded pre-performance column (e.g. "Sound Footing").
//                  Legitimately has no work, no verdict, and no rating.
const REVIEW_REQUIRED = ['work', 'workSlug', 'verdict', 'rating'] as const;

const reviews = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/reviews' }),
  schema: z
    .object({
      title: z.string(),
      kind: z.enum(['review', 'dispatch']).default('review'),
      company: z.string(),
      companySlug: z.string(),
      // Optional so a dispatch (which reviews no specific work) can omit them;
      // the refine below re-requires them for kind: review.
      work: z.string().optional(),
      workSlug: z.string().optional(),
      dancers: z.array(z.string()).default([]),
      verdict: z.enum(['rave', 'admiring', 'mixed', 'cool', 'pan']).nullable().optional(),
      // A dispatch has no score; do not fake one. Null/absent is valid here,
      // and re-required for reviews by the refine below.
      rating: z.number().min(0).max(5).nullable().optional(),
      isoYear: z.number().int(),
      isoWeek: z.number().int(),
      week: z.string(),
      pubDate: z.coerce.date(),
      // Single URL field for binary assets so they can later move to external
      // hosting with only a base-URL change. Null when there's no audio yet.
      audioUrl: z.string().url().nullable().optional(),
      // Dispatch identity fields, preserved from the draft.
      column: z.string().optional(),
      dateline: z.string().optional(),
      venue: z.string().optional(),
    })
    .superRefine((d, ctx) => {
      if (d.kind === 'review') {
        for (const field of REVIEW_REQUIRED) {
          if (d[field] === undefined || d[field] === null) {
            ctx.addIssue({
              code: z.ZodIssueCode.custom,
              path: [field],
              message: `A review requires "${field}" (only a dispatch may omit it).`,
            });
          }
        }
      }
    }),
});

export const collections = { reviews };
