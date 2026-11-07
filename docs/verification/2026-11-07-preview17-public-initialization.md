# Preview.17 发布与公网自动初始化验收

日期：2026-11-07；项目：dsh-crate-web；任务：Preview.17 发布及公网初始化。

## 结果

发布及自动初始化功能：PASS。附加的重启后截图留档：FAIL。因此包含截图的总报告保留 DEGRADED，不声称所有验证通过。

- npm `dsh-crate-web@0.1.2-preview.17` 已发布，`preview` 已指向该版，`latest` 仍为 `0.1.1`。
- 现有可信发布仅手动触发，未添加自动发布触发器。运行编号 `42336691673`，云端校验、普通安装、OIDC 发布和注册表下载哈希校验全部通过。
- 配套组件已上传本次 GitHub Release。匿名公网下载与内置清单的 SHA-256 一致。
- 本机重新从 npm 下载，不使用本地构建包替代；注册表完整性和发布前 SHA-256 一致。
- 在独立目录普通 npm 安装通过，没有 force、legacy-peer-deps 或 ignore-scripts；实际导出入口加载通过。

## 真实桌面流程

本机 Windows 11 专业工作站版 10.0.26200，主机 Node 24.13.0、npm 11.6.2；实际程序为官方 DSH 0.2.2-rc.1 的隔离副本，Crate 为注册表下载后的 Preview.17。主机 Node 版本不等同于 DSH 内嵌运行时版本。

两轮均执行：

1. 创建全新独立 Home 与未打补丁的程序副本，确认组件缓存为空。
2. 启动实际 Electron Desktop；插件自行从固定公网 URL 下载组件，校验并达到可启用状态。
3. 打开实际设置页面的 Crate，点击启用并确认。
4. 正常关闭该测试实例；维护工具完成程序快照及补丁应用，回执为 applied，并保留 user-data-dir。
5. 自动重启，插件 API 恢复，桌面维护能力启用。
6. 再次打开实际 Crate 页面，读回“Desktop support is enabled”、版本 Preview.17、无更新的正式版检查状态。

全部窗口运行于 Win32 非活动桌面，不调用 SwitchDesktop，不在主屏幕操作。未修改日常 DSH 安装，零模型请求；测试结束未遗留该目录下的 Desktop 进程。

## 截图限制

初始化完成、尚未应用前的真实页面截图已保存并视觉查看，页面正常。

重启后 `Page.captureScreenshot` 超时；在非活动桌面内将页面置前、另行重启现有测试副本并改用 `fromSurface=false` 后仍超时。页面文本读取与实际导航成功，但这不足以代替重启后的像素级验收。未切换主屏幕规避此限制，未将截图失败报告改写为 PASS。

## 证据

- `work/desktop-bootstrap/release17/workflow-result.json`
- `work/desktop-bootstrap/registry17/report.json`
- `work/desktop-bootstrap/registry17/clean/report.json`
- `work/desktop-bootstrap/public-desktop-screenshot-failure.json`
- `work/desktop-bootstrap/public-desktop-report.json`
- `work/desktop-bootstrap/screenshot-probe-report.json`
- `work/desktop-bootstrap/release17/verification-preview17.json`

npm 包 SHA-256：`d814013ef554e6f77e26abb73f399b45be2e0de020ee6e7249eb2ced858aa187`。

桌面组件 SHA-256：`33b6135cafe547d8b76862cb62be87c87f710254db0ab5ad5fbd138b14dd7496`。

## 未覆盖

另一台 Win10、其他 DSH 版本、公网被阻断的网络环境未在本轮验收。此次未重跑全部安全研究插件、模型调用和迁移业务；先前对应验收记录不能被本次发布与初始化测试替代。

首次启用仍需用户确认后从 DSH 菜单正常退出；之后快照、应用和重启由维护工具执行。
