// CLI argument tests must never send network requests, including valid flags.
globalThis.fetch = (async () => new Response("", { status: 200 })) as typeof fetch;
