/**
 * T12 (lanes B+C) — session-sharing realtime visibility QA.
 *
 * Runs against the seeded QA stack (`qa-realtime`, gateway on 127.0.0.1:3100):
 *   CONTEXT A = seeded employee from `qa/session-sharing-setup.json`
 *   CONTEXT B = employee created through the REAL admin console (pinned step 8)
 *
 * Lane B (this spec's first test): two-context browser flow, author identity,
 * member add/remove, live proxy SSE proof, and the four T09/T10 screenshots.
 *
 * Lane C (the two Node-side tests after it, plan L181-L182):
 *   1. 20-viewer load case — 20 concurrent SSE connections to ONE shared
 *      session through the REAL `/askai-api` proxy path, one stubbed turn,
 *      identical ordered frame sequences, event-to-frame p95 <= 2 s, and all
 *      20 long-lived streams still held (post-turn heartbeats, no EOF/abort).
 *   2. Failure controls — a deliberately BUFFERING local proxy (stdlib python
 *      written to the OS temp dir, never the worktree) must be DETECTED as
 *      clustered/stale while the direct path passes the same incremental
 *      contract; an invalid/expired bearer must surface 401; and a stream
 *      aborted mid-flight must be flagged as interrupted instead of passing.
 *
 * Hygiene contract (plan L179): every artifact path in this spec is an ABSOLUTE
 * `path.join(process.env.EVIDENCE_ROOT, ...)` value, so nothing Playwright writes
 * from this file can land in `qa/test-results/` or `qa/playwright-report/`.
 * The failure control writes its proxy script under `os.tmpdir()` for the same
 * reason. The plan pins the tracked qa/ file set at exactly six files, so these
 * Node-side cases live inside this spec by mandate.
 *
 * Idempotency: the create-user step treats a duplicate-login 409 as SUCCESS, and
 * the load-case viewers (`qa-load-01` .. `qa-load-20`) are created through the
 * real admin API with the same 409-as-success rule, so the pinned sequence can
 * be re-run against the same stack (F3 / lane C).
 *
 * Step (9) live-stream proof: a page-`evaluate` authenticated `fetch` reader on
 * the REAL `/askai-api` proxy path — heartbeats are SSE comments on a fixed 15 s
 * interval, observed within a bounded <= 25 s wait, and chunk arrival TIMES prove
 * the proxy does not buffer `text/event-stream`.
 */
import { test, expect, type Browser, type Page } from '@playwright/test';
import { spawn } from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import { ADMIN_LOCALE_RESET } from './playwright.config';

const EVIDENCE_ROOT = process.env.EVIDENCE_ROOT || '';
if (!EVIDENCE_ROOT) {
  throw new Error('EVIDENCE_ROOT must be exported before Playwright loads this spec (pinned step 0)');
}

const BASE_URL = process.env.MOVO_QA_BASE_URL || 'http://127.0.0.1:3100';
const ADMIN_URL = process.env.ADMIN_URL || `${BASE_URL}/admin`;

const ADMIN = { username: 'qa-admin', password: 'qa-admin-pass-2026' };
const EMPLOYEE_A = {
  username: 'qa-employee',
  password: 'qa-employee-pass-2026',
  name: 'QA 实时员工',
};
/** Long display name exercises the initials fallback + truncation at mobile width. */
const EMPLOYEE_B = {
  name: 'QA Realtime Participant B Longname',
  loginName: 'qa-employee-b',
  password: 'qa-employee-b-pass-2026',
  mobile: '13900000001',
  email: 'qa.employee.b@example.com',
};

const COMPOSER = 'textarea[placeholder="有问题，尽管问"]';
const STUB_REPLY = 'qa-stub stream ok';
const MSG_A = 'T12 message from owner A';
const MSG_B = 'T12 message from participant B';
const MSG_C = 'T12 live stream probe turn';

function log(message: string): void {
  console.log(`[T12] ${message}`);
}

function evidencePath(name: string): string {
  return path.join(EVIDENCE_ROOT, name);
}

/**
 * Compose several real browser captures into ONE evidence file (side by side).
 * Pure Playwright: the captures are rendered as data URLs and re-screenshotted,
 * so no image-processing dependency is introduced.
 */
async function captureSideBySide(
  browser: Browser,
  name: string,
  panels: { buffer: Buffer; label: string }[],
  viewport: { width: number; height: number },
): Promise<number> {
  const composer = await browser.newPage({ viewport });
  try {
    const cards = panels
      .map(
        (panel) => `
      <figure>
        <figcaption>${panel.label}</figcaption>
        <img src="data:image/png;base64,${panel.buffer.toString('base64')}" />
      </figure>`,
      )
      .join('');
    await composer.setContent(
      `<!doctype html><html><head><meta charset="utf-8" />
      <style>
        body { margin: 0; background: #0f172a; font: 13px/1.4 system-ui, sans-serif; color: #e2e8f0; }
        .row { display: flex; gap: 8px; padding: 8px; align-items: flex-start; }
        figure { margin: 0; flex: 1 1 0; min-width: 0; }
        figcaption { padding: 4px 0; font-weight: 600; }
        img { display: block; width: 100%; height: auto; border: 1px solid #334155; }
      </style></head><body><div class="row">${cards}</div></body></html>`,
      { waitUntil: 'load' },
    );
    const target = evidencePath(name);
    await composer.screenshot({ path: target, fullPage: true });
    const size = fs.statSync(target).size;
    log(`captured ${name} -> ${size} bytes (side-by-side)`);
    expect(size, `${name} must be non-trivial`).toBeGreaterThan(10_000);
    return size;
  } finally {
    await composer.close();
  }
}

type LiveChunk = { at: number; bytes: number; text: string };

type LiveProbe = {
  status: number;
  contentType: string | null;
  cacheControl: string | null;
  openedAtMs: number;
  chunks: LiveChunk[];
  heartbeatAtMs: number[];
  sawTurnStarted: boolean;
  sawTurnCompleted: boolean;
  sawAccessRevoked: boolean;
  eof: boolean;
  error: string | null;
};

/**
 * Authenticated `fetch` SSE reader inside the page (same pattern as T6/F3):
 * reads the REAL `/askai-api` proxy path with the browser's bearer token and
 * records each chunk's arrival time, so buffering can be disproved by timing.
 *
 * The read loop NEVER abandons a pending `reader.read()` promise: a settled
 * `Promise.race` timeout would leave that read queued, and every later chunk
 * would resolve the abandoned read (FIFO) and be lost. The observation budget
 * is enforced with an AbortController instead.
 */
