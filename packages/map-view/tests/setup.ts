import '@testing-library/jest-dom/vitest';

// jsdom has no canvas; the terrain map draws nothing there but must not crash.
HTMLCanvasElement.prototype.getContext = (() => null) as unknown as HTMLCanvasElement['getContext'];
