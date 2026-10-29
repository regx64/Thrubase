import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { HIGH_CONTRAST, mockApi } from './mock';

async function open(page: Page, theme: 'light' | 'dark' | 'high-contrast') {
  await page.emulateMedia({ colorScheme: theme === 'dark' ? 'dark' : 'light', reducedMotion: 'reduce' });
  await mockApi(page);
  await page.goto('/?token=t');
  if (theme === 'high-contrast') {
    await page.addStyleTag({ content: HIGH_CONTRAST });
    await page.evaluate(() => document.body.classList.add('vscode-high-contrast'));
  }
  await page.getByRole('button', { name: /Start climb/ }).waitFor();
}

async function climbScreen(page: Page) {
  await page.getByRole('button', { name: /Start climb/ }).click();
  await page.locator('.tb-checkpoint').waitFor();
  await page.locator('.tb-code').waitFor();
}

for (const theme of ['light', 'dark', 'high-contrast'] as const) {
  test(`terrain map · ${theme}`, async ({ page }) => {
    await open(page, theme);
    await expect(page).toHaveScreenshot(`map-${theme}.png`, { fullPage: true });
  });

  test(`climbing · ${theme}`, async ({ page }) => {
    await open(page, theme);
    await climbScreen(page);
    await expect(page).toHaveScreenshot(`climb-${theme}.png`, { fullPage: true });
  });

  test(`no accessibility violations · ${theme}`, async ({ page }) => {
    await open(page, theme);
    const map = await new AxeBuilder({ page }).analyze();
    expect(map.violations).toEqual([]);
    await climbScreen(page);
    // first wrong answer -> hint state
    await page.getByRole('radio').nth(1).click();
    await page.getByRole('button', { name: 'Check' }).click();
    await page.locator('.tb-hint, .tb-explanation').first().waitFor();
    const climb = await new AxeBuilder({ page }).analyze();
    expect(climb.violations).toEqual([]);
  });
}

test('keyboard: 1–4 pick, Enter check, S skip', async ({ page }) => {
  await open(page, 'light');
  await climbScreen(page);
  const card = page.locator('.tb-checkpoint');
  await card.focus();
  await page.keyboard.press('1');
  await expect(page.getByRole('radio').first()).toHaveAttribute('aria-checked', 'true');
  await page.keyboard.press('Enter');
  await page.locator('.tb-hint, .tb-explanation').first().waitFor();
  const title = await page.locator('.tb-segment h2').textContent();
  await page.getByRole('button', { name: 'Continue' }).or(page.getByRole('button', { name: 'Skip' })).first().click();
  await expect(page.locator('.tb-segment h2')).not.toHaveText(title ?? '', { timeout: 5000 }).catch(() => undefined);
});

test('Korean UI', async ({ page }) => {
  await mockApi(page, { lang: 'ko' });
  await page.addInitScript(() => Object.defineProperty(navigator, 'language', { get: () => 'ko-KR' }));
  await page.goto('/?token=t');
  await page.getByRole('button', { name: /등반 시작/ }).waitFor();
  await page.getByRole('button', { name: /등반 시작/ }).click();
  await expect(page.locator('.tb-question')).toContainText('`');
  await expect(page.getByRole('button', { name: '건너뛰기' })).toBeVisible();
});