async function probeLiveStream(page: Page, sessionId: string, budgetMs: number): Promise<LiveProbe> {
  return await page.evaluate(
    async ({ sessionId, budgetMs }) => {
      const started = performance.now();
      const out = {
        status: 0,
        contentType: null as string | null,
        cacheControl: null as string | null,
        openedAtMs: 0,
        chunks: [] as LiveChunk[],
        heartbeatAtMs: [] as number[],
        sawTurnStarted: false,
        sawTurnCompleted: false,
        sawAccessRevoked: false,
        eof: false,
        error: null as string | null,
      };
      const w = window as unknown as { __t12ProbeOpened?: boolean };
      const token = window.localStorage.getItem('auth_token') || '';
      const ctrl = new AbortController();
      const budgetTimer = setTimeout(() => ctrl.abort(), budgetMs);
      let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
      try {
        const response = await fetch(`/askai-api/api/sessions/${sessionId}/live`, {
          method: 'GET',
          headers: {
            Authorization: `Bearer ${token}`,
            Accept: 'text/event-stream',
          },
          signal: ctrl.signal,
          cache: 'no-store',
        });
        out.status = response.status;
        out.contentType = response.headers.get('content-type');
        out.cacheControl = response.headers.get('cache-control');
        out.openedAtMs = Math.round(performance.now() - started);
        w.__t12ProbeOpened = true;
        if (!response.body) throw new Error(`no response body (status ${response.status})`);
        reader = response.body.getReader();
        const decoder = new TextDecoder();
        while (true) {
          const read = await reader.read();
          if (read.done) {
            out.eof = true;
            break;
          }
          const text = decoder.decode(read.value, { stream: true });
          out.chunks.push({
            at: Math.round(performance.now() - started),
            bytes: read.value.byteLength,
            text,
          });
          if (text.includes(': heartbeat')) out.heartbeatAtMs.push(Math.round(performance.now() - started));
          if (text.includes('event: turn.started')) out.sawTurnStarted = true;
          if (text.includes('event: turn.completed')) out.sawTurnCompleted = true;
          if (text.includes('event: session.access.revoked')) out.sawAccessRevoked = true;
          if (out.heartbeatAtMs.length > 0 && out.chunks.length >= 2 && out.sawTurnCompleted) break;
        }
        clearTimeout(budgetTimer);
        await reader.cancel().catch(() => undefined);
      } catch (error) {
        clearTimeout(budgetTimer);
        out.error = String(error);
        try {
          await reader?.cancel();
        } catch {
          /* reader already cancelled */
        }
      }
      return out;
    },
    { sessionId, budgetMs },
  );
}

/** Scope message text to a rendered conversation row (the same text also appears in the sidebar title/header). */
function messageRow(page: Page, text: string) {
  return page.locator('[class*="group/user-message"]').filter({ hasText: text });
}

// ---------------------------------------------------------------------------
// Real-UI helpers (selectors verified against the feat/session-sharing tree)
// ---------------------------------------------------------------------------

async function loginAdmin(page: Page): Promise<void> {
  await page.goto(`${ADMIN_URL}/login`);
  await page.getByPlaceholder('请输入账号').fill(ADMIN.username);
  await page.getByPlaceholder('输入密码').fill(ADMIN.password);
  await page.getByRole('button', { name: '登录后台' }).click();
  // Single-tenant deployment: straight to the dashboard; tenant picker handled defensively.
  const tenantOption = page.locator('.tenant-option').first();
  await Promise.race([
    page.waitForURL('**/admin/dashboard', { timeout: 30_000 }),
    tenantOption.waitFor({ state: 'visible', timeout: 30_000 }).catch(() => undefined),
  ]);
  if (await tenantOption.isVisible().catch(() => false)) {
    await tenantOption.click();
  }
  await page.waitForURL('**/admin/dashboard', { timeout: 30_000 });
  log('admin signed in at /admin/dashboard');
}

