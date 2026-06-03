// @ts-check
import { defineConfig } from 'astro/config';

// NOTE: `site` + `base` are set for a GitHub Pages PROJECT site served at
//   https://<user>.github.io/yuriatin/
// Replace the placeholder host below with your GitHub username before deploy
// (RSS canonical URLs derive from `site`). The CI workflow also injects it.
export default defineConfig({
  site: 'https://example.github.io',
  base: '/yuriatin',
  trailingSlash: 'ignore',
  // Keep the build fully static — no JS islands yet (a later phase).
  output: 'static',
});
