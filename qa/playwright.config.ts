import path from 'path';

import { defineConfig } from '@playwright/test';

/**
 * Init script for the admin browser context.
 *
 * `apps/admin-web/src/composables/i18n.ts:18` gives a STORED `askai-admin-locale`
 * value precedence over `navigator.languages[0]`, so a locale stored by an earlier
 * `setLocale()` call in the same context silently defeats the `locale: 'zh-CN'`
 * pin below. This script must run before any page script.
 *
 * Playwright 1.63.0 has no config-level `addInitScript` test option (it is not in
 * `PlaywrightTestOptions` and passing it to `use` is silently ignored — verified
 * against the installed 1.63.0 build). A config cannot target one specific
 * context, so the spec must register this on the admin context explicitly:
 *
 *     const adminContext = await browser.newContext();
 *     await adminContext.addInitScript(ADMIN_LOCALE_RESET);
 *
 * The global `locale: 'zh-CN'` option below IS inherited by contexts created via
 * `browser.newContext()` (the test runner injects combined context options into
 * every context creation), so only the stored-key removal needs this manual step.
 */
export const ADMIN_LOCALE_RESET = (): void => {
  window.localStorage.removeItem('askai-admin-locale');
};

export default defineConfig({
  testDir: '.',
  outputDir: path.join(process.env.EVIDENCE_ROOT, 'playwright'),
  reporter: [
    ['list'],
    [
      'html',
      {
        outputFolder: path.join(process.env.EVIDENCE_ROOT, 'playwright', 'report'),
        open: 'never',
      },
    ],
  ],
  workers: 1,
  use: {
    baseURL: process.env.MOVO_QA_BASE_URL,
    locale: 'zh-CN',
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
});
