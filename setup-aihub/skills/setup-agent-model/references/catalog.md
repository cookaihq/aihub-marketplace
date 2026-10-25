# 模型目录与公开数据刷新

维护源是 [data/models.json](../data/models.json)，[manifest](../data/models.manifest.json) 由 `catalog-build` 生成。格式版本为 1，目录版本为递增正整数；每次改正文递增 `catalog_version`，再用 `catalog-build --check` 校验。程序版本与目录版本独立。

固定远端为 `https://raw.githubusercontent.com/cookaihq/aihub-marketplace/main/setup-aihub/skills/setup-agent-model/data/` 下同名两个文件。只有公开 JSON 数据可刷新，不接受可执行脚本、地址覆盖、客户端名单或凭证。远端不可达或数据校验失败时，使用有效缓存或包内基线。

每个条目必含 `id/name/description/status/routes`，可选 `key_groups/sources`。route 必含 `protocol/capabilities`，协议枚举 `openai-chat-completions/openai-responses/anthropic-messages/gemini-native`。capabilities 必含 `tool_calling/image_input/reasoning_efforts`，可选正整数 `context_window/max_output_tokens`；任何未核实能力为 `null`。两项布尔能力不得写字符串；reasoning_efforts 若非 null 必须是非空、无重复字符串数组。弃用条目 status 为 deprecated，保留旧配置，不作为新选择。

当前七个精确 ID 与分组来自 [AIhub 公开 pricing](https://api.aihubmax.com/api/pricing)。接口登记不证明每把 Key 的权限或未登记协议；能力没有可核验证据时保持 null。服务业务约束在适配逻辑处理，目录中不添加客户端白名单。

自动刷新先比较索引版本/schema/SHA-256：同版用本地，新版验证正文后更新用户缓存，较旧不降级，同版内容变更视为发布错误。并发发布仅重查一次索引。Windows 缓存在 `%LOCALAPPDATA%/setup-aihub/setup-agent-model/catalog/`，macOS 在 `~/Library/Caches/setup-aihub/setup-agent-model/catalog/`；保留最后一份有效代次。选有效缓存与包内目录中较新者。

网络遵循总预算 10 秒、每次最多 3 秒、整个刷新最多 3 次请求，瞬时错误指数退避并遵守剩余预算内的 Retry-After；确定性 4xx/证书错误立即回退。独立 GET worker 使 DNS/慢速正文也受墙钟预算限制。刷新失败仍可用有效缓存或基线，报告未更新，不能说已是最新。

保存确认固定选中的目录数据；确认后远端变化不自动换模型。程序更新由宿主 Plugin 机制处理，目录自动刷新不更新代码。
