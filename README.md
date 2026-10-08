# AIhub Marketplace

这个市场提供 AIhub 创作与文档处理、tikin 社交媒体数据与分析的完整 Plugin，并新增统一凭证入口 Setup AIHub。按需要选择安装对象。

本版提供 Setup AIHub 1.0.0、AIhub Studio 1.2.0 和 tikin Social 1.2.0。Setup 已完成 Windows 原生的 Codex 默认沙箱、WorkBuddy 配置闭环及两个服务的 Secret Book 真实表联调；Claude Code 已验证安装、发现和自然触发，配置闭环未实测。具体范围见 [Setup 使用说明](setup-aihub/README.md)。

| Plugin | 能做什么 | 包含的 Skill |
| --- | --- | --- |
| [AIhub Studio](aihub-studio/README.md)（`aihub-studio`） | 图片、视频、音频、音乐、多模态理解、文档处理 | 6 个 `aihub-*` Skill |
| [tikin Social](tikin-social/README.md)（`tikin-social`） | 社交媒体数据查询、素材下载、账号与评论分析、趋势研究 | 17 个 `tikin-*` Skill |
| [Setup AIHub](setup-aihub/README.md)（`setup-aihub`） | 检查、配置、更换和清除上述服务的本机密钥，保留实际来源与恢复进度 | `setup-aihub` |

仓库提供 Claude Code、Codex 和 WorkBuddy 的市场清单。清单登记不代表所有宿主与操作系统的完整调用都已验证；各 Plugin 的运行工具、配置要求与验证范围见其 README。

配置服务时可以说“帮我配置 AIhub 创作服务的密钥”或“换一下刚才的 tikin Key”。已加载 Setup 后，仅说 `setup-aihub` 即可开始中文菜单；Setup 尚未安装时先使用[完整安装提示词](setup-aihub/README.md#让-agent-帮你安装)。业务凭证已可读时无需运行 Setup。

## 让 Agent 帮你安装

### Claude Code / Codex：让 Agent 通过原生 Plugin 入口安装

Claude Code 和 Codex 支持原生 Plugin 管理。将下面这段话复制到当前 Agent 的对话中，把安装对象保留为你需要的 Plugin：

```text
请从 AIhub Marketplace 安装 aihub-studio 和 tikin-social：优先使用 https://cnb.cool/zhidateam/tannt/aihub-marketplace.git，CNB 网络故障时改用 https://github.com/cookaihq/aihub-marketplace.git，保持同一 Plugin 和版本。先阅读仓库 README 和对应 Plugin 的 README，核对当前宿主的支持范围，再使用原生插件管理入口安装受支持的完整 Plugin，保留已有设置。分别报告市场添加、Plugin 安装、Skill 发现与调用的结果。
```

各 Plugin 的完整媒体、文档和数据业务验证范围以对应 README 为准；Setup 的凭证配置验收不代表这些业务全部通过。业务调用还需要对应服务的配置与权限。

### WorkBuddy：手动填写市场源并安装套件

在 WorkBuddy 中，请按下面的步骤操作原生套件管理界面：

1. 打开 **专家·技能·连接器 → 顶部“技能” → “套件”**。如果已有 `aihub-marketplace`，先让 Agent 核对来源并复用；没有时，点击市场名称一行右侧的圆形 **“＋”**。
2. 在弹出的 **“添加市场”** 窗口中，将下面的地址粘贴到 **“市场源”**，再点击 **“提交”**。

   ```text
   https://cnb.cool/zhidateam/tannt/aihub-marketplace.git
   ```

3. 添加成功后选择 `aihub-marketplace`，找到 **aihub-studio** 或 **tikin-social** 套件卡片，点击所需卡片上的 **“＋”** 安装。
4. 安装完成后，在 WorkBuddy 新会话中让 Agent 按对应 Plugin README 完成所需配置，并分别检查 Skill 发现与调用结果。

CNB 网络故障时，可改填 `https://github.com/cookaihq/aihub-marketplace.git`，保持安装对象和版本一致；切换前先检查上次是否已添加成功。若显示“此市场暂无套件”，可让 Agent 检查当前市场来源、加载情况和已有安装记录。

![WorkBuddy 添加市场入口：技能 → 套件 → 市场名称右侧的圆形＋](aihub-studio/references/images/workbuddy-add-marketplace.png)

截图来自 Windows WorkBuddy 5.6.2 的实机，红色 1、2、3 依次标注“技能”“套件”和市场行的圆形“＋”；“添加市场”是点击“＋”后出现的窗口标题。图中的“此市场暂无套件”是截图时的本机状态，截图仅用于定位入口，安装结果需另行检查。需要 Agent 协助时，可让它阅读 [WorkBuddy 安装说明](aihub-studio/references/workbuddy-install.md)。

## 从旧市场迁移

| 旧安装标识 | 新安装标识 | Plugin 全局配置目录 |
| --- | --- | --- |
| `aihub@plugin-marketplace` | `aihub-studio@aihub-marketplace` | `~/.config/aihub-studio/` |
| `tikin-plugin@plugin-marketplace` 或 `tikin-plugin@tikin-plugins` | `tikin-social@aihub-marketplace` | `~/.config/tikin-social/` |

Plugin 安装身份已经改变，现有安装不会自动变成新名称。请先读新 Plugin 的配置迁移说明，安装新版本并准备配置，再通过宿主入口停用旧 Plugin。开启新会话，确认 Plugin 身份和 Skill 来源指向新版本后再验证；验证成功后才卸载旧版。保留旧配置，只有你明确选择时才删除。六个 `aihub-*`、十七个 `tikin-*` Skill 名称及 `AIHUB_*`、`TIKIN_*` 配置字段保持原名。

旧 `~/.config/aihub/` 与 `~/.config/tikin/`（或原 tikin 的 XDG 配置位置）不会自动搬迁或作为旧别名继续读取。需要复用旧配置时，让 Agent 核对源文件、目标文件及已有设置，再按你的明确选择迁移；不要把密钥写进 Plugin 安装目录。项目配置及各 Skill 的普通配置回退规则见对应 README。

旧 `tikin-plugins` 转发市场固定在 `tikin-plugin` 0.3.0；新功能和维护版本在本市场的 `tikin-social` 发布。

## 版本与 Release

版本标签随代码同步到 CNB；下表链接指向 GitHub 上发布的 Release 说明。

<!-- release-table:begin -->
| 目标 | 版本 | Release |
|---|---|---|
| aihub-studio | 1.2.0 | [aihub-studio/v1.2.0](https://github.com/cookaihq/aihub-marketplace/releases/tag/aihub-studio%2Fv1.2.0) |
| setup-aihub | 1.0.0 | [setup-aihub/v1.0.0](https://github.com/cookaihq/aihub-marketplace/releases/tag/setup-aihub%2Fv1.0.0) |
| tikin-social | 1.2.0 | [tikin-social/v1.2.0](https://github.com/cookaihq/aihub-marketplace/releases/tag/tikin-social%2Fv1.2.0) |
<!-- release-table:end -->
