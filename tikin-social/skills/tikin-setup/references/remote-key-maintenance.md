# Remote key maintenance

Read this only when the user explicitly requests remote key creation or online validation. It is outside ordinary existing-key configuration and outside Setup AIHub's scope. `<tikin-setup-dir>` is the installed directory containing the parent SKILL.md.

## Explicit remote key creation or online validation

Only for a user-requested online check, after verifying the endpoint is non-billing, run the helper. Credential-only setup ends with local config-check; a nonempty value does not prove authentication:

```bash
uv run --project "<tikin-setup-dir>" python "<tikin-setup-dir>/scripts/tikin-config" validate
```

`validate` classifies its own failures the way `tikin-rest-api` describes under **Reliability**:
401/403 fails immediately as authentication/permission rejection; check the selected key and
service URL before attributing it to a bad key, while a transient failure (429, 5xx, timeout,
connection error) is retried up to 3 attempts total with a 1s then 2s backoff — honouring
`Retry-After` on a 429 — and logs each retry to stderr without the key. Each attempt uses a 30s
timeout, matching the `--max-time 30` that **Reliability** mandates for JSON calls against
`$BASE`; override it with `--timeout <seconds>` only when you have a reason to. Treat its exit
status as final; do not wrap it in a retry loop of your own.

If validation succeeds, continue. If configuration is missing or there is evidence of an invalid
key, return to [the credential flow](credential-setup.md). The browser-assisted
branch below is only for an explicit request to create a remote key:

1. Look for a browser-control MCP, an in-app browser, Chrome control, or a browser-opening CLI.
2. Open `https://console.tikin.net` directly when one is available. Otherwise give the URL and
   wait while the user opens it.
3. Let the user complete sign-in, passwords, CAPTCHA, passkeys, and 2FA. Never enter, request, or
   inspect those credentials.
4. After the user is signed in, navigate through the visible UI to the API Keys page. Do not guess
   an undocumented URL path.
5. Explain that a new credential will be created and get confirmation once. Create the key with a
   descriptive label that the user approves.
6. Prefer the page's Copy action. Do not take a screenshot, DOM snapshot, or tool response that
   reveals the secret. Use automatic transfer only when the browser/CLI can copy the value without
   returning it to the model.
7. For an explicitly approved first shared-file save that also authorizes routing initialization, pipe the clipboard into the helper without command-line interpolation, for example on macOS:

   ```bash
   pbpaste | uv run --project "<tikin-setup-dir>" python "<tikin-setup-dir>/scripts/tikin-config" set-key
   ```

   Existing-file repair follows [the credential flow](credential-setup.md); `set-key` is not a general repair command. Use the equivalent clipboard reader on other operating systems. If no secret-safe transfer is
   available, ask the user to copy the key and provide it to `set-key` through a local hidden or
   non-echoing stdin prompt. Do not ask the user to paste it into chat.
8. Finish with local `config-check`. Run `validate` only if the user separately requested online authentication and the endpoint has been verified non-billing. Report the two results independently.

If an invalid key comes from the process environment or a project file, use `status` to identify
that source; do not silently write a home key that the higher-priority value will override.
