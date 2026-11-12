/**
 * live id（GET /v1/models 的账号模型 id）与 catalog model id（spec 派生）的归一化。
 *
 * 两侧命名规则不同，必须归一化后才能对齐：
 * - live 侧可能带 provider 前缀与方括号变体：`google/veo-3.1[fast|audio]`、`fabric-1.0[480p]`
 * - catalog 侧是文档命名：`veo-3.1`、`fabric-1.0`
 *
 * 注意方向性：catalog 的裸 family 名（`veo-3.1`）**不一定可直接提交**，
 * 归一化只用于「给 live id 找参数说明」，不能据此推断可提交的 id。
 * 已核实的请求映射另在 models.ts 中显式处理，例如 Fabric 的型号与分辨率。
 */
/**
 * 只剥**第一段** provider 前缀，这是刻意的而非疏漏。
 *
 * 源仓记录的 provider 前缀示例是 `google/veo-3.1*`、`openai/sora-2*`，均为单段前缀。
 * 若改用 lastIndexOf 去贪婪剥离，遇到 `some-model/edit` 这种「斜杠不是 provider 前缀」
 * 的 id 会算出 base=`edit`，可能误匹配到毫不相干的 catalog 条目。
 * 归一化只用于「给 live id 找参数说明」，宁可漏匹配（退化成无参数说明）也不能误匹配
 * （给出错误的参数说明）。
 */
export function normalizeModelId(id) {
    const noPrefix = id.includes("/") ? id.slice(id.indexOf("/") + 1) : id;
    const m = /^([^[]+)(?:\[([^\]]*)\])?$/.exec(noPrefix);
    const base = (m?.[1] ?? noPrefix).trim();
    const variants = (m?.[2] ?? "")
        .split("|")
        .map((v) => v.trim())
        .filter(Boolean);
    return { base, variants };
}
