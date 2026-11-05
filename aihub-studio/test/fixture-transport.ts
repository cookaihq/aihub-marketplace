/** Route the real CLI's fixed service requests to an offline fixture server. */
export function fixtureTransport(base: string): NodeJS.ProcessEnv {
  const preload = new URL('./fixtures/local-service.mjs', import.meta.url).href;
  return {
    NODE_OPTIONS: `${process.env.NODE_OPTIONS ?? ''} --import=${preload}`.trim(),
    AIHUB_TEST_ORIGIN: base,
  };
}
