# Second-batch candidate workflows

This catalog is a development candidate. It contains the 919 first-batch operations
plus 110 selected additions: 47 Bilibili synchronous queries (45 Huahuo and two Web),
57 other synchronous queries, five LinkedIn asynchronous operations and one YouTube
proxy download operation. Catalog presence does not prove that the live service has
enabled an operation. Use it only with the matching accepted service release or an
explicit controlled test target.

The complete fixed operation list, cohort and snapshot list prices are in
[catalog-cohorts.json](catalog-cohorts.json). `tikin-find-endpoint --describe <path>
--method GET|POST` returns the unmodified public contract, reachable schemas, price,
cohort and candidate identity. Read both the schema and the operation description:
cross-field restrictions and specific rate limits can be stricter than the generic
metadata. Current billing and legitimate input access still need verification.

Use the existing `tikin-config request` for all data API calls, preserve the same
`--record`, and apply the shared request/retry/budget rules. Do not add a retry loop
around it. HTTP 400/422 are not automatically retried, including LinkedIn comments
whose upstream prose recommends three retries; investigate the actual failure and
remaining allowance before any explicit follow-up. Unknown GET operations are
conservatively treated as having side effects.

## Synchronous platform guidance

| Platform | Request construction and limits | Result verification |
| --- | --- | --- |
| Bilibili Huahuo | Use `upper_mid` versus `mid` exactly as described. Search uses POST JSON; ordinary dropdown/detail queries use GET. Obtain dynamic categories, labels and cooperation fields from the documented dropdown/static operations, which are separate priced queries. | Account/session and upstream access can affect results; no valid production session is implied by a catalog or controlled test. Retain returned creator IDs and compare the actual result shape. |
| Bilibili Web | `fetch_dynamic_comments`: supply exactly one of `dynamic_id` and `oid`; `comment_type` belongs only to `oid`, and `pagination_str` remains a JSON string. `fetch_user_post_videos_v2`: `pn >= 1`, `1 <= ps <= 100`, fixed newest-first order; there is no `order` field. | The V2 video list omits some V1 statistics; do not invent missing comments/category data. The provider's unlimited page depth does not remove the user's/page budget. |
| Douyin search | General V3 and video V5 start with `offset:0`, `page:1`, empty `search_id`/`backtrace`; carry all three pagination values from the prior result, increment page, maximum 200. Video V3 has no paging; V4 and live V2 use their own schemas and fixed page sizes. | Stop on `has_more:0`; do not synthesize cursor values, sorting or unsupported filters. |
| Xingtu | Preserve the operation's exact author/item identifier spelling, date strings, enum values and JSON array types. Read the reachable schemas before constructing bulk item requests. | Invalid/deleted IDs can be omitted from results; report unmatched inputs rather than treating the returned subset as complete. |
| Twitter/X | Live status requires numeric `rest_id`; usernames produce placeholder values. Community members has a legacy `cursor` field that is ineffective. Other list/community operations use their documented cursor. | Placeholder `"s"` fields are not verified profile/live data; community members is one page. |
| WeChat MP | H5 endpoints accept POST JSON with an allowed `mp.weixin.qq.com/s...` URL and optional `raw`; stats can reuse a legitimate prior `comment_id`. | H5 stats lacks some metrics exposed by the other stats endpoint; distinguish unavailable metrics from zero. Preserve article/image/page variants. |
| Weibo | Followers use `page` and `data.list.next_page`; following uses returned `since_id` (`timestamp|offset`), not page numbers. Both depend on the server's logged-in Cookie. | Stop followers at zero/missing next page, following at absent `since_id`; retain the final partial page. The hot-search brief has no paging; a nonzero `chat_status_stage` with generation text is not a completed brief. |
| Xiaohongshu PGY | Strict bodies reject unknown fields. Content-square filters/sorts depend on `biz_type`; change only `page_num` when paging. Live-blogger lists carry the prior `seed` and preserve all other filters. | Respect endpoint caps: notes 8/page, similar 4/page, content square 34/page and only 100 total, live bloggers 20/page and at most 250 pages. Featured note comments returns five with no paging. `get_note_components` is explicitly zero-priced in the snapshot; confirm actual zero billing separately. |
| TikTok Ads | `get_top_ads_filters` accepts an optional raw JSON Cookie string, not an object wrapper. Other new Ads bodies have optional `cookie`. Supply only an authorized Cookie; omit it when unavailable. | Top-content requests require a 10-digit Unix seconds timestamp paired with the period: 1=weekly (UTC Sunday), 3=daily, 5=long period. These are not day counts. A syntactically valid/recent date can have no results; do not assume a sample date remains available. |
| TikTok Web | `fetch_post_ai_article` requires `itemId` with this capitalization. | A response can legitimately contain title/description/keywords with an empty article; report which fields are actually present. |
| Threads | Profile search V2 has no paging and returns roughly eight entries; detail V3 takes the full `url`. | Do not invent pagination or infer complete profile coverage. |
| Instagram | Hashtag V3 uses `tag` and the returned `max_id`. | Verify the item list and stop when the cursor is absent; an empty result can still be charged. |
| LinkedIn comments | Supply the numeric activity `urn`, optional `sort_by`, `page`, returned `pagination_token`, and `share_urn` when relevant. Snapshot price is USD 0.05/request. | A constrained resource pool can fail; preserve the error and original allowance. Avoid assuming the cheaper async creation price applies to comments. |

## Representative requests

Replace synthetic identifiers with authorized inputs. Every request file also
requires `original_request` containing the user's actual request. The following
are construction examples, not permission to perform real samples.

