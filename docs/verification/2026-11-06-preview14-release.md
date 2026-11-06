# Preview.14 可信发布与下载验收

日期：2026-11-06。包：`dsh-crate-web@0.1.2-preview.14`。

## 发布结果

- PASS：复用 npm 已有效的 `joezhou172/dsh-crate-web` / `publish-dsh-crate-web.yml` 可信发布连接，无新增长期令牌。
- PASS：发布入口仅 `workflow_dispatch`，仅 main 可执行；普通推送、PR 和标签均不自动触发。手动输入版本、验收哈希与发布开关。
- PASS：从 GitHub 预发布制品下载已经本机验收的 tgz，不重新打包旧 main 功能源码。制品来源是本次本机验收产物，GitHub 工作流承担检查与发布，不声称该 tgz 由 main 源码重新构建。
- PASS：云端制品安全扫描、版本对齐、空环境普通 npm 安装及入口加载。没有 force、legacy-peer-deps 或忽略脚本安装选项；没有自动安装另一套 DSH。
- PASS：OIDC 发布成功，发布后的注册表制品哈希相同。`preview` 为 `0.1.2-preview.14`，`latest` 仍为 `0.1.1`。
- PASS：最终流程的只检查模式成功，publish 作业按开关跳过。

发布运行：https://github.com/joezhou172/dsh-crate-web/actions/runs/42158102676

最终流程只检查运行：https://github.com/joezhou172/dsh-crate-web/actions/runs/42158556992

SHA-256：`a1e02dcb2d21c2a689cba23b1a89d054706e356cfa8d82741f173743a19448ce`。

首次运行因只读 Actions 令牌无法读取草稿而失败，未执行 npm 发布。将同一哈希制品设为公开预发布后复跑成功；未扩大工作流写权限。

## npm 下载后的本机实际 UI 验证

环境：Windows 11、官方 DSH 0.2.2-rc.1。独立用户目录、DSH_HOME、缓存与 PATH；Profile 初始仅安装从 npm 下载的 Crate，未使用日常 desktop。全局 node/npm/pnpm/python/python3/py/git/dsh-crate 不可见。这是同机隔离模拟，不是 Win10 或虚拟机验收。

注册表安装一次成功，94 个文件与验收制品逐字节一致。本机下载安装驱动使用 ignore-scripts、legacy-peer-deps；上方独立云端普通安装未使用这两个选项。

真实 DSH UI 自动操作结果：

| 项目 | 状态 |
| --- | --- |
| 安全研究包检查、新建“安全研究 测试”环境 | PASS |
| 导入后询问是否打开；确认后启动目标 Profile | PASS |
| 独立浏览器渲染 DSH 主界面 | PASS |
| 重复打开复用 PID、运行环境禁止删除 | PASS |
| 从 UI 停止环境，desktop 继续可用 | PASS |
| 增量只新增：预览、执行、保留快照、导入后询问 | PASS |
| 增量更新：预览、执行、保留快照、导入后询问 | PASS |
| 故意损坏配置的环境启动失败，原 desktop 配置不变 | PASS |
| UI 未捕获异常、测试进程正常退出 | PASS |
| Win10 实机、其他 DSH 版本 | UNTESTED |
| 模型请求、全部插件业务、外部工具 | UNTESTED |
| 本轮重新注入导入失败并验证快照自动恢复 | UNTESTED |

本机证据保存在功能工作树：`work/release14-registry-consumer/download-verification.json`、`work/release14-open-1793936760860/report.json`、同目录 `opened-environment.png`。报告不上传用户运行数据。独立浏览器显示正常登录提示，未输入凭据。

## 使用边界

安装时明确选择 `dsh-crate-web@0.1.2-preview.14`；使用 latest 不会获得本次预览版。

各 Profile 保持独立，desktop 不被导入环境覆盖。由 Crate 打开的环境是其管理的子进程：退出原 DSH 或卸载当前 Crate 会停止这些环境；环境文件保留。

本次没有重新生成安全研究迁移包。发布及下载验证不能代替 Win10 实机、模型和插件业务验收。
