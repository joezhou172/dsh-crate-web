# DSH Crate Development Plan / 开发计划

**Product / 产品：DSH Crate**

[English](#english) · [中文](#中文)

This document describes the public development plan starting from the first Preview release.

本文档描述 DSH Crate 从首个公开 Preview 开始的开发计划。

---

# English

## Product direction

DSH Crate has two connected product directions:

### Share

Make a DSH environment easy to inspect, send, import, and reproduce.

### Freeze

Preserve as much of a working DSH environment as possible so future restoration depends less on original package sources, local state, or manual setup steps.

The project should keep these two directions connected instead of expanding into a general DSH marketplace or control panel.

---

## Current Preview — August 15, 2026

### User-facing scope

The current release supports:

- current Profile inspection
- installed plugin and Bundle inspection
- `.dshcrate` export
- per-plugin embedded/reference-only mode
- required Secret name recording without Secret values
- Inspect / Preflight
- BLOCKER / WARNING / INFO
- environment differences
- Import preview
- Import into a new Profile
- explicit-confirmation overwrite of an existing Profile
- Profile Verify
- full diagnostic view
- copyable diagnostic JSON
- operation history
- Crate download
- deletion of non-running Profiles
- explicit-confirmation Profile switch and restart

### Explicitly not provided yet

- model conversation tests
- Session creation tests
- Core Tool tests
- plugin-specific business Smoke Tests
- automatic DSH runtime installation
- Profile merge
- silent overwrite of the current Profile

### Release acceptance

The public Preview should keep passing these gates:

1. the npm package installs into a clean DSH test Profile;
2. DSH starts with the package installed;
3. Settings → DSH Crate opens;
4. Export produces a downloadable `.dshcrate`;
5. Inspect remains read-only;
6. one valid Crate reaches Import preview;
7. one BLOCKER prevents Import;
8. one WARNING remains visible and is not converted into PASS;
9. new-Profile Import succeeds;
10. existing-Profile overwrite requires explicit confirmation;
11. the current running Profile is not silently overwritten;
12. failed Import does not commit a partially successful target;
13. full diagnostic JSON remains available;
14. deletion is limited to non-running Profiles;
15. switch/restart requires explicit confirmation.

---

## npm and local deployment

The public installation command is:

```powershell
dsh plugin --profile web add dsh-crate-web@0.1.0
```

Local development and offline testing remain supported:

```powershell
# From the repository root
dsh plugin --profile web add .

# From a local .tgz artifact
dsh plugin --profile web add .\dsh-crate-web-0.1.0.tgz
```

The plugin must be installed into the target DSH Profile. Do not use a global `npm install` for plugin deployment.

Publishing is performed by `.github/workflows/publish-dsh-crate-web.yml` with GitHub OIDC and npm provenance. A release tag is pushed with:

```powershell
git tag dsh-crate-web-v0.1.0
git push origin dsh-crate-web-v0.1.0
```

The workflow validates the package before running `npm publish --provenance --access public`.

## August 16, 2026 — Troubleshooting Skill

### Goal

Ship a practical troubleshooting layer immediately after the first public Preview.

The Skill should consume artifacts DSH Crate already produces:

- diagnostic JSON
- Import report
- Verify report
- Crate manifest
- plugin/package identity information
- relevant stdout/stderr

### Flow

```text
Failure
  ↓
Diagnostic JSON
  ↓
Classify failing stage
  ↓
Evidence-backed hypotheses
  ↓
Minimal repair or next check
  ↓
DSH Crate Verify
```

### Rules

- do not hide FAIL by converting it into WARNING
- do not declare repair success without Verify evidence
- prefer minimal, local changes
- preserve full diagnostics
- avoid modifying unrelated Profiles
- do not modify credentials automatically
- do not broadly rewrite the entire DSH_HOME
- stop when evidence is insufficient instead of inventing a repair

### Acceptance

At least these cases should be covered:

1. missing or unresolved plugin source;
2. Bundle/composition failure;
3. Profile preparation or Import failure;
4. runtime start/Verify failure;
5. one intentionally unrepairable case where the Skill stops without destructive changes.

---

## By August 19, 2026 — Expanded environment export

### Goal

Move beyond only Profile/plugin portability and include the environment data users actually care about carrying with them.

### Planned additions

- Conversation export/import
- plugin configuration portability
- plugin-owned workflow portability
- additional plugin-local portable data where ownership can be identified safely
- clearer export inventory
- privacy review before sharing user data

### Data classification

Every exported data class should be explicitly classified as one of:

```text
portable
reference-only
secret-name-only
excluded
unsupported
```

### Privacy boundary

Credential values remain excluded.

Conversation and user-data portability must be explicit and reviewable before sharing.

Do not silently copy the entire DSH_HOME.

### Acceptance

At minimum:

1. selected Conversation data can be exported and imported into an isolated test environment;
2. plugin configuration survives export/import;
3. plugin-owned workflows survive export/import when the plugin exposes a stable and identifiable storage boundary;
4. Secret values remain excluded;
5. unsupported plugin-local data is reported instead of silently ignored;
6. failed import does not corrupt the source Profile;
7. export inventory clearly tells the user what is included and excluded.

---

## By August 23, 2026 — In-Profile management

### Goal

Manage what is inside the current DSH Profile directly, without leaving DSH or rebuilding the environment by hand. This is in-Profile management for the Profile you are already working with, not a second general-purpose Profile manager.

### Phase 1 — plugin management (by August 19)

- List plugins installed in the current Profile: resolved version, Bundle status, runtime source.
- Add, remove, enable, or disable a plugin through an explicit review step that shows the planned change.
- Show version intent clearly: requested specifier, resolved version, runtime version.
- A change succeeds only when the Profile boots, a new Session can be created, and the configured smoke tests pass. Otherwise the status is `FAIL` or `UNTESTED`.
- The original Profile is never overwritten without explicit confirmation; changes are inspectable before they apply.

### Phase 2 — all in-Profile content management (by August 23)

Extend the same review-then-apply pattern to all Profile content:

```text
Profile configuration
+ Bundles
+ plugin configuration
+ plugin-owned workflows
+ selected Conversations / user data
+ required Secret names (values stay local)
+ environment inventory
+ integrity evidence
```

### Main acceptance gate

```text
Current Profile
        ↓
  List / change
        ↓
   Review step
        ↓
      Apply
        ↓
      Verify
        ↓
PASS / FAIL / UNTESTED / DEGRADED
```

No content is reported as managed unless the real Verify step passed.

## By September 15, 2026 — Full Configuration Freeze

### Goal

Make **Freeze** a first-class product workflow.

The user should be able to take a working DSH setup and preserve as much of its reconstructible state as possible in one Crate.

### Freeze target

```text
Profile configuration
+ Bundle order
+ plugin identity
+ embedded plugin artifacts
+ plugin configuration
+ plugin-owned workflows
+ selected Conversations / user data
+ required Secret names
+ environment inventory
+ integrity evidence
```

### Export presets

The target UX should expose:

```text
Share
Freeze
Custom
```

**Share**

Prefer smaller, reference-friendly output.

**Freeze**

Prefer embeddable artifacts and preservation.

**Custom**

Let the user choose per component.

### Freeze completeness report

Before export, show:

```text
Embedded
Reference-only
Secret-name-only
Excluded
Unsupported
Host dependency
Offline-restorable: YES / NO / UNPROVEN
```

Never call a Crate fully frozen merely because some plugins are embedded.

### Main acceptance gate

```text
Working DSH environment
        ↓
      Freeze
        ↓
   .dshcrate
        ↓
Network disabled
        ↓
Fresh DSH_HOME
        ↓
     Restore
        ↓
      Verify
```

A test environment only receives an offline-restorable claim when every required external component has been accounted for and the actual offline restore passes.

---

## By September 30, 2026 - Scheduled snapshots and startup-failure auto recovery

### Goal

Make a working DSH environment recoverable without manual reconstruction.

### Scheduled snapshots

- Capture a lightweight snapshot on a configurable schedule (disabled by default).
- A snapshot describes the Profile and its reconstructible state; it does not copy the entire `DSH_HOME` and contains no Secret values, only required Secret names.
- Snapshots are immutable and read-only: they can be listed, Inspected, and Preflighted, and nothing writes into an existing snapshot.
- Snapshots support retention-based cleanup and can be restored into a fresh Profile without touching the original.

### Startup-failure auto recovery

- When DSH fails to start, offer to restore the most recent snapshot into a new Profile.
- Recovery must not overwrite the original Profile; it creates a recoverable copy and runs Verify before reporting success.
- Success is only reported when DSH actually boots, a new session can be created, and the configured smoke tests pass. Until then the status is `FAIL` or `UNTESTED`, never assumed `PASS`.
- Every automatic action is logged with machine-readable diagnostics (stage, status, evidence) so a recovery can be audited and the diagnostics copied for bug reports.

### Main acceptance gate

```text
Working DSH environment
        ↓
Schedule a snapshot
        ↓
     snapshot
        ↓
DSH fails to start
        ↓
  Auto-recovery
        ↓
      Verify
        ↓
PASS / FAIL / UNTESTED / DEGRADED
```

A recovery is only marked `PASS` when the real boot, new-session, and smoke-test run succeeds in the recovered Profile.

---

## Community Crates

### Goal

Allow useful, tested DSH environments to be shared through Pull Requests without turning DSH Crate into a generic plugin marketplace.

Good submissions include:

- Minimal environments
- Coding environments
- Research / Browser environments
- specialized workflow environments
- proven plugin combinations

### Submission requirements

Every Community Crate should document:

```text
Purpose
Included plugins
Embedded/reference-only status
Required Secret names
Tested DSH version
Tested Node version
Tested OS
Verification scope
Known limitations
Last tested date
```

### Review rule

`Verified` only means:

> the listed checks were actually executed in the listed environment.

It never means universal compatibility.

Untested capabilities must remain explicitly untested.

### Growth purpose

Community Crates should help answer a practical question:

> “What useful DSH environments have people already built and actually tried?”

They are not a replacement for plugin repositories and should not become a general rating system.

---

## After the first month

Priority after the Freeze milestone should be decided from real usage.

Candidate work:

- polished standalone CLI distribution
- better restore/recovery UX
- Crate schema migration between versions
- broader cross-platform testing
- improved diagnostic tooling
- optional signing/integrity infrastructure if sharing demand justifies it
- additional portable data classes

---

## Deferred until demand is proven

Do not prioritize these simply because other DSH projects have them:

- plugin marketplace
- cloud sync
- user accounts
- ratings/reviews
- social Crate platform
- automatic plugin recommendations
- general Profile manager features
- Compatibility Lab
- silent/force overwrite
- bundled DSH runtime

---

## What to measure after Preview

Use real usage to change priorities.

Track:

1. whether users export mainly to share or preserve;
2. how often embedded mode works for real third-party plugins;
3. which plugin sources fail most often;
4. which Import stage fails most often;
5. whether users understand BLOCKER / WARNING / INFO;
6. whether explicit overwrite is actually used;
7. whether Verify gives users enough confidence;
8. whether users submit useful Community Crates;
9. which Community Crate categories attract downloads;
10. which missing data types most often prevent a full migration;
11. whether users value Troubleshooting Skill enough to keep expanding it.

Roadmap items are priorities, not promises that every item must exist forever.

---

## Release principles

For every release:

- preserve Profile safety
- keep diagnostics complete
- distinguish tested from untested
- never broaden compatibility claims beyond evidence
- keep credential values out of ordinary Crates
- prefer one complete end-to-end workflow over several half-built features

---

# 中文

## 产品方向

DSH Crate 目前有两条互相连接的主线。

### Share：分享

让一套 DSH 环境可以被检查、发送、导入和重建。

### Freeze：冻结

尽可能保存一套已经工作的 DSH 环境，让未来恢复时更少依赖原始插件来源、本地状态和人工重新配置。

这两条主线应该继续共用同一个 Crate、Import 和 Verify 体系，而不是把项目扩张成另一个通用插件市场或 DSH 控制面板。

---

## 当前 Preview — 2026 年 8 月 15 日

### 当前用户能力

当前版本支持：

- 查看当前 Profile
- 查看已安装插件和 Bundle
- 导出 `.dshcrate`
- 每个插件选择 embedded/reference-only
- 记录 required Secret 名称但不导出 Secret 值
- Inspect / Preflight
- BLOCKER / WARNING / INFO
- 环境差异
- Import 预览
- 导入为新的 Profile
- 明确确认后覆盖已有 Profile
- Profile Verify
- 查看完整诊断
- 复制完整诊断 JSON
- 操作历史
- 下载 Crate
- 删除当前未运行的 Profile
- 明确确认后切换并重启 Profile

### 当前明确不提供

- 模型对话测试
- Session 创建测试
- Core Tool 测试
- 插件业务 Smoke Test
- 自动安装 DSH runtime
- Profile Merge
- 静默覆盖当前 Profile

### Preview 发布验收

公开版本至少持续满足：

1. npm 包可以安装到干净 DSH 测试 Profile；
2. 安装后 DSH 可以启动；
3. Settings → DSH Crate 可以打开；
4. Export 可以生成并下载 `.dshcrate`；
5. Inspect 保持只读；
6. 正常 Crate 可以进入 Import Preview；
7. BLOCKER 可以真实阻止 Import；
8. WARNING 不会被错误显示成 PASS；
9. 新 Profile Import 成功；
10. 覆盖已有 Profile 必须明确确认；
11. 当前运行 Profile 不会被静默覆盖；
12. Import 失败不会提交半成品目标 Profile；
13. 完整诊断 JSON 始终可以查看；
14. 只能删除当前未运行的 Profile；
15. 切换/重启必须明确确认。

---

## npm 与本地部署

正式安装命令：

```powershell
dsh plugin --profile web add dsh-crate-web@0.1.0
```

本地开发和离线测试仍然支持：

```powershell
# 从仓库根目录执行
dsh plugin --profile web add .

# 安装本地 .tgz 制品
dsh plugin --profile web add .\dsh-crate-web-0.1.0.tgz
```

插件必须安装到目标 DSH Profile。不要使用全局 `npm install` 作为插件部署方式。

发布由 `.github/workflows/publish-dsh-crate-web.yml` 使用 GitHub OIDC 和 npm provenance 完成。发布版本时执行：

```powershell
git tag dsh-crate-web-v0.1.0
git push origin dsh-crate-web-v0.1.0
```

Workflow 会先验证包内容，再执行 `npm publish --provenance --access public`。

## 2026 年 8 月 16 日 — Troubleshooting Skill

### 目标

在首个公开 Preview 后马上补一层实际可用的排障能力。

Skill 直接消费 DSH Crate 已经产生的：

- diagnostic JSON
- Import report
- Verify report
- Crate manifest
- 插件/包身份信息
- 相关 stdout/stderr

### 流程

```text
失败
 ↓
Diagnostic JSON
 ↓
判断失败阶段
 ↓
基于证据提出根因假设
 ↓
给出最小修复或下一步检查
 ↓
DSH Crate Verify
```

### 规则

- 不能把 FAIL 改成 WARNING 来制造“修好了”
- 没有 Verify 证据不能宣布修复成功
- 优先最小、本地修改
- 保留完整诊断
- 默认不修改无关 Profile
- 不自动修改 Credential
- 不大范围改写整个 DSH_HOME
- 证据不足时应停止，而不是猜一个修复方案

### 至少验收

1. 插件来源缺失/无法解析；
2. Bundle / Composition 故障；
3. Profile 准备或 Import 故障；
4. Runtime 启动 / Verify 故障；
5. 一个故意不可修复案例，Skill 能停止且不做破坏性修改。

---

## 2026 年 8 月 19 日前 — 扩大环境导出范围

### 目标

从 Profile / 插件层继续扩展到用户真正想一起带走的数据。

### 计划增加

- Conversation 导出 / 导入
- 插件配置导出 / 导入
- 插件内工作流导出 / 导入
- 能够安全识别归属关系的其他插件本地数据
- 更清楚的导出内容清单
- 分享用户数据前的隐私检查

### 数据分类

所有导出数据都应该明确属于：

```text
portable
reference-only
secret-name-only
excluded
unsupported
```

### 隐私边界

Credential value 继续强制排除。

Conversation 和用户数据必须由用户明确选择，并且分享前可以检查。

不能为了“全量迁移”简单复制整个 DSH_HOME。

### 至少验收

1. 选中的 Conversation 可以在隔离环境完成导出/导入；
2. 插件配置导出后可以恢复；
3. 插件存在稳定且可识别存储边界时，插件内工作流可以恢复；
4. Secret 值不会进入 Crate；
5. 无法支持的插件本地数据必须明确报告，不能静默漏掉；
6. 导入失败不能破坏源 Profile；
7. 导出清单可以明确告诉用户哪些内容被包含、排除或尚不支持。

---

## 2026 年 8 月 23 日前 — Profile 内管理

### 目标

直接管理当前 DSH Profile 里的内容，不用离开 DSH，也不用手动重建环境。这是对正在使用的 Profile 进行管理，不是另一个通用 Profile 管理器。

### 第一阶段 — 插件管理（8 月 19 日前）

- 列出当前 Profile 已安装插件：解析版本、Bundle 状态、runtime 来源。
- 新增 / 移除 / 启用 / 禁用插件时，先经过一个明确展示变更内容的确认步骤。
- 明确展示版本意图：请求的 specifier、解析版本、runtime 版本。
- 只有 Profile 真正启动、能创建新会话、配置的 smoke test 真实通过，才报告成功；否则状态只能是 `FAIL` 或 `UNTESTED`。
- 没有明确确认前不覆盖原 Profile；变更在应用前可检查。

### 第二阶段 — Profile 内全部内容管理（8 月 23 日前）

把同样的“先确认再应用”流程扩展到 Profile 内所有内容：

```text
Profile 配置
+ Bundle
+ 插件配置
+ 插件内工作流
+ 选定的 Conversation / 用户数据
+ required Secret 名称（值保留在本机）
+ 环境清单
+ 完整性证据
```

### 核心 Gate

```text
当前 Profile
        ↓
 列出 / 修改
        ↓
   确认步骤
        ↓
     应用
        ↓
     Verify
        ↓
PASS / FAIL / UNTESTED / DEGRADED
```

除非真实 Verify 通过，否则不声称任何内容已被管理。

## 2026 年 9 月 15 日前 — Full Configuration Freeze

### 目标

把 **Freeze** 做成一等功能。

用户应该能够把已经工作的 DSH 环境尽可能完整地冻结到一个 Crate 中。

### Freeze 目标内容

```text
Profile 配置
+ Bundle 顺序
+ 插件身份
+ embedded 插件制品
+ 插件配置
+ 插件内工作流
+ 选定的 Conversation / 用户数据
+ required Secret 名称
+ 环境清单
+ 完整性证据
```

### 导出模式

目标 UI：

```text
Share
Freeze
Custom
```

**Share**

优先小体积和 reference-friendly。

**Freeze**

优先嵌入和长期保存。

**Custom**

允许用户逐项决定。

### Freeze 完整度报告

导出前明确展示：

```text
Embedded
Reference-only
Secret-name-only
Excluded
Unsupported
Host dependency
Offline-restorable: YES / NO / UNPROVEN
```

不能因为部分插件被 embedded，就把整个 Crate 宣传成“已经完全冻结”。

### 核心 Gate

```text
正在工作的 DSH 环境
        ↓
      Freeze
        ↓
   .dshcrate
        ↓
断开网络
        ↓
Fresh DSH_HOME
        ↓
     Restore
        ↓
      Verify
```

只有所有 required 外部组件都已经处理，而且真实离线恢复通过，才允许给该测试环境标记 offline-restorable。

---

## 2026 年 9 月 30 日前 — 定时快照与启动失败自动恢复

### 目标

让已经调好的 DSH 环境出问题时也能快速恢复，不需要手动重建。

### 定时快照

- 按可配置的间隔自动生成轻量快照（默认关闭）。
- 快照描述 Profile 及其可重建状态，不复制整个 `DSH_HOME`，不含 Secret 值，只记录 required Secret 名称。
- 快照不可变、只读：可以列出、Inspect、Preflight，不会写入已有快照。
- 支持按保留策略清理，也可以恢复到全新 Profile，不影响原 Profile。

### 启动失败自动恢复

- DSH 启动失败时，提供用最近快照恢复到新 Profile 的选项。
- 恢复不覆盖原 Profile；先创建可恢复副本，Verify 通过后才报告成功。
- 只有 DSH 真正启动、能创建新会话、配置的 smoke test 真实通过才算成功；在此之前状态只能是 `FAIL` 或 `UNTESTED`，不能自行判定为 `PASS`。
- 每次自动操作都会记录日志和机器可读诊断（阶段、状态、证据），便于审计和提交 Issue。

### 核心 Gate

```text
正在工作的 DSH 环境
        ↓
  定时生成快照
        ↓
      快照
        ↓
DSH 启动失败
        ↓
    自动恢复
        ↓
      Verify
        ↓
PASS / FAIL / UNTESTED / DEGRADED
```

只有恢复后的 Profile 真实完成启动、创建新会话和 smoke test，才能标记为 `PASS`。

---

## Community Crates

### 目标

允许用户通过 Pull Request 分享**真正好用、已经实际测试过**的 DSH 环境，但不把 DSH Crate 做成普通插件市场。

适合投稿：

- Minimal 环境
- Coding 环境
- Research / Browser 环境
- 专用工作流环境
- 已经长期使用过的插件组合

### 投稿必须说明

```text
用途
包含插件
Embedded/reference-only 状态
Required Secret 名称
测试 DSH 版本
测试 Node 版本
测试操作系统
实际验证范围
已知限制
最后测试日期
```

### Review 规则

`Verified` 只表示：

> 列出的测试确实在列出的环境中运行过。

绝不表示全平台、全版本永久兼容。

没有测试的能力必须继续标记为未测试。

### Community Crates 的作用

它主要回答：

> “别人已经搭过、实际用过哪些有价值的 DSH 环境？”

而不是替代插件仓库或做通用评分系统。

---

## 第一个月之后

完成 Freeze 里程碑后，根据真实使用情况排序：

- 面向普通用户的独立 CLI 分发
- 更好的 Restore / Recovery UX
- 不同 Crate schema 版本迁移
- 更多跨平台测试
- 更好的诊断工具
- 如果真实分享需求足够强，再做签名/完整性基础设施
- 更多可移植数据类型

---

## 在需求明确前暂缓

不要因为别的 DSH 项目有，就立刻做：

- 插件市场
- 云同步
- 用户账号
- 评分/评论
- 社交 Crate 平台
- 自动插件推荐
- 通用 Profile Manager 功能
- Compatibility Lab
- 静默/强制覆盖
- 内置 DSH runtime

---

## Preview 之后重点收集什么

真实用户数据应该决定后续优先级。

重点看：

1. 用户更多是为了分享还是保存；
2. embedded 对真实第三方插件的成功率；
3. 哪种插件来源最容易失败；
4. Import 最常失败在哪一步；
5. 用户是否理解 BLOCKER / WARNING / INFO；
6. 覆盖已有 Profile 是否真的常用；
7. Verify 是否给了用户足够信心；
8. 是否有人愿意提交 Community Crate；
9. 哪类 Community Crate 下载最多；
10. 哪些缺失数据最妨碍完整迁移；
11. Troubleshooting Skill 是否真的值得继续投入。

Roadmap 是当前优先级，不代表每个功能未来都必须存在。

---

## 发布原则

每个版本都要坚持：

- 保护 Profile
- 保留完整诊断
- 明确区分 tested 和 untested
- 不做超出证据范围的兼容性承诺
- Credential value 不进入普通 Crate
- 优先完成一个端到端闭环，而不是同时做很多半成品功能