```json
{"method":"POST","path":"/api/v1/bilibili/huahuo/search_upper","body":{"main_search":"智能手机","page":1,"region_id":[4,5],"price_info":[{"cooperation_type":1,"creative_skill":[],"include_content":[],"price_min":100000,"price_max":"","price_right":[]}]}}
```

Huahuo `price_info` uses the six documented fields; non-applicable choices remain
empty arrays. Read `square_static_info.price_info_options` before selecting them.
`nickname_or_mids` and `main_search` represent creator search and content search;
usually choose one. `upper_label_tree` value IDs belong only to their documented
filter dimensions, not one catch-all label list.

```json
{"method":"GET","path":"/api/v1/bilibili/web/fetch_dynamic_comments","query":{"oid":"12345","pagination_str":"{\"offset\":\"next\"}"}}
{"method":"POST","path":"/api/v1/douyin/search/fetch_video_search_v5","body":{"keyword":"猫咪","offset":0,"page":1,"search_id":"","backtrace":""}}
{"method":"GET","path":"/api/v1/twitter/web/fetch_user_live_status","query":{"rest_id":"12345"}}
{"method":"POST","path":"/api/v1/wechat_mp/v2/fetch_article_stats_h5","body":{"url":"https://mp.weixin.qq.com/s/example","raw":false,"comment_id":"1234"}}
{"method":"GET","path":"/api/v1/weibo/app/fetch_user_following","query":{"uid":"12345","since_id":"1787913903|40"}}
{"method":"POST","path":"/api/v1/xiaohongshu/pgy/get_content_square","body":{"biz_type":1,"category":"内容类目#美妆","date_range":7,"page_num":1}}
{"method":"POST","path":"/api/v1/xiaohongshu/pgy/get_live_blogger_list","body":{"page_num":2,"seed":7654321}}
{"method":"GET","path":"/api/v1/threads/web/search_profiles_v2","query":{"query":"example"}}
{"method":"GET","path":"/api/v1/instagram/v3/get_hashtag_posts","query":{"tag":"example","max_id":"returned-cursor"}}
{"method":"GET","path":"/api/v1/linkedin/web_v2/get_post_comments","query":{"urn":"12345","pagination_token":"returned-token"}}
```

Use one object per request file. For Ads, choose the target ranking date first and
convert that date to Unix seconds; do not reuse a hardcoded historical timestamp
as a real regression target. An optional Cookie requires its own current source
and authorization; an example never supplies account access.

## LinkedIn asynchronous tasks

All three `GET /api/v1/linkedin/web_v2/async/create_*_task` operations have side
effects and snapshot list price USD 0.008 each. Creation returns `task_id`; it is
not a completed scrape. The shared executor enforces side effects even if a
request file says `side_effects:false`. A known successful creation is retained;
repeating it in the same record returns `task_exists`. A timeout, interrupted
submission or uncertain 429/5xx is `submission_unknown`: reconcile the original
task, and never create a new record to bypass this state.

```json
{"original_request":"<用户原始需求>","method":"GET","path":"/api/v1/linkedin/web_v2/async/create_user_profile_task","query":{"url":"https://www.linkedin.com/in/example/"}}
{"original_request":"<用户原始需求>","method":"GET","path":"/api/v1/linkedin/web_v2/async/get_task_status","query":{"task_id":"<returned task_id>"}}
{"original_request":"<用户原始需求>","method":"GET","path":"/api/v1/linkedin/web_v2/async/get_task_result","query":{"task_id":"<returned task_id>"}}
```

Status and result queries have zero snapshot price and a specific limit of one
request/second/user/route. The executor conservatively spaces queries at least
one second apart in the same record, including retries. It honors a longer valid
`Retry-After`. Generic `10/second` metadata does not override this restriction.
Preserve the same record across commands and processes, using the original caller
Skill. The durable per-task polling allowance is ten query attempts
across both routes and at most 60 seconds. At the limit, report waiting with the
task ID; do not restart the job or reset the ledger to extend the allowance.

Starting/running/not-ready/processing and `ready:false` are intermediate states.
Even a ready status response still requires the result query. Only `ready:true`
with a `records` array from the result route is final; `ready:false, records:[]`
is not final absence. A genuinely ready empty array can be a final empty result.
Failed status or per-record `error`/`error_code` is a remote failure and keeps the
task ID and local report. Invalid, missing or expired task IDs return 400; the
provider retains results for 30 days, not forever. All real task and zero-billing
claims remain unverified until checked against an authorized service and usage.

## YouTube proxy prerequisites

The second-batch `POST /api/v1/youtube/web_v2/get_video_streams_v3` accepts an
11-character `video_id`, required `proxy_url`, one to four unique numeric-string
`itags` (default `137`, `140`), and optional `verify_download` (default false).
Only an HTTP proxy with a fixed public exit or a sticky session is supported;
URL-encode reserved characters in proxy credentials. Metadata API traffic itself
does not need that proxy, but actual media downloads do. Proxy credentials never
belong in a query string, a pasted command argument, or an error report.

Retain every stream's exact signed URL, `download_headers`, `expires_at`, verification
fields, and the metadata's `proxy_exit_ip`. Use the same proxy session and actual
exit; a matching country or session label is insufficient. False verification,
changed exit, expired links and metadata-only success are not completed downloads.
HTTP 200 metadata is charged even when optional sample verification is false.
Sampled-range verification is not full-file verification. Separate audio/video
streams require downloading both and an explicit merge step if a combined file
is requested. Use the [shared download entry](../../tikin-setup/references/downloads.md)
with the original request and full successful response; its same-proxy exit checks,
complete byte/container checks and durable partial state enforce those conditions.
No approved real proxy or sample is provided by this candidate.
