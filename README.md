# DSH Crate — Preview

DSH Crate 为 DeepSeek Harness 的设置页提供环境包导出、检查、恢复、验证和历史记录。正式 npm 包名是 `dsh-crate-web`；本候选为 `0.1.2-preview.2`，使用 `preview` 标签，保留既有 `latest`。

可通过官方插件入口安装明确版本：

```powershell
dsh plugin --profile web add dsh-crate-web@0.1.2-preview.2
```

重启后打开 Settings → DSH Crate。离线环境可从同版本 tgz 安装。Windows x64 随包保留 Python 3.14.6，无需另外安装系统 Python。其他系统未完成本轮桌面验收。

Import 默认恢复到新 Profile，先执行 Preflight 和计划检查。覆盖、删除和切换已有 Profile 均需另外显式确认。导出排除凭据值；分享前仍应检查准备公开的内容。

默认 Verify 使用独立验证桌面并隔离 Home、工作区与缓存，不调用模型。模型、原生工具和各插件的真实业务验收必须有单独的执行证据；报告中的 UNTESTED 不能视为 PASS。

此 npm 包仅含 Crate 插件、Core 和必要运行文件，不包含完整 DSH 桌面，也不向官方安装目录写入 Windows 终端或 NARB 补丁。历史业务证据来自配套的 Windows x64 / DSH 0.2.1-rc.5 独立修补桌面；本候选调整了正式包身份，尚未完成该身份下的完整桌面复测，不能宣称任意官方桌面均已兼容。

已知限制：Windows 上 Import 偶发在临时 Profile 改为正式目录名时返回 WinError 5。界面会提示文件可能仍被占用或权限不足，并保留完整原始错误与回滚结果。请关闭正在使用目标目录的文件预览、编辑器或终端，核实权限与残留状态后手动重新导入；程序不会自动重试。历史故障的实际占用者尚未定位，当前提示不代表根因已修复。

本版本按维护者确认作为 Preview 发布：上述偶发问题、公共包身份下尚未完成的完整桌面复测，以及 Inspector 首启耗时未完全归因，均保留为已知限制。后续修复会升新版本发布，不覆盖本版本，也不把现有 UNTESTED 或 FAIL 改写为通过。

工作流先扫描提交与实际 tgz，再让发布任务复用同一 tgz 并核对 SHA-256。新代码必须升 prerelease 版本；同版本不同内容会停止。现有 npm Trusted Publisher 对应本仓库和 `publish-dsh-crate-web.yml`，无需把长期 npm Token 写入仓库。
