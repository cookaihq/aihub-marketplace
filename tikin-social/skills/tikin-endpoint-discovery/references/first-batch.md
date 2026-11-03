# First-batch contract and migration guide

This candidate contains 919 operations from one frozen index and public OpenAPI.
Its identity is in `catalog-identity.json`; `status: candidate` does not establish
that the configured service has deployed it. Confirm the matching service release
before a live call. This batch repairs existing capabilities and includes the
reviewed Threads search candidate; second-batch capabilities are excluded.

Use `tikin-find-endpoint --describe <exact path> --method <method>` before constructing
a changed request. It returns the complete operation, all referenced components,
catalog identity, snapshot price/rate and reviewed side-effect classification.
OpenAPI 3.1 siblings such as `default` beside `$ref` remain effective. A null
`side_effects` means unclassified: verify semantics or keep conservative protection.
Snapshot prices are not proof of current billing and never approve a regression call.

## Thirteen method migrations

These operations now use **POST** with a JSON body. Do not resend an old GET or
automatically translate its query into a new body. The old GET is absent from
discovery; the service owns enforcement of old-method and retired-route rejection.
The examples below describe construction only, not valid live objects. Obtain an
authorized sample and verify current pricing before calling.

All TikTok paths below have prefix `/api/v1/tiktok/ads/`.

| Action | Body required | Required body fields | Minimal construction example |
| --- | --- | --- | --- |
| `get_ad_interactive_analysis` | yes | `material_id` | `{"material_id":"<authorized material ID>"}` |
| `get_ad_keyframe_analysis` | yes | `material_id` | `{"material_id":"<authorized material ID>"}` |
| `get_ad_percentile` | yes | `material_id` | `{"material_id":"<authorized material ID>"}` |
| `get_ads_detail` | yes | `ads_id` | `{"ads_id":"<authorized ad ID>"}` |
| `get_configure_safety` | no | none; JSON **string** | omit body, or `"<authorized Cookie>"` |
| `get_location_list` | no | none; JSON **string** | omit body, or `"<authorized Cookie>"` |
| `get_query_suggestions` | no | none; JSON object | `{"query":"coffee"}` |
| `get_recommended_ads` | yes | `material_id` | `{"material_id":"<authorized material ID>"}` |
| `get_top_ads_spotlight` | no | none; JSON object | `{}` |
| `get_trends_hashtag_detail` | yes | `hashtag_id` | `{"hashtag_id":"<authorized hashtag ID>"}` |
| `get_trends_hashtag_list` | no | none; JSON object | `{}` |
| `search_ads` | no | none; JSON object | `{"keyword":"coffee"}` |

`POST /api/v1/douyin/web/fetch_user_collects_videos` requires the object
`{"collects_id":"<authorized collection ID>","cookie":"<owning account Cookie>"}`.
The Cookie must belong to the authorized account; a public collection ID alone is
insufficient. Optional `counts` and `max_cursor` follow the frozen schema. Treat
Cookie as sensitive business input: protect the request file and do not echo it.
The executor preserves the transmitted string/object and masks known Cookie values
in ordinary evidence and any echoed response. Installation/configuration does not
authorize saving a Cookie or acquiring another account's credentials.

To use a row, put its exact body under `body` in the shared request JSON with
`method: POST`, its full `path`, and the user's `original_request`. Do not wrap
the two string bodies as `{"cookie": ...}`. An omitted body remains empty;
objects, arrays and strings are sent as the supplied JSON value. POST retains
write protection, even for an apparently read-oriented action.

## Seventy-six request-definition changes

`request-changes.json` records every one of the 76 same-method/path changes
separately from the 13 method migrations. Each row has changed field paths,
compatible/breaking/behavior classification, source and public request hashes,
and its offline coverage. These classifications describe request contracts,
not live success or response equivalence. No parameters are silently renamed.

- Instagram's affected `v3/get_user_*` operations require `username` and remove
  `user_id`; inspect the exact operation rather than sending both.
- LinkedIn company posts remove date filters, add `sort_by` and use only the
  documented effective `start` pagination. User posts expose `start` and
  `pagination_token` in the schema but document them as ineffective: do not
  promise further pages. Job-search filters changed; inspect current names
  instead of forwarding old `keyword`, `company`, `country` or singular filters.
- WeChat `fetch_account_profile` and `fetch_account_services` expand the accepted
  username format: all previous `gh_` values of up to 64 characters remain valid,
  and the new schema permits additional formats up to 80 characters. These two
  changes are compatible extensions, not required client migrations.
  Pugongying objects reject unknown fields where `additionalProperties: false`;
  an old permissive payload must not be treated as valid.
- Reddit adds identifier patterns, lengths, enums and bounded arrays. Repeated
  query values stay repeated; do not join them into an invented comma format.
- Douyin ranking bodies now describe nested objects. Xingtu retains defaults
  beside schema references, including `seach_type: 2` and `time_range_days: 180`;
  preserve the published `seach_type` spelling. Defaults are applied by the
  service, not silently injected by the request helper.

Two audited source defaults receive the coordinator's permitted public conversion:
Kuaishou's integer `boardId` default is integer `1`, and the translation request's
supplier-branded example default is omitted while `src_content` remains. The
remaining 74 normalized request contracts match the audit input. Legal business
fields and request constraints are retained.

## Retirement and candidate replacements

The `retired` array in `request-changes.json` covers all 110 operations selected
for retirement, including method migrations and paths observed only in channels.
Each has a reason and explicit replacement status. An absent verified replacement
is a capability gap, not an invitation to guess a similar path.

- Threads `search_top` / `search_recent` are retired. `search_posts` is the
  first-batch candidate; its request/response/billing semantics and a real sample
  still require acceptance before recommending it as equivalent.
- Shop detail V2 is retired. V3 is already retained in this batch and is not
  counted as another new capability; do not assume response equivalence.
- Searching live streamers by account/nickname is not a verified substitute for
  old content-keyword live search. A new LinkedIn comment API does not replace
  every removed LinkedIn detail endpoint. Unselected second-batch routes stay absent.

Keep historical operation records. A migration or configuration repair does not
automatically replay a possibly charged request. Actual replacement acceptance,
service readiness, current billing and native-host installation are separate gates.
