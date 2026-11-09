import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, beforeAll, vi } from "vitest";

afterEach(() => {
  cleanup();
});

// Suppress React Router v7 future-flag console warnings in tests.
// The warnings are informational (not errors) and are suppressed in the
// production app via the future flags on BrowserRouter in App.tsx.
beforeAll(() => {
  const originalWarn = console.warn.bind(console);
  console.warn = (...args: unknown[]) => {
    const msg = args[0];
    if (
      typeof msg === "string" &&
      msg.includes("React Router Future Flag Warning")
    ) {
      return;
    }
    originalWarn(...args);
  };
});

afterEach(() => {
  cleanup();
});

// jsdom does not implement matchMedia; Radix and responsive helpers rely on it.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Radix Dialog/Select call these DOM APIs which jsdom lacks.
if (!window.HTMLElement.prototype.hasPointerCapture) {
  window.HTMLElement.prototype.hasPointerCapture = vi.fn();
}
if (!window.HTMLElement.prototype.releasePointerCapture) {
  window.HTMLElement.prototype.releasePointerCapture = vi.fn();
}
if (!window.HTMLElement.prototype.scrollIntoView) {
  window.HTMLElement.prototype.scrollIntoView = vi.fn();
}
