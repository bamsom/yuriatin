import rss from '@astrojs/rss';
import { getCollection } from 'astro:content';

// Weekly column => RSS is a first-class output, not an afterthought.
export async function GET(context) {
  const base = import.meta.env.BASE_URL.replace(/\/$/, ''); // -> "/yuriatin"
  const reviews = (await getCollection('reviews')).sort(
    (a, b) => b.data.pubDate.valueOf() - a.data.pubDate.valueOf(),
  );

  return rss({
    title: 'R. A. Pi — A Weekly Ballet Column',
    description: 'Dispatches from the ballet of a city that isn’t there.',
    site: context.site,
    items: reviews.map((r) => ({
      title: r.data.title,
      pubDate: r.data.pubDate,
      description:
        r.data.kind === 'dispatch'
          ? `DISPATCH — ${r.data.company}${r.data.dateline ? `, ${r.data.dateline}` : ''}`
          : `${r.data.verdict.toUpperCase()} (${r.data.rating}★) — ${r.data.company}, ${r.data.work}`,
      link: `${base}/reviews/${r.id}/`,
    })),
    customData: '<language>en-us</language>',
  });
}