/** Step (8): create CONTEXT B through the real admin console; 409 is idempotent success. */
async function createEmployeeViaAdminConsole(page: Page): Promise<'created' | 'duplicate'> {
  await page.goto(`${ADMIN_URL}/organizations/users`);
  await page.getByRole('button', { name: '新增用户', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible({ timeout: 15_000 });
  await dialog.getByPlaceholder('请输入登录名（登录时使用）').fill(EMPLOYEE_B.loginName);
  await dialog.getByPlaceholder('至少 10 位').fill(EMPLOYEE_B.password);
  await dialog
    .locator('.n-form-item:has(.n-form-item-label__text:text-is("姓名")) .n-input__input-el')
    .fill(EMPLOYEE_B.name);
  await dialog
    .locator('.n-form-item:has(.n-form-item-label__text:text-is("手机号")) .n-input__input-el')
    .fill(EMPLOYEE_B.mobile);
  await dialog
    .locator('.n-form-item:has(.n-form-item-label__text:text-is("邮箱")) .n-input__input-el')
    .fill(EMPLOYEE_B.email);
  await dialog.getByRole('button', { name: '保存' }).click();

  const success = page.locator('.n-message--success-type', { hasText: '用户已创建' });
  const duplicate = page.locator('.n-message--error-type', { hasText: '登录名已存在' });
  const outcome = await Promise.race([
    success
      .waitFor({ state: 'visible', timeout: 30_000 })
      .then(() => 'created' as const)
      .catch(() => 'timeout' as const),
    duplicate
      .waitFor({ state: 'visible', timeout: 30_000 })
      .then(() => 'duplicate' as const)
      .catch(() => 'timeout' as const),
  ]);
  if (outcome === 'duplicate') {
    log('employee B already exists — 409 登录名已存在 treated as idempotent success');
    await dialog.getByRole('button', { name: '取消' }).click();
    await expect(dialog).toBeHidden({ timeout: 15_000 });
  } else if (outcome === 'created') {
    log('employee B created through the admin console');
    await expect(dialog).toBeHidden({ timeout: 15_000 });
  } else {
    throw new Error('admin create-user produced neither 用户已创建 nor 登录名已存在');
  }
  return outcome;
}

/** Fill the login modal WITHOUT navigating (the share token lives in memory only). */
async function fillUserWebLogin(page: Page, username: string, password: string): Promise<void> {
  const usernameInput = page.locator('#movo-login-username');
  await expect(usernameInput).toBeVisible({ timeout: 30_000 });
  await usernameInput.fill(username);
  await page.locator('#movo-login-password').fill(password);
  await page.locator('button[type="submit"]').click();
  await expect(usernameInput).toBeHidden({ timeout: 30_000 });
}

async function loginUser(page: Page, username: string, password: string): Promise<void> {
  await page.goto('/');
  await fillUserWebLogin(page, username, password);
  await expect(page.getByRole('button', { name: '新建对话' })).toBeVisible({ timeout: 30_000 });
  log(`user-web signed in as ${username}`);
}

/**
 * CONTEXT B redeems the share link through the real UI: opening the link logs
 * the visitor out, the login modal appears on the SAME URL, and the token is
 * only held in memory until the post-login auto-join runs. Never navigate again.
 */
async function redeemShare(page: Page, shareUrl: string, username: string, password: string): Promise<void> {
  await page.goto(shareUrl);
  await fillUserWebLogin(page, username, password);
  await expect(page.getByText('分享给我').first()).toBeVisible({ timeout: 30_000 });
  log('share link redeemed; session joined and opened');
}

/** Enter a session via 新建对话, send the first message, and capture X-Session-Id. */
async function createChatSession(page: Page, message: string): Promise<string> {
  await page.getByRole('button', { name: '新建对话' }).click();
  const composer = page.locator(COMPOSER).first();
  await expect(composer).toBeVisible({ timeout: 15_000 });
  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().includes('/askai-api/api/chat/completions') && response.request().method() === 'POST',
    { timeout: 60_000 },
  );
  await composer.fill(message);
  await composer.press('Enter');
  const response = await responsePromise;
  const sessionId = response.headers()['x-session-id'];
  expect(sessionId, 'chat completion response must carry X-Session-Id').toBeTruthy();
  await expect(page.locator('.assistant-content')).toHaveCount(1, { timeout: 60_000 });
  await expect(composer).toBeEnabled({ timeout: 60_000 });
  log(`session created: ${sessionId}`);
  return sessionId as string;
}

/** Send a message into the ACTIVE pane and wait for one more completed assistant row. */
async function sendMessage(page: Page, text: string): Promise<void> {
  const before = await page.locator('.assistant-content').count();
  const composer = page.locator(COMPOSER).first();
  await composer.fill(text);
  await composer.press('Enter');
  await expect(page.locator('.assistant-content')).toHaveCount(before + 1, { timeout: 60_000 });
  await expect(page.getByText(STUB_REPLY).last()).toBeVisible({ timeout: 60_000 });
  await expect(composer).toBeEnabled({ timeout: 60_000 });
  log(`message sent on active pane: "${text}"`);
}

/** Open the share dialog via the header and create the link through the real UI. */
async function createShareLink(page: Page): Promise<{ shareUrl: string; sessionId: string }> {
  await page.locator('[aria-label="分享会话"]').click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible({ timeout: 15_000 });
  const responsePromise = page.waitForResponse(
    (response) =>
      /\/askai-api\/api\/sessions\/[^/]+\/share$/.test(response.url()) &&
      response.request().method() === 'POST',
    { timeout: 30_000 },
  );
  await dialog.getByRole('button', { name: '生成分享链接' }).click();
  const response = await responsePromise;
  const segments = new URL(response.url()).pathname.split('/').filter(Boolean);
  const sessionId = segments[3] || '';
  expect(sessionId, 'share response URL must expose the session id').toBeTruthy();
  const linkInput = dialog.locator('input[readonly]').first();
  await expect(linkInput).toHaveValue(/session-share=/, { timeout: 15_000 });
  const shareUrl = await linkInput.inputValue();
  expect(shareUrl).toContain('session-share=');
  log(`share link created through the UI (session ${sessionId})`);
  return { shareUrl, sessionId };
}

async function assertNoHorizontalOverflow(page: Page, label: string): Promise<void> {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  log(`${label}: horizontal overflow = ${overflow}px`);
  expect(overflow, `${label} must not overflow horizontally`).toBeLessThanOrEqual(2);
}

test.describe.configure({ retries: 0 });

test('T12 step (9): two-context sharing, author identity, member add/remove, live proxy proof', async ({
  browser,
}) => {
  test.setTimeout(600_000);
  const shotSizes: Record<string, number> = {};

  // ---------------------------------------------------------------- step (8)
  const adminContext = await browser.newContext();
  await adminContext.addInitScript(ADMIN_LOCALE_RESET);
  const adminPage = await adminContext.newPage();
  await loginAdmin(adminPage);
  const employeeOutcome = await createEmployeeViaAdminConsole(adminPage);
  log(`create-user outcome: ${employeeOutcome}`);
  await adminContext.close();

  // ------------------------------------------------------- CONTEXT A (owner)
  const contextA = await browser.newContext();
  const pageA = await contextA.newPage();
  pageA.on('console', (message) => log(`[A console ${message.type()}] ${message.text()}`));
  pageA.on('requestfailed', (request) =>
    log(`[A requestfailed] ${request.url()} ${request.failure()?.errorText ?? ''}`),
  );
  pageA.on('response', (response) => {
    if (response.url().includes('/live')) log(`[A live response] ${response.status()} ${response.url()}`);
  });
  await loginUser(pageA, EMPLOYEE_A.username, EMPLOYEE_A.password);
  const sessionId = await createChatSession(pageA, MSG_A);
  const { shareUrl } = await createShareLink(pageA);

  // Header participant count starts at 0 for the owner alone; dialog stays open
  // so the member add is observed live (T10: no reload).
  const participantsButton = pageA.locator('[aria-label$="位成员"]');
  await expect(participantsButton).toHaveAttribute('aria-label', '0 位成员', { timeout: 15_000 });
  const dialogA = pageA.getByRole('dialog');
  await expect(dialogA.locator('.member-row').filter({ hasText: EMPLOYEE_B.name })).toHaveCount(0);

  // -------------------------------------------------- CONTEXT B (participant)
  const contextB = await browser.newContext();
  const pageB = await contextB.newPage();
  pageB.on('response', (response) => {
    if (response.url().includes('/live')) log(`[B live response] ${response.status()} ${response.url()}`);
  });
  await redeemShare(pageB, shareUrl, EMPLOYEE_B.loginName, EMPLOYEE_B.password);
  await expect(messageRow(pageB, MSG_A)).toBeVisible({ timeout: 30_000 });

  // T10 (happy, live update): A's dialog and header refresh WITHOUT a reload.
  await expect(dialogA.locator('.member-row').filter({ hasText: EMPLOYEE_B.name })).toBeVisible({
    timeout: 30_000,
  });
  await expect(participantsButton).toHaveAttribute('aria-label', '1 位成员', { timeout: 30_000 });
  log('member add propagated to owner dialog + header without reload');
  await dialogA.getByRole('button', { name: '关闭' }).click();
  await expect(dialogA).toBeHidden({ timeout: 15_000 });

  // B (viewer) sends a message; A must receive it over the live stream.
  await sendMessage(pageB, MSG_B);
  await expect(messageRow(pageA, MSG_B)).toBeVisible({ timeout: 30_000 });

  // ------------------------------------------------- T09 author identity (both browsers)
  for (const [page, role] of [
    [pageA, 'owner'],
    [pageB, 'viewer'],
  ] as const) {
    const strips = page.locator('[data-user-message-author]');
    await expect(strips).toHaveCount(2, { timeout: 15_000 });
    await expect(strips.filter({ hasText: EMPLOYEE_A.name })).toHaveCount(1);
    await expect(strips.filter({ hasText: EMPLOYEE_B.name })).toHaveCount(1);
    const initials = page.locator('[data-user-message-author] [role="img"]');
    await expect(initials).toHaveCount(2);
    const ariaLabels = await initials.evaluateAll((nodes) =>
      nodes.map((node) => node.getAttribute('aria-label')),
    );
    expect(ariaLabels, `${role} initials aria-labels`).toEqual(
      expect.arrayContaining([EMPLOYEE_A.name, EMPLOYEE_B.name]),
    );
    // No <img> is rendered: every avatar URL here is empty or a relative object path,
    // so the deterministic initials fallback applies and no unsafe image is requested.
    await expect(page.locator('[data-user-message-author] img')).toHaveCount(0);
    log(`${role} author strips: 2 initials avatars, 0 <img>, aria-labels ok`);
  }

  // T09-browser.png — happy path, both authors, owner + viewer views.
  const t09Owner = await pageA.screenshot({ fullPage: true });
  const t09Viewer = await pageB.screenshot({ fullPage: true });
  shotSizes['T09-browser.png'] = await captureSideBySide(
    browser,
    'T09-browser.png',
    [
      { buffer: t09Owner, label: 'CONTEXT A (owner) — both authors’ avatar + display name' },
      { buffer: t09Viewer, label: 'CONTEXT B (viewer/participant) — viewer-authored row included' },
    ],
    { width: 2560, height: 1400 },
  );

  // T09-fallback.png — initials fallback at mobile AND desktop widths, no overflow.
  await pageA.setViewportSize({ width: 390, height: 844 });
  await expect(pageA.locator('[data-user-message-author] [role="img"]').first()).toBeVisible();
  await assertNoHorizontalOverflow(pageA, 'mobile 390px');
  const t09Mobile = await pageA.screenshot({ fullPage: true });
  await pageA.setViewportSize({ width: 1280, height: 800 });
  await assertNoHorizontalOverflow(pageA, 'desktop 1280px');
  const t09Desktop = await pageA.screenshot({ fullPage: true });
  shotSizes['T09-fallback.png'] = await captureSideBySide(
    browser,
    'T09-fallback.png',
    [
      { buffer: t09Mobile, label: 'mobile 390px — initials fallback, long name truncated' },
      { buffer: t09Desktop, label: 'desktop 1280px — initials fallback, no overflow' },
    ],
    { width: 2000, height: 1200 },
  );

  // ------------------------------------------- step (9) live proxy SSE proof
  const probePromise = probeLiveStream(pageA, sessionId, 25_000);
  await pageA.waitForFunction(
    () => (window as unknown as { __t12ProbeOpened?: boolean }).__t12ProbeOpened === true,
    undefined,
    { timeout: 15_000 },
  );
  await sendMessage(pageB, MSG_C);
  const probe = await probePromise;
  log(`live probe: ${JSON.stringify({
    status: probe.status,
    contentType: probe.contentType,
    cacheControl: probe.cacheControl,
    chunks: probe.chunks.map((chunk) => chunk.at),
    heartbeats: probe.heartbeatAtMs,
    turnStarted: probe.sawTurnStarted,
    turnCompleted: probe.sawTurnCompleted,
    eof: probe.eof,
    error: probe.error,
  })}`);
  expect(probe.status, 'bearer auth must be forwarded through /askai-api').toBe(200);
  expect(probe.contentType || '').toContain('text/event-stream');
  expect(probe.cacheControl || '').toContain('no-cache');
  expect(probe.error).toBeNull();
  expect(probe.eof, 'stream must survive a normal turn completion').toBe(false);
  expect(probe.sawTurnStarted, 'turn.started frame observed').toBe(true);
  expect(probe.sawTurnCompleted, 'turn.completed frame observed').toBe(true);
  expect(probe.sawAccessRevoked).toBe(false);
  expect(probe.heartbeatAtMs.length, 'at least one SSE heartbeat comment').toBeGreaterThanOrEqual(1);
  expect(probe.heartbeatAtMs[0], 'heartbeat within the bounded <= 25 s wait').toBeLessThanOrEqual(25_000);
  expect(probe.heartbeatAtMs[0], 'heartbeat on the configured ~15 s interval').toBeGreaterThanOrEqual(10_000);
  expect(probe.chunks.length, 'chunks arrive incrementally, not buffered').toBeGreaterThanOrEqual(2);
  const arrivalTimes = probe.chunks.map((chunk) => chunk.at);
  expect(Math.max(...arrivalTimes) - Math.min(...arrivalTimes)).toBeGreaterThanOrEqual(5_000);
  const dataArrivals = probe.chunks.filter((chunk) => chunk.text.includes('event:')).map((chunk) => chunk.at);
  expect(dataArrivals.length, 'turn frames observed as data chunks').toBeGreaterThanOrEqual(1);
  expect(Math.min(...dataArrivals), 'turn frames precede the heartbeat while the stream stays open').toBeLessThan(
    probe.heartbeatAtMs[0],
  );
  log('live proxy proof: unbuffered, bearer-forwarded, 15 s heartbeat, survives turn completion');

  // -------------------------------------------- T10 happy (add) two browsers
  await pageA.locator('[aria-label="分享会话"]').click();
  await expect(dialogA).toBeVisible({ timeout: 15_000 });
  await expect(dialogA.locator('.member-row').filter({ hasText: EMPLOYEE_B.name })).toBeVisible({
    timeout: 15_000,
  });
  const t10HappyA = await pageA.screenshot({ fullPage: true });
  const t10HappyB = await pageB.screenshot({ fullPage: true });
  shotSizes['T10-browser-happy.png'] = await captureSideBySide(
    browser,
    'T10-browser-happy.png',
    [
      { buffer: t10HappyA, label: 'CONTEXT A (owner) — share dialog lists participant B' },
      { buffer: t10HappyB, label: 'CONTEXT B (participant) — shared session live' },
    ],
    { width: 2560, height: 1400 },
  );

  // ------------------------------------ T10 failure (remove + access loss)
  await dialogA
    .locator('.member-row')
    .filter({ hasText: EMPLOYEE_B.name })
    .getByRole('button', { name: '移除' })
    .click();
  await expect(pageA.locator('.n-message--success-type', { hasText: '已移除该成员' })).toBeVisible({
    timeout: 15_000,
  });
  await expect(dialogA.locator('.member-row').filter({ hasText: EMPLOYEE_B.name })).toBeHidden({
    timeout: 15_000,
  });
  // Participant B loses access: terminal SSE frame -> pane cleared, shared row dropped, notice shown.
  await expect(
    pageB.locator('.n-message--warning-type', { hasText: '你已无法访问该会话。' }),
  ).toBeVisible({ timeout: 20_000 });
  const t10FailureB = await pageB.screenshot({ fullPage: true });
  await expect(messageRow(pageB, MSG_B)).toBeHidden({ timeout: 15_000 });
  // The shared pane is gone entirely: no session header / share control remains.
  // (Do NOT assert the sidebar 分享给我 section disappears — the stack is reused
  // across runs and B can still be a member of sessions from earlier runs.)
  await expect(pageB.locator('[aria-label="分享会话"]')).toHaveCount(0, { timeout: 15_000 });
  const t10FailureA = await pageA.screenshot({ fullPage: true });
  shotSizes['T10-browser-failure.png'] = await captureSideBySide(
    browser,
    'T10-browser-failure.png',
    [
      { buffer: t10FailureA, label: 'CONTEXT A (owner) — member removed, list back to owner only' },
      { buffer: t10FailureB, label: 'CONTEXT B (removed viewer) — access-lost notice, pane cleared' },
    ],
    { width: 2560, height: 1400 },
  );

  for (const [name, size] of Object.entries(shotSizes)) {
    log(`evidence ${name}: ${size} bytes`);
  }
  log(`capture summary: ${JSON.stringify(shotSizes)}`);
  await contextA.close();
  await contextB.close();
});

// ===========================================================================
// T12 lane C — Node-side 20-viewer load case and failure controls (L181-L182)
// ===========================================================================

const RAW_API = `${BASE_URL}/askai-api/api`;
const ADMIN_API = `${BASE_URL}/admin-api/api`;
const LOAD_VIEWERS = 20;
/** Owner-set event-to-frame bar, plan L181 (2026-09-26): p95 <= 2 s. */
const LATENCY_BAR_MS = 2_000;
/** A single reader is INCREMENTAL when its first and last frame are > 1 s apart. */
const INCREMENTAL_SPREAD_MS = 1_000;
const BUFFERING_PROXY_PORT = 18_201;
const BUFFERING_PROXY_FLUSH_SECONDS = 10;
const LOAD_USER_PASSWORD = 'qa-load-pass-2026';

type JsonObject = { [key: string]: unknown };

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function asRecord(value: unknown): JsonObject {
  return typeof value === 'object' && value !== null ? (value as JsonObject) : {};
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' ? value : null;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

async function apiFetch(
  url: string,
  options: { method?: string; token?: string; body?: unknown; signal?: AbortSignal } = {},
): Promise<Response> {
  const headers: Record<string, string> = {};
  if (options.token) headers.Authorization = `Bearer ${options.token}`;
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  return await fetch(url, {
    method: options.method ?? (options.body !== undefined ? 'POST' : 'GET'),
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  });
}

/** API login is the approved way to obtain member tokens for the load case. */
async function apiEndUserLogin(username: string, password: string): Promise<string> {
  const response = await apiFetch(`${RAW_API}/auth/login`, { body: { username, password } });
  expect(response.ok, `end-user login for ${username} -> HTTP ${response.status}`).toBe(true);
  const payload = asRecord(await response.json());
  expect(asNumber(payload.code), `login ${username} code`).toBe(0);
  const token = asString(asRecord(payload.data).token);
  expect(token, `login ${username} must return a token`).not.toBe('');
  return token;
}

async function apiAdminLogin(): Promise<string> {
  const response = await apiFetch(`${ADMIN_API}/auth/login`, { body: ADMIN });
  expect(response.ok, `admin login -> HTTP ${response.status}`).toBe(true);
  const token = asString(asRecord(await response.json()).token);
  expect(token, 'admin login must return a token').not.toBe('');
  return token;
}

/** Seed a session with one paced stub turn and return its id (X-Session-Id). */
async function apiCreateSession(ownerToken: string, text: string): Promise<string> {
  const response = await apiFetch(`${RAW_API}/chat/completions`, {
    token: ownerToken,
    body: { messages: [{ role: 'user', content: text }] },
  });
  expect(response.status, `session seed turn -> HTTP ${response.status}`).toBe(200);
  const sessionId = response.headers.get('x-session-id') ?? '';
  expect(sessionId, 'seed turn must carry X-Session-Id').not.toBe('');
  await response.text(); // drain the POST stream so the seed turn finalizes
  return sessionId;
}

/** Drive ONE turn into an existing session and wait for its POST stream to end. */
async function apiStartTurn(
  ownerToken: string,
  sessionId: string,
  text: string,
): Promise<{ messageId: string; finishedMs: number }> {
  const startedAt = Date.now();
  const response = await apiFetch(`${RAW_API}/chat/completions`, {
    token: ownerToken,
    body: { messages: [{ role: 'user', content: text }], output_spec: { session_id: sessionId } },
  });
  expect(response.status, `turn POST -> HTTP ${response.status}`).toBe(200);
  const messageId = response.headers.get('x-message-id') ?? '';
  await response.text(); // the paced stub turn (~4.5 s) completes here
  return { messageId, finishedMs: Date.now() - startedAt };
}

async function apiShareToken(ownerToken: string, sessionId: string): Promise<string> {
  const response = await apiFetch(`${RAW_API}/sessions/${sessionId}/share`, { token: ownerToken, body: {} });
  expect(response.status, `create share -> HTTP ${response.status}`).toBe(200);
  const token = asString(asRecord(asRecord(await response.json()).data).token);
  expect(token, 'share response must return a token').not.toBe('');
  return token;
}

async function apiJoinShare(viewerToken: string, shareToken: string): Promise<void> {
  const response = await apiFetch(`${RAW_API}/session-shares/${shareToken}/join`, { token: viewerToken, body: {} });
  expect(response.status, `join share -> HTTP ${response.status}`).toBe(200);
  expect(asNumber(asRecord(await response.json()).code), 'join share code').toBe(0);
}

type LoadViewerAccount = { name: string; loginName: string; mobile: string; email: string };

function loadViewerAccount(index: number): LoadViewerAccount {
  const padded = String(index).padStart(2, '0');
  return {
    name: `QA Load ${padded}`,
    loginName: `qa-load-${padded}`,
    mobile: `1390000${String(100 + index)}`,
    email: `qa.load.${padded}@example.com`,
  };
}

/**
 * Create (or reuse; a duplicate-login 409 is success, exactly like pinned step
 * (8)) N user-web identities through the REAL admin API and return one logged-in
 * bearer per viewer. Every viewer joins the share, so all 20 connections are
 * authorized members of ONE shared session.
 */
async function provisionLoadViewers(count: number): Promise<string[]> {
  const adminToken = await apiAdminLogin();
  const departmentsResponse = await apiFetch(`${ADMIN_API}/directory/departments/tree`, { token: adminToken });
  expect(departmentsResponse.ok, `department tree -> HTTP ${departmentsResponse.status}`).toBe(true);
  const departments = asArray(await departmentsResponse.json()).map(asRecord);
  const departmentId = asString(departments[0]?.id);

  const rolesResponse = await apiFetch(`${ADMIN_API}/position-roles`, { token: adminToken });
  expect(rolesResponse.ok, `position roles -> HTTP ${rolesResponse.status}`).toBe(true);
  const roles = asArray(await rolesResponse.json()).map(asRecord);
  const activeRole = roles.find((role) => asString(role.status) === 'active') ?? roles[0];
  const roleId = asString(activeRole?.id);
  expect(departmentId, 'a seeded root department must exist').not.toBe('');
  expect(roleId, 'a seeded active position role must exist').not.toBe('');

  let created = 0;
  let reused = 0;
  for (let index = 1; index <= count; index += 1) {
    const account = loadViewerAccount(index);
    const response = await apiFetch(`${ADMIN_API}/directory/users`, {
      token: adminToken,
      body: {
        ...account,
        primaryDepartmentId: departmentId,
        departmentIds: [departmentId],
        initialPassword: LOAD_USER_PASSWORD,
        primaryRoleId: roleId,
        roleIds: [roleId],
      },
    });
    expect([201, 409], `create ${account.loginName} -> HTTP ${response.status}`).toContain(response.status);
    if (response.status === 201) created += 1;
    else reused += 1;
  }
  log(`load viewers: ${created} created, ${reused} already existed (409 idempotent success)`);

  const tokens: string[] = [];
  for (let index = 1; index <= count; index += 1) {
    tokens.push(await apiEndUserLogin(loadViewerAccount(index).loginName, LOAD_USER_PASSWORD));
  }
  return tokens;
}

// ---------------------------------------------------------------------------
// Node-side SSE reader and the incremental-delivery checker (the "smoke check"
// whose detection power the failure controls prove)
// ---------------------------------------------------------------------------

type NodeFrame = { atMs: number; id: string | null; event: string; data: JsonObject | null };

type NodeStream = {
  status: number;
  contentType: string | null;
  openedAtMs: number;
  frames: NodeFrame[];
  heartbeatsMs: number[];
  eof: boolean;
  aborted: boolean;
  error: string | null;
};

type LiveStreamHandle = {
  label: string;
  stream: NodeStream;
  ready: Promise<void>;
  finished: Promise<void>;
  abort: () => void;
};

function parseSseFrame(raw: string, atMs: number): NodeFrame {
  if (raw.startsWith(':')) return { atMs, id: null, event: '', data: null };
  let id: string | null = null;
  let event = 'message';
  const dataLines: string[] = [];
  for (const line of raw.split('\n')) {
    if (line.startsWith('id:')) id = line.slice(3).trim();
    else if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
  }
  let data: JsonObject | null = null;
  if (dataLines.length > 0) {
    try {
      data = asRecord(JSON.parse(dataLines.join('\n')));
    } catch {
      data = null;
    }
  }
  return { atMs, id, event, data };
}

function openLiveStream(
  sessionId: string,
  token: string,
  options: { baseUrl?: string; label?: string; abortAfterFirstFrame?: boolean } = {},
): LiveStreamHandle {
  const label = options.label ?? 'reader';
  const baseUrl = options.baseUrl ?? BASE_URL;
  const stream: NodeStream = {
    status: 0,
    contentType: null,
    openedAtMs: 0,
    frames: [],
    heartbeatsMs: [],
    eof: false,
    aborted: false,
    error: null,
  };
  const controller = new AbortController();
  let resolveReady: () => void = () => undefined;
  const ready = new Promise<void>((resolve) => {
    resolveReady = resolve;
  });
  const startedAt = Date.now();
  const finished = (async () => {
    try {
      const response = await fetch(`${baseUrl}/askai-api/api/sessions/${sessionId}/live`, {
        method: 'GET',
        headers: { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' },
        signal: controller.signal,
        cache: 'no-store',
      });
      stream.status = response.status;
      stream.contentType = response.headers.get('content-type');
      stream.openedAtMs = Date.now() - startedAt;
      resolveReady();
      if (!response.body) throw new Error(`no response body (HTTP ${response.status})`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      for (;;) {
        const read = await reader.read();
        if (read.done) {
          stream.eof = true;
          break;
        }
        buffer += decoder.decode(read.value, { stream: true });
        let boundary = buffer.indexOf('\n\n');
        while (boundary >= 0) {
          const raw = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          const frame = parseSseFrame(raw, Date.now());
          if (frame.event === '') {
            stream.heartbeatsMs.push(frame.atMs);
          } else {
            stream.frames.push(frame);
            if (options.abortAfterFirstFrame && stream.frames.length === 1) {
              log(`${label}: deliberately aborting mid-turn after the first data frame`);
              controller.abort();
            }
          }
          boundary = buffer.indexOf('\n\n');
        }
      }
      await reader.cancel().catch(() => undefined);
    } catch (error) {
      if (controller.signal.aborted) stream.aborted = true;
      else stream.error = String(error);
    } finally {
      resolveReady();
    }
  })();
  return {
    label,
    stream,
    ready,
    finished: finished.then(() => undefined),
    abort: () => controller.abort(),
  };
}

type StreamAnalysis = {
  label: string;
  status: number;
  contentType: string | null;
  frameCount: number;
  executionFrames: number;
  identities: string[];
  controlFrames: string[];
  streamSeqsIncreasing: boolean;
  executionLatenciesMs: number[];
  spreadMs: number;
  p95LatencyMs: number | null;
  maxLatencyMs: number | null;
  terminalIndex: number;
  heartbeatCount: number;
  heartbeatAfterTerminal: boolean;
  eof: boolean;
  aborted: boolean;
  error: string | null;
};

/**
 * Compare ordered frame IDENTITIES, not cursor values: every frame's opaque
 * `id:` cursor embeds the poll-time revision digest, which may differ between
 * readers and polls, while event ids / message ids / statuses are stable.
 */
function frameIdentity(frame: NodeFrame): string {
  const data = frame.data ?? {};
  if (frame.event === 'turn.started') return `turn.started#${asString(data.message_id)}`;
  if (frame.event === 'execution') {
    return `execution#${asString(data.event_id)}#seq${asNumber(data.stream_seq) ?? '?'}`;
  }
  if (frame.event === 'turn.completed') {
    return `turn.completed#${asString(data.message_id)}#${asString(data.status)}`;
  }
  if (frame.event === 'thread.changed') return `thread.changed#${asString(data.reason)}`;
  if (frame.event === 'members.changed') return 'members.changed';
  return `${frame.event}#${JSON.stringify(data)}`;
}

/** Nearest-rank percentile: rank = ceil(fraction * n), 1-based. */
function percentileNearestRank(values: number[], fraction: number): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((left, right) => left - right);
  const rank = Math.max(1, Math.ceil(fraction * sorted.length));
  return sorted[Math.min(sorted.length, rank) - 1] ?? null;
}

function terminalFrameAtMs(stream: NodeStream): number | null {
  for (let index = stream.frames.length - 1; index >= 0; index -= 1) {
    const frame = stream.frames[index];
    if (frame && frame.event === 'turn.completed') return frame.atMs;
  }
  return null;
}

function hasHeartbeatAfterTerminal(stream: NodeStream): boolean {
  const terminalAt = terminalFrameAtMs(stream);
  return terminalAt !== null && stream.heartbeatsMs.some((at) => at > terminalAt);
}

function analyzeLiveStream(handle: LiveStreamHandle): StreamAnalysis {
  const frames = [...handle.stream.frames];
  const heartbeatsMs = [...handle.stream.heartbeatsMs];
  const executionFrames = frames.filter((frame) => frame.event === 'execution');
  // Event-to-frame latency uses the frame's OWN durable event time (`ts`, epoch
  // ms stamped by the projector) against local Date.now() — same-host clocks.
  const latencies = executionFrames
    .map((frame) => {
      const eventAtMs = asNumber(frame.data?.ts);
      return eventAtMs === null ? null : frame.atMs - eventAtMs;
    })
    .filter((value): value is number => value !== null);
  const streamSeqs = executionFrames.map((frame) => asNumber(frame.data?.stream_seq) ?? -1);
  const terminalIndex = frames.findIndex((frame) => frame.event === 'turn.completed');
  const terminalAt = terminalIndex >= 0 ? frames[terminalIndex]?.atMs ?? null : null;
  const firstAt = frames.length > 0 ? frames[0]?.atMs ?? null : null;
  const lastAt = frames.length > 0 ? frames[frames.length - 1]?.atMs ?? null : null;
  return {
    label: handle.label,
    status: handle.stream.status,
    contentType: handle.stream.contentType,
    frameCount: frames.length,
    executionFrames: executionFrames.length,
    identities: frames.map(frameIdentity),
    controlFrames: frames
      .filter((frame) => frame.event === 'thread.changed' || frame.event === 'members.changed')
      .map(frameIdentity),
    streamSeqsIncreasing: streamSeqs.every(
      (seq, index) => index === 0 || seq > (streamSeqs[index - 1] ?? Number.NEGATIVE_INFINITY),
    ),
    executionLatenciesMs: latencies,
    spreadMs: firstAt !== null && lastAt !== null ? lastAt - firstAt : 0,
    p95LatencyMs: percentileNearestRank(latencies, 0.95),
    maxLatencyMs: latencies.length > 0 ? Math.max(...latencies) : null,
    terminalIndex,
    heartbeatCount: heartbeatsMs.length,
    heartbeatAfterTerminal: terminalAt !== null && heartbeatsMs.some((at) => at > terminalAt),
    eof: handle.stream.eof,
    aborted: handle.stream.aborted,
    error: handle.stream.error,
  };
}

/**
 * The incremental-delivery contract (plan L182 "the unbuffered assertion"): a
 * healthy SSE reader sees the turn arrive across separated polls, ends on the
 * terminal marker, and is never EOF/aborted/errored. A buffered path violates
 * exactly this by delivering everything in one late flush.
 */
function incrementalDeliveryReasons(analysis: StreamAnalysis): string[] {
  const reasons: string[] = [];
  if (analysis.status !== 200) reasons.push(`status=${analysis.status}`);
  if (analysis.error) reasons.push(`error=${analysis.error}`);
  if (analysis.terminalIndex < 0) {
    reasons.push(analysis.aborted || analysis.eof ? 'interrupted-before-terminal' : 'missing-terminal');
  }
  if (analysis.spreadMs < INCREMENTAL_SPREAD_MS) reasons.push(`clustered(spread=${analysis.spreadMs}ms)`);
  return reasons;
}

// ---------------------------------------------------------------------------
// Failure control (a): a local, deliberately BUFFERING proxy — stdlib python,
// written under the OS temp dir at test time so no artifact enters the worktree.
// ---------------------------------------------------------------------------

const BUFFERING_PROXY_SOURCE = String.raw`#!/usr/bin/env python3
"""T12 failure control: a deliberately BUFFERING SSE proxy (stdlib only).

Accumulates every upstream response byte and flushes it as ONE batch at
FLUSH_AFTER_SECONDS, so the incremental-delivery checker MUST flag this path as
clustered/stale while the direct path passes. Local QA control only; it forwards
GET requests (Authorization/Accept/Last-Event-ID) to the real gateway.
"""
import http.server
import sys
import threading
import time
import urllib.request

UPSTREAM = sys.argv[1]
PORT = int(sys.argv[2])
FLUSH_AFTER_SECONDS = float(sys.argv[3])


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "t12-buffering-proxy"

    def log_message(self, fmt, *args):
        sys.stderr.write("buffering-proxy: " + (fmt % args) + "\n")
        sys.stderr.flush()

    def do_GET(self):
        if self.path == "/healthz":
            body = b'{"status":"ok","proxy":"buffering"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        request = urllib.request.Request(UPSTREAM + self.path)
        for name in ("Authorization", "Accept", "Last-Event-ID"):
            value = self.headers.get(name)
            if value is not None:
                request.add_header(name, value)
        try:
            upstream = urllib.request.urlopen(request, timeout=120)
        except Exception as exc:
            self.send_response(502)
            self.send_header("Content-Length", "0")
            self.end_headers()
            self.log_message("upstream error %r", exc)
            return
        self.send_response(200)
        self.send_header("Content-Type", upstream.headers.get("Content-Type") or "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        state = {"buffer": bytearray(), "closed": False}
        lock = threading.Lock()
        deadline = time.monotonic() + FLUSH_AFTER_SECONDS

        def flusher():
            while True:
                time.sleep(0.05)
                payload = b""
                with lock:
                    if state["buffer"] and (state["closed"] or time.monotonic() >= deadline):
                        payload = bytes(state["buffer"])
                        state["buffer"].clear()
                if payload:
                    try:
                        self.wfile.write(payload)
                        self.wfile.flush()
                    except Exception:
                        with lock:
                            state["closed"] = True
                with lock:
                    if state["closed"] and not state["buffer"]:
                        return

        pump = threading.Thread(target=flusher, daemon=True)
        pump.start()
        try:
            while True:
                chunk = upstream.read1(4096)
                if not chunk:
                    break
                with lock:
                    state["buffer"] += chunk
        except Exception as exc:
            self.log_message("read error %r", exc)
        finally:
            with lock:
                state["closed"] = True
            pump.join(timeout=5)
            self.close_connection = True


def main():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.daemon_threads = True
    print("buffering-proxy listening on 127.0.0.1:%d -> %s" % (PORT, UPSTREAM), file=sys.stderr, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
`;

async function startBufferingProxy(
  upstreamBase: string,
  port: number,
  flushAfterSeconds: number,
): Promise<{ stop: () => void }> {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 't12-buffering-proxy-'));
  const scriptPath = path.join(directory, 't12_buffering_proxy.py');
  fs.writeFileSync(scriptPath, BUFFERING_PROXY_SOURCE);
  const child = spawn('python3', [scriptPath, upstreamBase, String(port), String(flushAfterSeconds)], {
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  child.stderr?.on('data', (chunk: Buffer) => log(`[buffering-proxy] ${chunk.toString().trim()}`));
  child.on('exit', (code) => log(`[buffering-proxy] exited with code ${code}`));

  let ready = false;
  const deadline = Date.now() + 15_000;
  while (!ready && Date.now() < deadline) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/healthz`);
      ready = response.ok;
    } catch {
      ready = false;
    }
    if (!ready) await delay(200);
  }
  expect(ready, `buffering proxy must become ready on 127.0.0.1:${port}`).toBe(true);
  log(`buffering proxy ready on 127.0.0.1:${port} (flush after ${flushAfterSeconds}s; script ${scriptPath})`);
  return {
    stop: () => {
      child.kill('SIGTERM');
      try {
        fs.rmSync(directory, { recursive: true, force: true });
      } catch {
        log('buffering proxy temp dir cleanup failed (best effort)');
      }
    },
  };
}

// ---------------------------------------------------------------------------
// P1 — the 20-viewer load case (plan L181)
// ---------------------------------------------------------------------------

test('T12 load: 20 concurrent viewers receive one identical frame sequence (p95 <= 2 s) and all streams stay held', async () => {
  test.setTimeout(420_000);
  const ownerToken = await apiEndUserLogin(EMPLOYEE_A.username, EMPLOYEE_A.password);
  const sessionId = await apiCreateSession(ownerToken, 'T12 load-case seed turn');
  const shareToken = await apiShareToken(ownerToken, sessionId);
  log(`load: session ${sessionId} seeded and shared (share token ${shareToken.length} chars)`);

  const viewerTokens = await provisionLoadViewers(LOAD_VIEWERS);
  for (const viewerToken of viewerTokens) await apiJoinShare(viewerToken, shareToken);
  log(`load: ${viewerTokens.length} distinct viewer members joined the shared session`);

  const readers = viewerTokens.map((viewerToken, index) =>
    openLiveStream(sessionId, viewerToken, { label: `viewer-${String(index + 1).padStart(2, '0')}` }),
  );
  await Promise.all(readers.map((reader) => reader.ready));
  const badStatuses = readers
    .filter((reader) => reader.stream.status !== 200)
    .map((reader) => `${reader.label}:${reader.stream.status}`);
  expect(badStatuses, 'every viewer stream must attach with HTTP 200').toEqual([]);
  log(`load: all ${readers.length} viewer streams attached (HTTP 200)`);
  // Let every connection finish its first (empty) poll before the turn exists,
  // so all 20 cold-attach to the same active run and replay it from position 0.
  await delay(2_000);

  const turn = await apiStartTurn(ownerToken, sessionId, 'T12 load-case viewer turn');
  log(`load: turn ${turn.messageId} completed after ${turn.finishedMs} ms on the POST stream`);

  const terminalDeadline = Date.now() + 30_000;
  while (
    readers.some((reader) => reader.stream.frames.every((frame) => frame.event !== 'turn.completed')) &&
    Date.now() < terminalDeadline
  ) {
    await delay(250);
  }
  const heartbeatDeadline = Date.now() + 45_000;
  while (readers.some((reader) => !hasHeartbeatAfterTerminal(reader.stream)) && Date.now() < heartbeatDeadline) {
    await delay(250);
  }

  const analyses = readers.map((reader) => analyzeLiveStream(reader));
  const reference = analyses[0];
  expect(reference, 'at least one viewer analysis').toBeTruthy();

  for (const analysis of analyses) {
    expect(analysis.status, `${analysis.label} status`).toBe(200);
    expect(analysis.contentType ?? '', `${analysis.label} content type`).toContain('text/event-stream');
    expect(analysis.error, `${analysis.label} error`).toBeNull();
    expect(analysis.eof, `${analysis.label} must not have been closed by the gateway`).toBe(false);
    expect(analysis.aborted, `${analysis.label} must still be open (not aborted)`).toBe(false);
    expect(analysis.terminalIndex, `${analysis.label} must see turn.completed`).toBeGreaterThanOrEqual(0);
    expect(analysis.heartbeatAfterTerminal, `${analysis.label} must observe a heartbeat AFTER turn.completed`).toBe(
      true,
    );
    expect(analysis.identities, `${analysis.label} ordered frame identities must equal the reference`).toEqual(
      reference.identities,
    );
    expect(analysis.identities[0] ?? '', `${analysis.label} first frame`).toContain('turn.started');
    expect(analysis.identities[analysis.identities.length - 1] ?? '', `${analysis.label} last frame`).toContain(
      'turn.completed',
    );
    expect(analysis.controlFrames, `${analysis.label} must see no control frames`).toEqual([]);
    expect(analysis.streamSeqsIncreasing, `${analysis.label} execution stream_seq must be strictly increasing`).toBe(
      true,
    );
    expect(analysis.executionFrames, `${analysis.label} must carry execution frames`).toBeGreaterThan(0);
    log(
      `load ${analysis.label}: frames=${analysis.frameCount} spread=${analysis.spreadMs}ms ` +
        `p95=${analysis.p95LatencyMs}ms max=${analysis.maxLatencyMs}ms heartbeats=${analysis.heartbeatCount} ` +
        `hbAfterTerminal=${analysis.heartbeatAfterTerminal} eof=${analysis.eof}`,
    );
  }

  const latencies = analyses.flatMap((analysis) => analysis.executionLatenciesMs);
  const p95 = percentileNearestRank(latencies, 0.95);
  expect(latencies.length, 'event-to-frame latency samples').toBeGreaterThanOrEqual(LOAD_VIEWERS);
  expect(p95 ?? Number.POSITIVE_INFINITY, 'p95 event-to-frame latency must be <= 2000 ms').toBeLessThanOrEqual(
    LATENCY_BAR_MS,
  );
  expect(Math.min(...latencies), 'same-host clocks cannot produce a negative latency beyond rounding').toBeGreaterThanOrEqual(
    -50,
  );

  log(`load sequence (identical on all ${analyses.length} viewers): ${reference.identities.join(' | ')}`);
  log(
    `load latency: samples=${latencies.length} p50=${percentileNearestRank(latencies, 0.5)}ms p95=${p95}ms ` +
      `max=${Math.max(...latencies)}ms min=${Math.min(...latencies)}ms`,
  );
  log(
    `load summary: ${JSON.stringify({
      viewers: analyses.length,
      framesPerViewer: reference.frameCount,
      sequenceLength: reference.identities.length,
      latencySamples: latencies.length,
      p50Ms: percentileNearestRank(latencies, 0.5),
      p95Ms: p95,
      maxMs: Math.max(...latencies),
      allStreamsOpen: analyses.every((analysis) => !analysis.eof && !analysis.aborted && analysis.error === null),
      heartbeatsAfterTurn: analyses.every((analysis) => analysis.heartbeatAfterTerminal),
    })}`,
  );

  for (const reader of readers) reader.abort();
  await Promise.all(readers.map((reader) => reader.finished));
});

// ---------------------------------------------------------------------------
// P2 — failure-case negative controls (plan L182)
// ---------------------------------------------------------------------------

test('T12 failure controls: proxy buffering, invalid auth, and an interrupted stream are all detected', async () => {
  test.setTimeout(300_000);
  const ownerToken = await apiEndUserLogin(EMPLOYEE_A.username, EMPLOYEE_A.password);
  const sessionId = await apiCreateSession(ownerToken, 'T12 failure-control seed turn');
  log(`failure: control session ${sessionId} seeded`);

  const proxy = await startBufferingProxy(BASE_URL, BUFFERING_PROXY_PORT, BUFFERING_PROXY_FLUSH_SECONDS);
  try {
    // (a) proxy buffering: one turn read through the DIRECT path and through the
    // BUFFERING proxy; the same checker must pass one and fail the other.
    const direct = openLiveStream(sessionId, ownerToken, { label: 'direct' });
    const buffered = openLiveStream(sessionId, ownerToken, {
      baseUrl: `http://127.0.0.1:${BUFFERING_PROXY_PORT}`,
      label: 'buffered-proxy',
    });
    const interrupted = openLiveStream(sessionId, ownerToken, { label: 'interrupted', abortAfterFirstFrame: true });
    await Promise.all([direct.ready, buffered.ready, interrupted.ready]);
    expect(direct.stream.status, 'direct attach').toBe(200);
    expect(buffered.stream.status, 'buffered attach').toBe(200);
    expect(interrupted.stream.status, 'interrupted attach').toBe(200);
    await delay(2_000);

    const turn = await apiStartTurn(ownerToken, sessionId, 'T12 failure-control turn');
    log(`failure: turn ${turn.messageId} completed after ${turn.finishedMs} ms`);

    const directDeadline = Date.now() + 30_000;
    while (
      direct.stream.frames.every((frame) => frame.event !== 'turn.completed') &&
      Date.now() < directDeadline
    ) {
      await delay(250);
    }
    const bufferedDeadline = Date.now() + 30_000;
    while (buffered.stream.frames.length === 0 && Date.now() < bufferedDeadline) {
      await delay(250);
    }
    await delay(1_000); // let the single buffered flush settle before snapshotting

    const directAnalysis = analyzeLiveStream(direct);
    const bufferedAnalysis = analyzeLiveStream(buffered);
    const interruptedAnalysis = analyzeLiveStream(interrupted);
    const directReasons = incrementalDeliveryReasons(directAnalysis);
    const bufferedReasons = incrementalDeliveryReasons(bufferedAnalysis);
    const interruptedReasons = incrementalDeliveryReasons(interruptedAnalysis);

    log(
      `failure direct: frames=${directAnalysis.frameCount} spread=${directAnalysis.spreadMs}ms ` +
        `p95=${directAnalysis.p95LatencyMs}ms terminal=${directAnalysis.terminalIndex} ` +
        `reasons=${JSON.stringify(directReasons)}`,
    );
    log(
      `failure buffered: frames=${bufferedAnalysis.frameCount} spread=${bufferedAnalysis.spreadMs}ms ` +
        `p95=${bufferedAnalysis.p95LatencyMs}ms terminal=${bufferedAnalysis.terminalIndex} ` +
        `reasons=${JSON.stringify(bufferedReasons)}`,
    );
    log(`failure buffered sequence (same turn, delivered as one late flush): ${bufferedAnalysis.identities.join(' | ')}`);
    log(
      `failure interrupted: frames=${interruptedAnalysis.frameCount} aborted=${interruptedAnalysis.aborted} ` +
        `eof=${interruptedAnalysis.eof} terminal=${interruptedAnalysis.terminalIndex} ` +
        `reasons=${JSON.stringify(interruptedReasons)}`,
    );

    expect(directReasons, 'unbuffered direct path must PASS the incremental contract').toEqual([]);
    expect(bufferedReasons, 'buffered path must FAIL the incremental contract (detected, never a false pass)').not.toEqual(
      [],
    );
    expect(
      bufferedReasons.some((reason) => reason.startsWith('clustered')),
      'the buffered run is detected as a clustered late flush',
    ).toBe(true);
    expect(
      bufferedAnalysis.identities,
      'the buffered path delivers the SAME complete turn, differing only in delivery timing',
    ).toEqual(directAnalysis.identities);
    expect(
      bufferedAnalysis.p95LatencyMs ?? 0,
      'the buffered path also violates the load-case p95 <= 2 s bar',
    ).toBeGreaterThan(LATENCY_BAR_MS);
    expect(bufferedReasons, 'buffered path must not be misread as an interruption').not.toContain(
      'interrupted-before-terminal',
    );

    expect(interruptedAnalysis.frameCount, 'interrupted reader received at least one data frame first').toBeGreaterThan(
      0,
    );
    expect(interruptedAnalysis.terminalIndex, 'interrupted reader never sees the terminal marker').toBe(-1);
    expect(interruptedAnalysis.aborted || interruptedAnalysis.eof, 'interrupted reader ended through abort/EOF').toBe(
      true,
    );
    expect(interruptedReasons, 'checker must flag the interruption instead of reporting success').toContain(
      'interrupted-before-terminal',
    );

    direct.abort();
    buffered.abort();
    await Promise.all([direct.finished, buffered.finished, interrupted.finished]);
  } finally {
    proxy.stop();
  }

  // (b) invalid/expired auth must be a detected 401, not a silent pass. An
  // unissued but structurally valid token follows the same server path an
  // expired/revoked session token does: the token id resolves to no session.
  const authCases: { label: string; token?: string }[] = [
    { label: 'malformed', token: 'not-a-movo-token' },
    { label: 'unissued (expired/revoked-like)', token: 'u.0000000000000000000000000000000000000000.deadbeef' },
    { label: 'anonymous (no Authorization header)' },
  ];
  for (const authCase of authCases) {
    const response = await apiFetch(`${RAW_API}/sessions/${sessionId}/live`, { token: authCase.token });
    expect(response.status, `${authCase.label} bearer must be rejected with 401`).toBe(401);
    const detail = asRecord(await response.json().catch(() => ({}))).detail;
    log(`failure auth ${authCase.label}: HTTP ${response.status} detail=${JSON.stringify(detail ?? null)}`);
  }

  // The final configuration must keep the direct path green and the external
  // evidence root OUTSIDE the implementation worktree (plan L182).
  const evidenceRoot = path.resolve(EVIDENCE_ROOT);
  expect(evidenceRoot.includes(`${path.sep}worktrees${path.sep}`), 'evidence root must not live under a worktree').toBe(
    false,
  );
  expect(process.cwd().startsWith(evidenceRoot), 'evidence root must not contain the spec working directory').toBe(
    false,
  );
  log(`failure: evidence root ${evidenceRoot} is outside the implementation worktree`);
});
