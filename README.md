# DSH Crate

> Share and import complete DeepSeek Harness setups as one inspectable Crate.  
> 分享和导入完整的 DeepSeek Harness 环境，一个可检查、可导入的 Crate。

```bash
dsh plugin --profile web add dsh-crate-web
```

[English](#english) · [中文](#中文)

> **Status / 状态：Preview**
>
> DSH Crate only claims what it actually checks. Import or Profile Verify success does not mean that model conversation, Session creation, Core Tool execution, or every third-party plugin business function has been verified.
>
> DSH Crate 只对实际执行过的检查负责。Import 或 Profile Verify 成功，不代表模型对话、Session 创建、Core Tool 或所有第三方插件业务功能都已经验证。

---

# English

## What is DSH Crate?

A useful DeepSeek Harness setup is often more than a list of installed packages. It may also depend on the current Profile, installed plugins, Bundles, plugin sources, Profile configuration, required Secret names, and runtime/environment information.

DSH Crate packages that environment definition into one file:

```text
Configured DSH Profile
        ↓
      Export
        ↓
   setup.dshcrate
        ↓
      Inspect
        ↓
   Import / Share
        ↓
   Target Profile
        ↓
      Verify
```

The main goal is simple:

> **If you already built a useful DSH setup, you should be able to share or move it without rewriting the setup process by hand.**

## Why not just zip `DSH_HOME`?

You can.

If your only goal is a private backup of your own machine, compressing the whole DSH directory may be the simplest option.

DSH Crate is for a different problem:

> **an environment you want to inspect, share, migrate, and reconstruct without copying the entire DSH home.**

A raw directory archive may contain or depend on credentials, private Conversations, caches, logs, temporary state, machine-specific paths, `node_modules`, and local runtime details.

DSH Crate instead tries to separate:

```text
portable environment data
reference-only dependencies
required Secret names
excluded private/runtime data
```

That makes the result more suitable for sharing and controlled Import.

## Install

Install the Web plugin into a DSH Web Profile:

```bash
dsh plugin --profile web add dsh-crate-web
```

Then start or restart DSH Web and open:

```text
Settings → DSH Crate
```

DSH Crate is a DeepSeek Harness extension. It does not install or replace the DSH runtime. The target machine must already have a working DSH installation.

## What works today

The current Preview can:

- inspect the current DSH Profile
- view installed plugins and Bundles
- export a Profile as `.dshcrate`
- choose `embedded` or `reference-only` for plugins
- record required Secret names without exporting Secret values
- Inspect / Preflight a Crate before Import
- show `BLOCKER`, `WARNING`, `INFO`, and environment differences
- preview the target Profile, plugins, and risks before Import
- import a Crate as a new Profile
- overwrite an existing Profile only after explicit confirmation
- Verify an imported or prepared Profile
- view complete failure diagnostics
- copy the complete diagnostic JSON
- review operation history
- download exported Crates
- delete Profiles that are not currently running
- switch Profiles and restart after explicit confirmation

## Quick troubleshooting with DSH Crate

When a DSH environment stops working:

1. Open **Settings → DSH Crate** and **Export** the current Profile as a `.dshcrate`.
2. Run **Inspect / Preflight** on the Crate - it lists `BLOCKER`, `WARNING`, and `INFO` problems and never modifies your environment.
3. **Import** the Crate into a fresh Profile (do not overwrite the original) and run **Verify**.
4. If a step fails, copy the full diagnostic JSON and attach it to an issue or troubleshooting tool.

Inspect and Preflight are read-only; nothing changes until you explicitly confirm an Import.

## Share a working setup

This is the primary use case.

Without a Crate, sharing a DSH setup may look like:

```text
Install plugin A
Install plugin B
Use this version
Enable these Bundles
Change this config
Remember these required Secrets
...
```

With DSH Crate:

```text
Export
  ↓
send setup.dshcrate
  ↓
Inspect
  ↓
Import
```

The recipient can see what is inside before changing their environment.

## Move a setup to another machine

DSH Crate can also be used as a migration layer:

```text
Machine A
   ↓
Export
   ↓
.dshcrate
   ↓
Machine B
   ↓
Preflight
   ↓
Import
   ↓
Verify
```

The goal is not to copy the entire original machine state. The goal is to reconstruct the DSH environment from portable information and explicit package sources.

## Embedded vs Reference-only

### Embedded

The Crate carries an installable plugin artifact when available and appropriate.

Use this when you want the Crate to preserve the actual installation artifact instead of depending only on a future package lookup.

```text
Plugin artifact
+ package identity
+ integrity information
        ↓
     .dshcrate
```

### Reference-only

The Crate stores the plugin source and identity and reacquires it during Import.

Use this when the source is expected to remain available, redistribution is not appropriate, or you want a smaller Crate.

A single Crate can mix embedded and reference-only plugins.

## Inspect before Import

Opening a Crate does not mean blindly installing it.

Preflight reports findings as:

- **BLOCKER** — Import should not continue
- **WARNING** — Import may continue, but there is a known risk or difference
- **INFO** — useful package or environment information

Before Import, DSH Crate shows the target Profile, plugin operations, environment differences, detected risks, and the Import decision.

## Import safety

Import creates a new Profile by default.

Existing Profiles are not silently replaced. If you choose to overwrite an existing Profile, DSH Crate requires explicit confirmation.

Other safety boundaries include:

- no silent overwrite of the current running Profile
- Profile deletion only when the Profile is not currently running
- Profile switch and restart require explicit confirmation
- Inspect and dry-run are read-only
- failed Import should not commit a partially successful target
- complete diagnostics remain available after failure

## Secrets stay out of the Crate

A Crate can record that a Secret is required:

```json
{
  "requiredSecrets": [
    "DEEPSEEK_API_KEY"
  ]
}
```

It does **not** export the Secret value.

Credential values such as API keys, access tokens, cookies, passwords, and private keys are excluded.

## Verify: what it means

DSH Crate can run Verify against an imported or prepared Profile and produce structured diagnostics.

A successful Profile Verify is **not** a claim that every plugin business capability works.

The current Preview does not directly provide:

- model conversation tests
- Session creation tests
- Core Tool tests
- plugin-specific business-function tests

Those capabilities remain outside the current verification claim.

## Full diagnostics

A failed operation should leave more than:

```text
Import failed.
```

DSH Crate keeps structured diagnostic information such as failure stage, severity, affected item, expected/observed state, command/exit code, evidence, impact, and suggested next checks.

The complete diagnostic JSON can be copied for bug reports and troubleshooting.

## Community Crates

Have a DSH setup that is genuinely useful and already tested?

**Useful, tested `.dshcrate` packages are welcome as Pull Requests.**

Good submissions include Coding environments, Research / Browser environments, minimal practical Profiles, specialized workflow environments, and useful plugin combinations.

A Community Crate should document:

- purpose
- included plugins
- embedded / reference-only choices
- required Secret names
- tested DSH version
- tested Node version
- tested operating system
- what was actually verified
- known limitations
- last tested date

`Verified` only means that the listed checks were actually executed in the listed environment. It does **not** mean universal compatibility.

If something was not tested, mark it as untested.

## Roadmap

### August 17, 2026 — Troubleshooting Skill

The next update is planned to add a Troubleshooting Skill that consumes DSH Crate diagnostics and helps identify the failing stage.

```text
Failure
  ↓
Diagnostic JSON
  ↓
Evidence-backed diagnosis
  ↓
Minimal repair / next check
  ↓
Verify again
```

The Skill does not replace Verify and cannot declare success without verification evidence.

### By August 20, 2026 — Broader environment portability

Planned additions:

- Conversation export/import
- plugin configuration portability
- plugin-owned workflow portability
- additional plugin-local portable data where ownership can be identified safely
- clearer export inventory
- privacy review before sharing user data

Credential values remain excluded.

The goal is to move from:

```text
Profile + Plugins
```

toward:

```text
Profile
+ Plugins
+ Plugin Config
+ Plugin Workflows
+ Selected Conversations / User Data
```

without blindly copying the entire `DSH_HOME`.

### By September 16, 2026 — Full Configuration Freeze

Freeze is a later, advanced workflow rather than the primary reason to use DSH Crate.

The goal is to preserve as much reconstructible DSH configuration as possible in one Crate.

Target scope includes Profile configuration, Bundles, plugin identity, embeddable plugin artifacts, plugin configuration, plugin-owned workflows, selected Conversations/user data, required Secret names, environment inventory, integrity evidence, and offline-restore reporting.

Target acceptance flow:

```text
Working DSH environment
        ↓
      Freeze
        ↓
   .dshcrate
        ↓
Fresh DSH_HOME
        ↓
     Restore
        ↓
      Verify
```

A Crate will only be described as fully frozen or offline-restorable when the corresponding restore test actually passes.

### By September 30, 2026 - Scheduled snapshots and startup-failure auto recovery

Make a working DSH environment recoverable without manual reconstruction.

**Scheduled snapshots**

- Snapshots are captured on a configurable schedule (disabled by default).
- A snapshot describes the Profile and its reconstructible state; it never copies the entire `DSH_HOME` and never contains Secret values (only required Secret names).
- Snapshots are read-only: they can be listed, Inspected, and Preflighted, but nothing writes into an existing snapshot.
- Snapshots support retention-based cleanup and can be restored into a fresh Profile without touching the original.

**Startup-failure auto recovery**

- When DSH fails to start, offer to restore the most recent snapshot into a new Profile.
- Recovery never overwrites the original Profile and only reports success after Verify: DSH actually boots, a new session can be created, and the configured smoke tests pass.
- Until that verification evidence exists, the status is `FAIL` or `UNTESTED` - never assumed `PASS`.
- Every automatic action is logged with machine-readable diagnostics for audit and bug reports.

Target acceptance flow:

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

## Development CLI

The Core currently exposes a development CLI:

```powershell
dsh-crate inspect .\example.dshcrate --json
dsh-crate import .\example.dshcrate --dsh-home $env:DSH_HOME --json
dsh-crate verify --dsh-home $env:DSH_HOME --profile my-profile --mode web --json
```

Use `--offline` to disable network fallback for missing reference-only plugins.

## What DSH Crate is not

DSH Crate is not trying to become:

- a generic plugin marketplace
- a second general-purpose Profile manager
- a cloud account or sync service
- a universal compatibility certification service
- a full DSH runtime installer

The focus is:

> **shareable environment packaging, controlled Import, migration, diagnostics, and evidence-based verification.**

## Contributing

Useful contributions include reproducible Import / Export failures, unusual npm / Git / tarball plugin sources, Windows / Linux / macOS test results, third-party packaging edge cases, documentation improvements, and useful tested Community Crates.

For bug reports, include:

```text
DSH version:
Node version:
OS / architecture:
Source Profile:
Expected behavior:
Observed behavior:
Diagnostic JSON:
```

Do not include real credentials.

## License

MIT License.

---

# 中文

## DSH Crate 是什么？

一套真正能用的 DeepSeek Harness 环境，往往不只是“装了哪些插件”。

它还可能依赖：

- 当前 Profile
- 已安装插件
- Bundle
- 插件来源
- Profile 配置
- required Secret 名称
- runtime 与环境信息

DSH Crate 会把这些环境信息整理成一个 `.dshcrate`：

```text
已经配置好的 DSH Profile
        ↓
      导出
        ↓
   setup.dshcrate
        ↓
      Inspect
        ↓
   分享 / Import
        ↓
   目标 Profile
        ↓
      Verify
```

它最核心的目标很简单：

> **一套 DSH 已经调好了，就应该能直接分享或迁移，而不是每次重新写一遍安装教程。**

## 为什么不直接压缩 `DSH_HOME`？

完全可以。

如果你的需求只是：

> “我自己备份一下这台电脑上的 DSH。”

那么直接压缩整个 DSH 目录可能反而是最简单的方案。

DSH Crate 解决的是另一个问题：

> **当你想检查、分享、跨机器迁移和受控重建环境时，不应该只能把整个 DSH_HOME 原样打包出去。**

一个普通目录压缩包可能同时包含或依赖：

- Credential
- 私人 Conversation
- 缓存
- 日志
- 临时状态
- 本机绝对路径
- `node_modules`
- 本机 runtime 状态

DSH Crate 更关注把环境拆成：

```text
可迁移数据
reference-only 依赖
required Secret 名称
明确排除的隐私 / runtime 数据
```

所以它更适合分享和受控 Import。

## 安装

把 Web 插件安装到 DSH Web Profile：

```bash
dsh plugin --profile web add dsh-crate-web
```

然后启动或重启 DSH Web，打开：

```text
Settings → DSH Crate
```

DSH Crate 是 DeepSeek Harness 的扩展，不负责安装或替代 DSH runtime。目标机器需要已经能够正常运行 DSH。

## 当前已经可以做什么

当前 Preview 支持：

- 查看当前 DSH Profile
- 查看 Profile 中已安装的插件和 Bundle
- 导出 Profile 为 `.dshcrate`
- 为插件选择 `embedded` 或 `reference-only`
- 记录 required Secret 名称，但不导出 Secret 值
- 在 Import 前执行 Inspect / Preflight
- 查看 `BLOCKER`、`WARNING`、`INFO` 和环境差异
- 预览目标 Profile、插件和风险
- 将 Crate 导入为新的 Profile
- 只有明确确认后才覆盖已有 Profile
- 对导入或准备好的 Profile 执行 Verify
- 查看完整错误诊断
- 复制完整诊断 JSON
- 查看操作历史
- 下载导出的 Crate
- 删除当前未运行的 Profile
- 明确确认后切换并重启 Profile

## 用 DSH Crate 排障（简版）

DSH 环境出问题时，不需要立刻删掉重装：

1. 打开 **Settings → DSH Crate**，把当前 Profile **Export** 成 `.dshcrate`；
2. 对 Crate 执行 **Inspect / Preflight**，它会列出 `BLOCKER`、`WARNING`、`INFO`，全程只读，不会改动你的环境；
3. **Import** 到一个全新 Profile（不要覆盖原来的），再执行 **Verify**；
4. 哪一步失败，就把完整诊断 JSON 复制出来，发给 Issue 或排查工具。

Inspect 和 Preflight 只读；只有你明确确认 Import 后才会真正改动。

## 分享一套已经调好的环境

这是 DSH Crate 当前最核心的使用场景。

没有 Crate 时，分享环境可能变成：

```text
先装插件 A
再装插件 B
用这个版本
Bundle 这样配
这里再改一下
还需要这些 Secret
……
```

有了 Crate：

```text
Export
  ↓
发送 setup.dshcrate
  ↓
Inspect
  ↓
Import
```

接收者可以先看到里面有什么，再决定是否导入。

## 把环境迁移到另一台机器

DSH Crate 也可以作为迁移层：

```text
电脑 A
  ↓
Export
  ↓
.dshcrate
  ↓
电脑 B
  ↓
Preflight
  ↓
Import
  ↓
Verify
```

这里的目标不是复制整台机器的状态，而是从可迁移的信息和明确的插件来源重新构建目标 DSH 环境。

## Embedded 与 Reference-only

### Embedded

在适合的情况下，把可安装的插件制品直接放进 Crate。

适合：

- 想保留实际安装制品
- 不想未来完全依赖原始来源
- 更重视可恢复性

```text
插件制品
+ Package Identity
+ 完整性信息
        ↓
     .dshcrate
```

### Reference-only

只保存插件来源和身份，在 Import 时重新获取。

适合原始来源预计长期可用、不适合重新分发插件制品，或希望 Crate 更小的场景。

同一个 Crate 可以同时包含 embedded 和 reference-only 插件。

## Import 前先 Inspect

打开 Crate 不等于直接安装。

Preflight 会把结果分为：

- **BLOCKER**：不应该继续 Import
- **WARNING**：可以继续，但存在已知风险或差异
- **INFO**：普通包信息或环境信息

真正写入之前，DSH Crate 会先显示目标 Profile、插件操作、环境差异、当前风险和 Import 决策。

## Import 安全边界

Import 默认创建新的 Profile。

已有 Profile 不会被静默替换。如果选择覆盖已有 Profile，必须明确确认。

当前安全边界还包括：

- 不静默覆盖当前正在运行的 Profile
- 只能删除当前未运行的 Profile
- Profile 切换与重启必须明确确认
- Inspect 和 dry-run 保持只读
- Import 失败时不应提交半成品目标 Profile
- 失败后保留完整诊断

## Secret 不进入 Crate

Crate 可以记录：

```json
{
  "requiredSecrets": [
    "DEEPSEEK_API_KEY"
  ]
}
```

但不会导出对应 Secret 的真实值。

API Key、Access Token、Cookie、密码和私钥等 Credential value 不应进入普通 Crate。

## Verify 到底验证了什么

DSH Crate 可以对已经导入或准备好的 Profile 执行 Verify，并输出结构化诊断。

但是：

> **Profile Verify 成功，不等于所有插件业务功能都已经验证。**

当前 Preview 不直接提供：

- 模型对话测试
- Session 创建测试
- Core Tool 测试
- 插件业务功能测试

所以这些能力不会因为 Import 或 Profile Verify 成功就被宣传成“已经验证”。

## 完整错误诊断

失败时不应该只剩一句：

```text
Import failed.
```

DSH Crate 会尽量保留失败阶段、Severity、出错对象、Expected、Observed、命令 / Exit Code、Evidence、Impact 和 Suggested Checks。

完整诊断 JSON 可以直接复制，用于 Issue、Bug 复现、后续排障和 Troubleshooting Skill。

## Community Crates

如果你有一套**真的好用，而且已经实际测试过**的 DSH 环境，欢迎通过 Pull Request 提交 `.dshcrate`。

适合投稿的内容包括：

- Coding 环境
- Research / Browser 环境
- 简洁但实用的 Profile
- 专用工作流环境
- 已经实际使用过的插件组合

Community Crate 至少应该说明：

- 用途
- 包含哪些插件
- 哪些是 embedded / reference-only
- 需要哪些 Secret 名称
- 测试时的 DSH 版本
- Node 版本
- 操作系统
- 实际验证了什么
- 已知限制
- 最后测试日期

`Verified` 只表示列出的检查确实在列出的环境中执行过，不表示全平台、全版本永久兼容。

没有测试的能力直接标记为未测试。

## 开发计划

### 2026 年 8 月 17 日 — Troubleshooting Skill

下一次更新计划加入排障 Skill：

```text
失败
 ↓
Diagnostic JSON
 ↓
基于证据判断问题
 ↓
给出最小修复 / 下一步检查
 ↓
再次 Verify
```

Skill 不替代 Verify，也不能在没有验证证据时自己宣布“已经修好”。

### 2026 年 8 月 20 日前 — 扩大环境迁移范围

计划增加：

- Conversation 导出 / 导入
- 插件配置导出 / 导入
- 插件内工作流导出 / 导入
- 能够安全识别归属关系的其他插件本地数据
- 更清楚的导出内容清单
- 分享用户数据前的隐私检查

Credential value 继续排除。

目标是从：

```text
Profile + Plugins
```

逐步扩展到：

```text
Profile
+ Plugins
+ Plugin Config
+ Plugin Workflows
+ Selected Conversations / User Data
```

但不会为了“完整”而直接复制整个 `DSH_HOME`。

### 2026 年 9 月 16 日前 — Full Configuration Freeze

Freeze 会作为后续高级能力，而不是 DSH Crate 当前最主要的卖点。

目标是尽可能把一套正在工作的 DSH 配置冻结成一个可恢复 Crate。

计划覆盖 Profile 配置、Bundle、插件身份、可嵌入插件制品、插件配置、插件内工作流、选定的 Conversation / 用户数据、required Secret 名称、环境清单、完整性证据和离线恢复状态。

目标验收：

```text
正在工作的 DSH 环境
        ↓
      Freeze
        ↓
   .dshcrate
        ↓
Fresh DSH_HOME
        ↓
     Restore
        ↓
      Verify
```

只有真正通过对应恢复测试的 Crate，才会被标记为 fully frozen / offline-restorable。

### 2026 年 9 月 30 日前 — 定时快照与启动失败自动恢复

让已经调好的 DSH 环境出问题时也能快速恢复，不需要手动重建。

**定时快照**

- 按可配置的间隔自动生成轻量快照（默认关闭）。
- 快照描述 Profile 及其可重建状态，不会复制整个 `DSH_HOME`，也不会包含 Secret 值（只记录 required Secret 名称）。
- 快照是只读的：可以列出、Inspect、Preflight，但不会写入已有快照。
- 快照支持按保留策略清理，也可以恢复到全新 Profile，不影响原 Profile。

**启动失败自动恢复**

- DSH 启动失败时，提供用最近快照恢复到新 Profile 的选项。
- 恢复不覆盖原 Profile；只有 Verify 通过（DSH 真正启动、能创建新会话、配置的 smoke test 真实通过）后才报告成功。
- 在没有验证证据前，状态只能是 `FAIL` 或 `UNTESTED`，不能自行判定为 `PASS`。
- 每次自动操作都会记录日志和机器可读诊断，便于审计和提交 Issue。

目标验收流程：

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

## 开发环境 CLI

Core 当前提供开发环境 CLI：

```powershell
dsh-crate inspect .\example.dshcrate --json
dsh-crate import .\example.dshcrate --dsh-home $env:DSH_HOME --json
dsh-crate verify --dsh-home $env:DSH_HOME --profile my-profile --mode web --json
```

使用 `--offline` 可以禁止 reference-only 插件在缺失时通过网络回退获取。

## DSH Crate 不准备做什么

DSH Crate 当前不会把主要精力投入到：

- 通用插件市场
- 第二套完整 Profile Manager
- 云账号 / 云同步
- 全生态兼容性认证平台
- DSH runtime 自动安装器

当前重点是：

> **环境分享、受控 Import、跨机器迁移、完整诊断和基于证据的 Verify。**

## 贡献

欢迎提交：

- 可复现的 Import / Export 问题
- 特殊 npm / Git / tarball 插件来源案例
- Windows / Linux / macOS 测试结果
- 第三方插件打包边界案例
- 文档修改
- 好用并经过实际验证的 Community Crate

Bug Report 建议包含：

```text
DSH version:
Node version:
OS / architecture:
Source Profile:
Expected behavior:
Observed behavior:
Diagnostic JSON:
```

请不要提交真实 Credential。

## License

MIT License.
