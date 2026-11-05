// Test-only preload. Production code neither imports this file nor reads its variable.
const fixture = new URL(process.env.AIHUB_TEST_ORIGIN);
if (fixture.protocol !== 'http:' || fixture.hostname !== '127.0.0.1' || !fixture.port ||
    fixture.username || fixture.password || fixture.pathname !== '/' || fixture.search || fixture.hash) {
  throw new Error('Offline fixture requires an explicit loopback HTTP origin.');
}
const originalFetch = globalThis.fetch;
globalThis.fetch = (input, init) => {
  const url = new URL(input instanceof Request ? input.url : input);
  if (url.origin === 'https://api.aihubmax.com') {
    const destination = new URL(url.pathname + url.search, fixture);
    return originalFetch(input instanceof Request ? new Request(destination, input) : destination, init);
  }
  if (url.protocol === 'http:' && url.hostname === '127.0.0.1') return originalFetch(input, init);
  throw new Error('Offline fixture blocked a non-fixture network request.');
};
