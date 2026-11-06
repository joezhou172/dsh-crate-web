# 手动可信发布实施计划

目标：复用 npm 已有效的 GitHub 信任关系，只允许手动发布已经验收的 Preview 制品，并下载校验。

架构：`workflow_dispatch` 接收版本与 SHA-256；从本仓库预发布制品下载指定 tgz，安全扫描、版本对齐检查、空环境安装通过后才授予发布作业 OIDC 权限。不从未验收源码重新打包，不使用长期 npm 令牌，不修改 latest。

技术：GitHub Actions、npm OIDC、现有 Python 发布扫描器与 Node 消费安装检查。

- [x] 核实正确仓库、现有改动和 npm 可信发布连接。
- [x] 在独立工作树改写 `.github/workflows/publish-dsh-crate-web.yml`，删除 push、pull_request、tag 自动入口，仅允许 main 手动触发。
- [x] 添加 `scripts/manual-release.py` 校验输入、哈希、包名、版本与完整制品；更新扫描器允许已验收的独立环境启动器。
- [x] 添加 `scripts/verify-published-release.mjs`，下载注册表实际 tgz 比对 SHA-256。
- [x] 本机验证输入拒绝、哈希拒绝、正常制品扫描和工作流结构；只提交发布流程相关文件。
- [x] 更新远程手动流程，上传 Preview.14 原始 tgz 到本仓库预发布制品，手动触发。
- [x] 观察 GitHub 发布结果；从 npm 新下载并复测实际 DSH UI，记录覆盖与未测试项。

本次授权包括发布流程配置、远程写入和 npm 发布。既有功能开发工作树保持不变。可信发布页面已显示有效，无需扩大 npm 权限。
