const { test, expect } = require('@playwright/test');
const catalog = require('../../agent/PhoneBox.Agent/widgets.json');
const desk = process.env.PHONEBOX_PWA_TEST_LOCAL;
const https = process.env.PHONEBOX_PWA_TEST_URL;
const headers = { 'X-PhoneBox-Panel': '1' };

async function pair(page, request, name) {
  const result = await request.post(desk + '/pwa/manage/pair', { headers });
  expect(result.ok()).toBeTruthy();
  const { link, code } = await result.json();
  await page.goto(link);
  await expect(page.getByLabel('Pairing code')).toHaveValue(code);
  expect(new URL(page.url()).hash).toBe('');
  await page.getByLabel('Device name').fill(name);
  await page.getByRole('button', { name: 'Pair', exact: true }).click();
  await expect(page.locator('body')).toHaveAttribute('data-pwa-session', 'paired');
  await expect(page.locator('.pwa-setup')).toBeHidden();
}

async function updateSettings(request, update) {
  const settings = await request.get(desk + '/api/settings');
  const config = await settings.json();
  update(config);
  const result = await request.put(desk + '/api/settings', {
    headers: { 'X-Config-Version': settings.headers()['x-config-version'] }, data: config,
  });
  expect(result.ok()).toBeTruthy();
}

test('installed shell, live agent, offline recovery, two sessions and revocation', async ({ browser, request }, info) => {
  const first = await browser.newContext({ viewport: { width: 780, height: 360 } });
  const second = await browser.newContext({ viewport: { width: 820, height: 1180 } });
  try {
    const page = await first.newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.goto(https + '/panel/');
    await expect(page.getByRole('heading', { name: 'Pair PhoneBox' })).toBeVisible();
    await expect(page.locator('link[rel="manifest"]')).toHaveAttribute('href', 'manifest.webmanifest');
    await expect(page.locator('meta[name="apple-mobile-web-app-capable"]')).toHaveAttribute('content', 'yes');

    await pair(page, request, 'PWA iPhone Chromium');
    await expect.poll(() => page.evaluate(async () => (await import('/panel/main.js')).streamOn)).toBe(true);
    await expect.poll(() => page.evaluate(async () => (await import('/panel/main.js')).D.state?.pc?.ramTotalGb || 0)).toBeGreaterThan(0);
    await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true);

    const kinds = await page.evaluate(async () => {
      const names = await caches.keys();
      const keys = await (await caches.open(names.find((n) => n.startsWith('phonebox-panel-')))).keys();
      return keys.map((r) => new URL(r.url).pathname);
    });
    expect(kinds).toContain('/panel/');
    expect(kinds).toContain('/panel/widgets/stack.js');
    expect(kinds.every((url) => url.startsWith('/panel/'))).toBe(true);

    const reference = await first.newPage();
    await reference.setViewportSize({ width: 780, height: 360 });
    await reference.goto(desk + '/panel/');
    const geometry = (p) => p.locator('.page[data-id="home"] .w').evaluateAll((items) =>
      items.map((el) => [el.className, el.offsetLeft, el.offsetTop, el.offsetWidth, el.offsetHeight]));
    await expect.poll(() => geometry(reference)).toEqual(await geometry(page));
    await reference.screenshot({ path: info.outputPath('reference-780x360.png') });
    await reference.close();

    for (const [width, height] of [[780, 360], [402, 874], [874, 402], [820, 1180], [1180, 820]]) {
      await page.setViewportSize({ width, height });
      await expect.poll(() => page.evaluate(() => document.querySelector('.page').offsetHeight)).toBe(height);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
      await page.screenshot({ path: info.outputPath(`pwa-${width}x${height}.png`) });
    }

    const other = await second.newPage();
    await pair(other, request, 'PWA iPad Chromium');
    await expect.poll(() => other.evaluate(async () => (await import('/panel/main.js')).streamOn)).toBe(true);
    await expect.poll(() => page.evaluate(async () => (await import('/panel/main.js')).streamOn)).toBe(true);
    await first.setOffline(true);
    await page.reload();
    await expect(page.locator('.page[data-id="home"]')).toBeVisible();
    await expect(page.locator('#offline')).toBeVisible();
    expect(await page.evaluate(async () => (await import('/panel/main.js')).D.state)).toBeNull();
    await first.setOffline(false);
    await expect.poll(() => page.evaluate(async () => (await import('/panel/main.js')).streamOn)).toBe(true);
    await expect(page.locator('#offline')).toBeHidden();

    const data = await (await request.get(desk + '/pwa/manage')).json();
    const device = data.devices.find((d) => d.name === 'PWA iPhone Chromium');
    await request.delete(desk + '/pwa/manage/' + device.id, { headers });
    await expect(page.getByRole('heading', { name: 'Pair PhoneBox' })).toBeVisible();
    await expect.poll(() => other.evaluate(async () => (await import('/panel/main.js')).streamOn)).toBe(true);
    expect(errors).toEqual([]);
  } finally {
    await first.close();
    await second.close();
  }
});

test('renders every original catalogue widget from real agent settings and synchronizes edits', async ({ page, request }) => {
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await pair(page, request, 'PWA catalogue Chromium');
  await updateSettings(request, (config) => {
    config.pages = catalog.map((w) => ({
      id: 'test-' + w.type, title: w.name, enabled: true,
      widgets: [{ id: w.type, type: w.type, x: 0, y: 0, w: w.w, h: w.h,
        options: Object.fromEntries(w.options.filter((o) => o.default !== undefined).map((o) => [o.key, o.default])) }],
    }));
  });

  await expect(page.locator('.page > .grid > .w')).toHaveCount(catalog.length);
  for (const w of catalog) await expect(page.locator('.page[data-id="test-' + w.type + '"] .w-' + w.type)).toHaveCount(1);
  const broken = await page.locator('.page > .grid > .w > .empty').evaluateAll((items) =>
    items.map((el) => el.textContent).filter((value) => /^[a-z]+: /.test(value)));
  expect(broken).toEqual([]);
  expect(errors).toEqual([]);
});

test('note editing persists as text through the existing agent configuration', async ({ page, request }) => {
  await updateSettings(request, (config) => {
    config.pages = [{ id: 'pwa-note', enabled: true, title: 'Test note', widgets: [
      { id: 'note', type: 'note', x: 0, y: 0, w: 6, h: 4, options: { text: 'Before' } },
    ] }];
  });
  await pair(page, request, 'PWA note Chromium');
  await page.locator('.w-note').click();
  const text = '<img src=x onerror="window.pwaTestInjected=true">';
  await page.locator('.note-ta').fill(text);
  await page.locator('.note-actions button').last().click();
  await expect(page.locator('.w-note')).toHaveText(text);
  await page.reload();
  await expect(page.locator('.w-note')).toHaveText(text);
  expect(await page.evaluate(() => window.pwaTestInjected)).toBeUndefined();
});
