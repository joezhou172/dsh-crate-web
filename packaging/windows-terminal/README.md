# Windows 终端宿主修复

该目录保存 DSH 0.2.1-rc.5 / Windows x64 的精确输入补丁和独立副本构建入口。它属于桌面宿主修复，**不随 npm 插件静默应用**，不修改用户原安装、Home、PowerShell Profile 或注册表。

已确认的原始故障是：打包 GUI EXE 作为 ConPTY 的 ACL runner 宿主时，runner 内 `GetStdHandle(-10)` 返回 NULL，受限 PowerShell 创建前即退出 127。管道关闭通知先于原生退出回调，旧 node-pty 又把退出码传播成 undefined，掩盖了原始错误。

补丁让独立桌面使用其随附的控制台 Node 运行原字节 ACL runner，保留原 sandbox 策略及显式 runner 覆盖优先级；同时修复退出事件、有效 PID 就绪、连接取消及 Windows PTY 收尾，并保留已采集的启动错误详情。不删除 required 插件，不放宽 ACL。

## 构建新副本

需要 Python 3.12 或更新版本，仅使用标准库。提供合法取得、与 manifest 中 EXE / ASAR / 控制台 Node 哈希完全一致的桌面目录；版本名相同不足以匹配。此仓库不分发官方桌面二进制或完整官方模块。

```powershell
python packaging/windows-terminal/build.py --source "<官方桌面目录>" --destination "<不存在的新目录>"
```

输入和输出不能嵌套，拒绝已有目标及重解析点。所有补丁与 ACL 依赖先核对哈希，再复制；不使用硬链接。EXE 仅更新与 ASAR 对应的完整性资源，不关闭完整性检查、不改 fuse；代码签名不会因此保持有效。失败时保留新副本现场，不自动删除或重试。

输出中的 `crate-terminal-fix-receipt.json` 记录输入 manifest 与输出身份。`BUILT_NOT_TESTED` 只表示构建完成，必须在独立 DSH_HOME、workspace、Electron userData、TEMP 和缓存中另做业务验收。

## 验证

```powershell
python -m unittest discover -s tests -p test_windows_terminal_build.py

# 可选：读取本地官方输入，应用实际补丁并执行真实模块的受控事件回归。
$env:DSH_CRATE_TEST_DESKTOP = "<官方桌面目录>"
python -m unittest discover -s tests -p test_windows_terminal_build.py
```

受控回归不启动桌面、Worker 或模型；没有指定本地桌面时，实际模块用例标为 skipped，不能据此声称真实终端通过。真实业务验收还需覆盖：打开终端、命令输出及文件标记、关闭、自然退出码、计划重启和移除 Crate 后继续可用，以及进程/Job/端点释放。

### 隔离目录的权限前提

验收夹具 `tests/windows_terminal_directory.py` 只创建明确 scope 内的新目录，并给原所有者显式保留 Modify + WRITE_OWNER，其他主体、owner、继承和官方沙箱策略不变。必须先准备整棵隔离运行目录的全新根目录，再在其中创建 Home、workspace、TEMP 和缓存，使子目录继承明确的所有者权限。只处理 workspace / TEMP 叶目录，仍可能因祖先目录不可访问而得到错误的工作目录。不要把它用于已有用户目录。仅继承 `OWNER RIGHTS` 的私有临时目录，可能在官方受限令牌下无法读取或写入；只补 WRITE_OWNER 不足以证明可用。

已观察到的失败链路是：沙箱子进程不能写入指定 TEMP → PowerShell 进入受限语言模式 → 编码／提示符初始化无法工作 → 最后报告就绪超时。应检查实际 PowerShell 语言模式、工作目录、指定 TEMP 写入及目录外写入仍被拒绝，不能通过关闭语言限制、增加 Everyone 权限或提高超时来制造通过。

在 manifest 锁定的 DSH 0.2.1-rc.5 / Windows x64 / 随包 Node 24.21.0 独立副本中，已实际验证恢复后、重启后和移除 Crate 后的 `terminal_open → terminal_send → terminal_close`：命令输出和文件标记正确、工作目录正确、目录外写入被拒绝，桌面正常退出，受控 Job 活动进程归零，相关 TCP 连接释放。自然退出 0 / 127 的事件传播另有实际 ConPTY 回归。调用通过显式隔离测试插件执行真实注册工具，不经过外部模型；逐名称管道释放没有独立探测。

默认零模型 Verify 的 composition、boot、surface_ready、new_session 和 cleanup 已实际通过；其模型、核心工具及插件业务步骤仍保留 `UNTESTED`，不能据此宣称完整业务验收通过。移除后的 API 检查应核对官方回退层语义：该版本静态回退层对未匹配的 POST 返回 405，不能把“必须是 404”用作卸载成功条件。

此补丁不包含 Inspector / NARB 的历史候选修复，不代表完整桌面产品交付，也不宣称适用所有 rc.5 制品或后续版本。node-pty 的变更基于其 MIT 许可模块；构建保留原安装内许可证，其他官方模块使用者仍须遵守其适用许可。
