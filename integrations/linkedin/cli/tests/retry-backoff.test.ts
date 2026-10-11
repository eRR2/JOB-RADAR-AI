import { afterEach, describe, expect, test } from "bun:test";
import { htmlFetch } from "../src/helpers";
// JOB-RADAR safety contract supersedes upstream retry/backoff semantics.
const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });
describe("htmlFetch refuses retry and bypass", () => {
  for (const status of [401, 403, 429, 999, 302, 500, 404]) {
    test(`HTTP ${status} fails after exactly one request`, async () => {
      let calls = 0;
      globalThis.fetch = (async () => { calls++; return new Response("", {status}); }) as typeof fetch;
      await expect(htmlFetch("https://www.linkedin.com/x")).rejects.toThrow(String(status));
      expect(calls).toBe(1);
    });
  }
  test("redirects are not followed and CAPTCHA stops a successful HTTP response", async () => {
    let options: RequestInit | undefined;
    globalThis.fetch = (async (_url, init) => { options = init; return new Response("captcha challenge"); }) as typeof fetch;
    await expect(htmlFetch("https://www.linkedin.com/x")).rejects.toThrow("ACCESS_RESTRICTED");
    expect(options?.redirect).toBe("manual");
  });
});
