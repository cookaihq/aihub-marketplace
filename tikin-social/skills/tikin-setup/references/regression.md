# Bounded regression through the shared request command

This is an opt-in test contract. Ordinary requests do not use this campaign's
budget. No live test is authorized by the presence of these files or examples.
The coordinating operator must first verify the test identity, service binding,
current prices, conversion, maximum billing units and upstream attempt bound.
Unknown inputs stop the affected test.

Use the existing `tikin-config request` entry. `--dry-run` describes the exact
`request_sha256` and selected identity without transmitting. It does not create
an approval, ledger or route proof. The fingerprint is SHA-256 of UTF-8 Python
`json.dumps([METHOD, full_url, body], sort_keys=True, ensure_ascii=False)`;
omitted body is `null`. Prefer the dry-run output over reconstructing it.

```text
uv run --frozen --project "<setup>" python "<setup>/scripts/tikin-config" --skill tikin-rest-api request --request-file "<request.json>" --dry-run
uv run --frozen --project "<setup>" python "<setup>/scripts/tikin-config" --skill tikin-rest-api request --request-file "<request.json>" --regression-approval "<shared approval.json>"
```

Keep the returned `--record` on continuation, along with the approval reference.
The record cannot drop or change its regression binding. All records, processes,
Skills and batches use the **same existing ledger**. The request command refuses
a missing ledger; it never initializes, renews, refunds or resets an allowance.

## Files supplied by the coordinator

All references are absolute resolved paths outside the Plugin installation.
Keep these files private. None contains a credential value; token fingerprints
are SHA-256 of the actual token without the `Bearer ` prefix. A local content
hash pins reviewed evidence; it is not independent proof that the evidence is true.

The service's `binding.json` uses `schema: tikin.regression-binding.v1` with
`environment: test`, `client_base_url`, `new_api_base`, `return_route`,
`upstream_base`, `test_token_sha256`, `upstream_token_sha256`, `catalog_sha256`
and timezone-aware ISO 8601 `expires_at`. Its identity is SHA-256 of the exact
file bytes. The first three URLs are the approved test entries, with no path,
query, credentials or trailing slash. The upstream address is the reviewed
provider target and is not a substitute for the test client entry.

Before each business attempt the executor calls the non-billing
`GET <client_base_url>/_tikin/regression-binding`, with the selected Authorization
and `X-Tikin-Regression-Binding: <binding file SHA-256>`. It requires HTTP 200
and the exact declaration plus `binding_sha256`. There is no automatic proof
retry or production fallback. Every business request carries the same header.
The service must check it before upstream IO and enforce its north/south return
association. A healthy process or a billing administration homepage is insufficient.

The operator separately verifies actual channel return routing, token ownership,
prices, conversion and the maximum number of upstream attempts. The service proof
does not establish those maintenance facts. The reviewed route proof is:

```json
{
  "schema": "tikin.regression-route-proof.v1",
  "environment": "test",
  "binding_sha256": "<64 hexadecimal characters>",
  "expires_at": "<timezone-aware ISO 8601 timestamp>",
  "route_verified": true,
  "price_evidence_sha256": "<hash of current verified pricing and billing evidence>"
}
```

`approval.json` binds the one campaign and exact approved requests. Example shape
(placeholders are deliberately invalid):

```json
{
  "schema_version": 1,
  "campaign_id": "<existing campaign>",
  "ledger_path": "<absolute shared ledger.json>",
  "binding_path": "<absolute binding.json>",
  "binding_sha256": "<binding file SHA-256>",
  "proof_path": "<absolute route-proof.json>",
  "proof_sha256": "<route proof file SHA-256>",
  "expires_at": "<timezone-aware ISO 8601 timestamp>",
  "limits": {"paid_attempts": 40, "paid_usd": "0.50", "zero_attempts": 40, "local_attempts": 8},
  "requests": {
    "<request_sha256 from dry-run>": {
      "category": "paid",
      "price_usd": "0.001",
      "max_units": 1,
      "upstream_attempts": 1,
      "side_effects": false,
      "price_evidence_sha256": "<same verified pricing evidence hash>"
    }
  }
}
```

Prices are exact decimal strings in USD. A reservation is price × maximum units
× maximum upstream attempts, and the attempt counter reserves that upstream bound.
`zero` requires verified numeric zero; missing price is never free. `local`
requires zero, one attempt and `upstream_forbidden: true`, justified by the service's
rejection/authentication boundary. Unknown-price requests and unknown multiplicity
are refused. No per-interface rate of 10 RPS is assumed.

The coordinator creates the ledger **once**, after approval. Its initial fields are
`schema_version: 1`, `campaign_id`, `ledger_path`, `binding_sha256`, the same `limits`,
`approval_sha256s: [<raw approval file hash>]`, `reservations: []`, `not_before: 0`.
Never reuse this empty initial form over existing state. A newly approved concrete
sample or renewed price evidence may add an approval hash to that same ledger;
existing reservations and limits remain. The deployment probe allowance belongs
to its separate deployment workflow, not this regression ledger.

If a later approved batch changes the catalog or renews the service declaration,
the operator may replace the ledger's active `binding_sha256` and register the
new approval hash **while preserving all reservations and limits**. Old run
records remain tied to their original binding and cannot be replayed under the
new target. This is an explicit evidence renewal, never a fresh campaign budget.

## Reservation, interruption and continuation

The executor locks the ledger and atomically saves a private reservation before
each actual business send. It does not refund failures, rejected calls or timeouts.
It persists the execution result before marking the reservation received. A crash
leaves a `reserved` entry; an ambiguous outcome is `unknown`. Both block an identical
request even from another process or a newly created run record. Do not clear these
entries to retry: investigate the original operation and obtain explicit follow-up
authorization. The original reserved amount remains counted.

Concurrent processes serialize reservations. Lock contention, malformed files,
expired/changed proof, target mismatch, unapproved request, exhausted budget or
unfinished identical attempt stops transmission. `regression_blocked.reason`
reports a stable local reason without credential or supplier diagnostics.
Valid `Retry-After` is stored in both the run and shared ledger without truncation.
The executor returns a resumable cooldown when the wait exceeds the per-invocation
time budget. Proof, binding and approval expire within at most 24 hours; the operator
renews verified evidence without renewing the campaign allowance.
