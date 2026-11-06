# Install, update and migrate one complete suite

Read this when installing, updating, repairing or migrating tikin-social. The only
maintained source is `cookaihq/aihub-marketplace`, directory `tikin-social/`.
GitHub and the CNB mirror contain the same release. Native Plugin and Skills-only
are two distributions of that complete directory, not separate product versions.
Never develop in an installation cache or update a single bundled Skill separately.

## Inspect before changing an installation

Use the active host's own installed-package inventory. Record the host, scope,
enabled state, package version, source repository/ref and actual loaded Skill paths.
Check both native Plugins (including the old `tikin-plugin` identities) and standalone
`tikin-*` Skills. Resolve links and record which other hosts use the same real directories.
Do not infer the active source from a directory's existence or from the list of available packages.

Run the actual installed helper with the caller's working directory and Skill name:

```text
uv run --frozen --project "<installed tikin-setup>" python "<installed tikin-setup>/scripts/tikin-config" --skill tikin-douyin status
```

Keep its configuration sources and routing result, without copying secret values.
The new `installation` result gives resolved paths, Plugin/Skill versions, the suite
and endpoint-index SHA-256, and changed/missing/additional files. `verified` means
local content matches the bundled identity, not that a host has loaded it or that
the remote service supports it. Missing metadata in an older package is `unverified`;
preserve that package and compare against its recorded source before replacing it.
Do not generate metadata over a user's modified installation to make it appear clean.

Configuration remains outside the package. Existing project files and ordinary Skill
fallbacks retain their priority. Do not migrate `~/.config/tikin/`, combine accounts,
write keys, or initialize routing as a side effect of installation. If an installation
contains local configuration, preserve it privately and resolve its intended source
with the user; copying it into a new package is not an account-selection policy.

## Choose and stage a fixed version

Before applying an update, show the current and proposed complete Plugin versions,
repository, exact tag (`tikin-social/v<version>`), resolved commit, target paths and
scope. Reuse an explicit installation/update request; a background update check alone
does not authorize replacement. Resolve the tag once and use that commit throughout.
If a native host cannot pin a ref, report that limitation and verify the exact result
it installed; do not claim that a floating marketplace operation used a requested SHA.

Use the native Plugin manager on Codex, Claude Code and WorkBuddy. Keep the scope of
the existing installation and change only tikin-social. WorkBuddy's native UI is the
supported entry, not its embedded CLI. Use the commands/UI described in the parent
Skill; inspect current help where syntax differs.

Hermes uses the native complete Plugin, not the Skills-only installer below. Check
the current `hermes plugins install --help`, then install
`https://github.com/cookaihq/aihub-marketplace.git#tikin-social` with `--ref <exact commit> --enable`.
Use the same `#tikin-social` fragment on the CNB mirror for network fallback.
Record the active Profile/HERMES_HOME. Verify `plugins list`, then `skills_list` and
`skill_view("tikin-social:tikin-endpoint-discovery")` in a fresh session. Keep all
17 Skills and shared resources together. Check updates with `plugins check-updates`;
apply an authorized update through `plugins update tikin-social`, then verify the
actual version, content identity and newly loaded source.

For another Agent Skills client, take **all 17 Skill directories together** from the
same fixed `tikin-social/skills/` tree, including setup and discovery. Stage an exact
commit archive/check-out in the task's temporary directory, record its provenance,
and invoke the existing installer on that local Plugin directory:

```text
npx --yes skills@1.7.6 add "<fixed source>/tikin-social" --skill '*' --agent <active-agent> --copy
```

Select the previously chosen project/user scope (`--global` only for user scope).
Do not use `--all`, which targets every agent, or a repository-wide install that also
installs aihub-studio/setup-aihub. A direct complete-directory copy is also valid when
the client's documented installation entry supports it; preserve sibling paths.
The installer is transport, not an independent release channel. Do not run per-Skill
`skills update` on this suite: stage and reinstall the next fixed complete suite instead.

Before replacement, retain the old package, install records, links and local changes
outside all active Skill search paths. Protect any private files in that backup.
If local edits conflict with the new version, show the conflicting paths and preserve
both versions until the user chooses; never use overwrite/reset to make the audit pass.
Do not overwrite a directory shared with another host. Install into the selected host's
independent scope first, or wait for an explicit migration decision for every consumer.

## Verify the replacement, then retire duplicates

1. Inspect the new package with `status`. Require a complete matching suite and the
   expected Plugin version and index hash. Compare configuration sources/account
   selection and routing with the pre-migration result, without sending a business call.
2. Temporarily disable the old source in **this host only**, preserving its original
   scope and settings. If standalone Skills have no disable switch, quarantine only
   this host's links/copies after checking all reverse references; never move or delete
   their shared target while another host still uses it. If isolation cannot be shown,
   stop the affected migration and leave its shared files intact.
3. Open a fresh session. Record the exact `SKILL.md` actually loaded, run the bundled
   endpoint search for `fetch_one_video`, and run the installed configuration `status`
   with that session's working directory. Require exactly the intended source and
   matching content identity. A CLI inventory or metadata check alone is insufficient.
4. On failure, restore this host's previous enablement/links and scope; retain evidence
   and the staged replacement for diagnosis. Do not switch accounts or repeat an API
   request to repair an installation failure.
5. After that fresh-session verification succeeds, uninstall only the obsolete native
   instance or retire only this host's duplicate entry. Keep shared targets still used
   elsewhere, user configuration and local-edit backups. Recheck other hosts' links.

Report native Plugin vs Skills-only separately: generated suite identity, source commit,
market tag/version, actual installed version/path, new-session loaded source, offline
discovery/configuration results and any unverified host or operating system. Real API
acceptance is separate. A future batch's generated index is a candidate until Tikin
confirms service readiness; installation work must not publish that contract early.
