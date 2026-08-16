<div align="center">

# DSH Crate

**把一整套 DeepSeek Harness 环境分享成一个可检查的文件。**

[![状态：Preview](https://img.shields.io/badge/status-preview-orange.svg)](#当前-preview)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](#license)
[![DeepSeek Harness](https://img.shields.io/badge/DeepSeek-Harness-4D6BFE.svg)](https://github.com/deepseek-ai/deepseek-harness)

[快速开始](#快速开始) · [工作方式](#工作方式) · [Community Crates](#community-crates) · [English](README.md)

</div>

DSH Crate 可以把已经配置好的 DeepSeek Harness Profile 导出为 `.dshcrate`：**导入前先检查，导入时受控重建，导入后再 Verify**。

不用再给别人发一长串插件列表、版本说明、Bundle 配置和操作步骤，直接发一个 Crate。

```mermaid
flowchart LR
    A["已经工作的 DSH Profile"] --> B["导出 .dshcrate"]
    B --> C["Inspect"]
    C --> D["Import"]
    D --> E["Verify"]
```

## 核心特点

- **分享完整环境** — 把已经工作的 DSH Profile 导出成一个 `.dshcrate`。
- **导入前先检查** — 在真正修改环境前查看插件、环境差异和风险。
- **插件来源可移植** — 适合时嵌入可安装制品，也可以保持 `reference-only`。
- **默认安全** — Secret 值不进入 Crate，Inspect 只读，已有 Profile 不会被静默覆盖。
- **导入后验证** — 对重建后的 Profile 执行 Verify，失败时保留结构化诊断。

## 快速开始

把 Web 插件安装到 DSH Web Profile：

```bash
dsh plugin --profile web add dsh-crate-web
```

重启 DSH Web，然后打开：

```text
Settings → DSH Crate
```

DSH Crate 是 DeepSeek Harness 的扩展，不负责安装或替代 DSH runtime。目标机器需要已经能够正常运行 DSH。

## 工作方式

### 1. Export

选择一个已经配置好的 Profile，导出为 `.dshcrate`。

Crate 可以记录：

- Profile 元数据
- 已安装插件的身份与来源
- Bundle
- required Secret 名称
- 环境信息
- 适合嵌入的插件制品

Secret **真实值**不会被导出。

### 2. Inspect

Import 前先执行 Preflight：

- **BLOCKER** — 不应该继续 Import
- **WARNING** — 可以继续，但存在已知风险或差异
- **INFO** — 普通包信息或环境信息

真正写入之前，可以先查看目标 Profile、插件操作、环境差异和检测到的风险。

### 3. Import

Import 默认创建**新的 Profile**。

覆盖已有 Profile 必须明确确认；当前正在运行的 Profile 不会被静默替换。

### 4. Verify

Import 后，DSH Crate 可以对导入或准备好的 Profile 执行 Verify，并生成结构化诊断。

Verify PASS 只代表 **DSH Crate 实际执行的检查通过了**，不代表模型、Session、Core Tool 或所有第三方插件业务功能全部可用。

## 当前 Preview

当前版本支持：

- 查看当前 Profile、已安装插件和 Bundle
- 导出 Profile 为 `.dshcrate`
- 为插件选择 `embedded` 或 `reference-only`
- 记录 required Secret 名称，但不导出 Secret 值
- Inspect / Preflight，展示 `BLOCKER`、`WARNING`、`INFO` 和环境差异
- Import 前预览目标 Profile、插件和风险
- 导入为新的 Profile
- 明确确认后覆盖已有 Profile
- 对导入或准备好的 Profile 执行 Verify
- 查看完整错误诊断并复制 diagnostic JSON
- 查看操作历史并下载导出的 Crate
- 删除当前未运行的 Profile
- 明确确认后切换并重启 Profile

当前 Preview **不直接测试**：

- 模型对话
- Session 创建
- Core Tool 执行
- 插件业务功能

因此这些能力不属于当前 Verify 的承诺范围。

## 分享或迁移

### 分享一套环境

没有 Crate 时：

```text
先装插件 A
再装插件 B
用这个版本
启用这些 Bundle
改这些配置
还需要这些 Secret
……
```

有了 DSH Crate：

```text
Export → 发送 setup.dshcrate → Inspect → Import
```

接收者可以先看到里面有什么，再决定是否导入。

### 迁移到另一台机器

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

目标不是把原机器逐字节复制过去，而是根据可迁移信息和明确的插件来源，在目标机器重建 DSH 环境。

## Embedded 与 Reference-only

### Embedded

在适合的情况下，把可安装的插件制品直接放进 Crate。

适合更重视实际安装制品保存、而不是文件体积的场景。

```text
插件制品
+ Package Identity
+ 完整性信息
        ↓
     .dshcrate
```

### Reference-only

只保存插件来源和身份，在 Import 时重新获取。

适合：

- 原始来源预计长期可用
- 不适合重新分发插件制品
- 希望 Crate 更小

同一个 Crate 可以同时包含两种模式。

## Community Crates

`.dshcrate` 不只是备份文件，也可以是一套可以直接复用的 DSH 环境。

**好用、经过实际验证的 Community Crate，欢迎通过 Pull Request 提交。**

适合投稿的内容包括：

- Coding 环境
- Research / Browser 环境
- 简洁但真正实用的 Profile
- 专用工作流环境
- 已经实际使用过的插件组合

Community Crate 至少应该说明：

- 用途
- 包含哪些插件
- embedded / reference-only 选择
- required Secret 名称
- 测试时使用的 DSH 版本
- Node 版本
- 操作系统
- 实际验证范围
- 已知限制
- 最后测试日期

`Verified` 只表示列出的测试确实在列出的环境中运行过，不表示全平台、全版本永久兼容。

## 安全边界

DSH Crate 的设计原则是：所有重要修改都应该显式、可检查。

- Secret 值不进入普通 Crate。
- Inspect 和 dry-run 保持只读。
- 已有 Profile 不会被静默覆盖。
- 覆盖、切换、重启和破坏性 Profile 操作需要明确确认。
- Import 失败时不应提交半成功目标。
- 失败后仍保留完整诊断。

## FAQ

### 为什么不直接压缩 `DSH_HOME`？

完全可以。

如果只是给自己备份当前机器，直接压缩整个 DSH 目录可能反而是最简单的方案。

DSH Crate 解决的是另一个问题：**分享、迁移、检查和受控重建**，而不是直接复制整个 DSH home。

普通压缩包可能同时包含或依赖 Credential、私人 Conversation、缓存、日志、临时状态、本机绝对路径、`node_modules` 和本地 runtime 状态。

DSH Crate 更关注把环境拆成可迁移数据、reference-only 依赖、required Secret 名称，以及明确排除的隐私 / runtime 数据。

### Verify 到底证明了什么？

只证明 DSH Crate 实际执行过的检查。

如果没有显式测试模型对话、Session 创建、Core Tool 或插件业务能力，那么 Profile Verify 成功也不能被解释成这些能力已经通过。

### DSH Crate 是 Profile Manager 吗？

Profile 管理不是主要产品。

DSH Crate 的重点是**可分享环境制品、受控 Import、跨机器迁移、诊断和基于证据的 Verify**，而不是再做一套通用 Profile Manager。

## Roadmap

近期开发方向会刻意保持收敛：

- **Troubleshooting Skill** — 读取 diagnostic JSON，定位失败阶段，基于证据提出最小修复，然后再次 Verify。
- **更完整的环境迁移** — 增加 Conversation、插件配置、插件内工作流，以及能够安全识别归属关系的其他插件本地数据。
- **Full Configuration Freeze** — 后续高级能力，尽可能保存可重建的 DSH 配置，并明确报告离线恢复是否真正经过验证。

Freeze 是高级工作流，不是 DSH Crate 当前最主要的使用理由。

## 开发环境 CLI

Core 当前提供开发环境 CLI：

```powershell
dsh-crate inspect .\example.dshcrate --json
dsh-crate import .\example.dshcrate --dsh-home $env:DSH_HOME --json
dsh-crate verify --dsh-home $env:DSH_HOME --profile my-profile --mode web --json
```

使用 `--offline` 可以禁止缺失 reference-only 插件时通过网络回退获取。

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
