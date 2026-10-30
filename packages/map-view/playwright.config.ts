import { defineConfig, devices } from '@playwright/test';

// Visual, accessibility and performance checks of the built map-view (npm run build first).
// The API is mocked with responses recorded from core (tests/visual/api.json).
export default defineConfig({
  testDir: 'tests/visual',
  outputDir: 'test-results',
  snapshotPathTemplate: '{testDir}/__screenshots__/{arg}-{projectName}{ext}',
  expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.01 } },
  fullyParallel: true,
  reporter: [['list']],
  use: { baseURL: 'http://127.0.0.1:4179', viewport: { width: 1280, height: 860 } },
  webServer: {
    command: 'npx vite preview --port 4179 --strictPort --host 127.0.0.1',
    url: 'http://127.0.0.1:4179',
    reuseExistingServer: true,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 860 } } }],
});
