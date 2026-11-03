/** jsdom has no ResizeObserver, DOMMatrix or matchMedia, which React Flow and the phone check use. */
export function installBrowserShims(options: { phone?: boolean } = {}): void {
  class Observer {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  Object.assign(globalThis, { ResizeObserver: Observer });
  if (!("DOMMatrixReadOnly" in globalThis)) {
    class Matrix {
      m22 = 1;
      constructor(public transform?: string) {}
    }
    Object.assign(globalThis, { DOMMatrixReadOnly: Matrix });
  }
  window.matchMedia = ((query: string) => ({
    matches: Boolean(options.phone) && query.includes("max-width"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia;
}
