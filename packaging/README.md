# DSH Crate Web - 本地离线 EXE 安装器

把插件装进 DSH，双击运行即可，完全本地、不联网。

## 构建（本机）

```powershell
cd <dsh-crate-web 仓库目录>\packaging
.\build-installer.ps1
```

产物：`dist\dsh-crate-web-installer-<版本>.exe`（单文件，内嵌插件 tgz）。

## 安装器做了什么

1. 自动定位 DSH 数据目录（优先级：`/D=` 命令行参数 → `$DSH_HOME` 环境变量 → 扫描 `%APPDATA%` 下的桌面版数据目录 → 默认 `~/.dsh`），可在安装界面手动改。
2. 自动定位 DSH 命令行程序（`vendor\deepseek-harness\apps\cli\lib\bin.js`，桌面版安装/开发目录内）。
3. 调用 DSH 自带的插件安装命令，把内嵌的 `dsh-crate-web-*.tgz` 装进 `web` profile（首次使用会自动初始化 profile）。
4. 提示重启 DeepSeek Harness 生效。

## 静默安装

```powershell
# 普通静默安装（自动检测 DSH 数据目录，完成后自动退出）
.\dsh-crate-web-installer-0.1.1.exe /S

# 指定 DSH 数据目录（/D= 必须是最后一个参数，不带引号）
.\dsh-crate-web-installer-0.1.1.exe /S /D=C:\path\to\dsh

# 记录安装日志
.\dsh-crate-web-installer-0.1.1.exe /S /LOG=C:\path\install.log
```

静默安装成功退出码为 0，失败为 1。

## 前置条件

- 本机已安装 Node.js（安装器会检测 `%ProgramFiles%\nodejs\node.exe` 或 PATH）。
- 本机已安装 pnpm（安装器会检测 PATH 或 `%APPDATA%\npm`）。
- 已安装/使用过 DeepSeek Harness 桌面版（用于提供 DSH 命令行与数据目录）。

缺失时安装器会给出明确提示，不会静默失败。

## 调试

直接运行辅助脚本（不经 EXE）：

```powershell
node .\installer\helper.mjs --dsh-home "C:\Users\...\dsh"
```

可用环境变量覆盖检测：`DSH_CRATE_NODE`、`DSH_CRATE_PNPM`、`DSH_CRATE_CLI`。

## 说明

- 安装写进 profile 的是本地 tgz 路径（`file:...`），因此安装器会把 tgz 固定在
  `%LOCALAPPDATA%\dsh-crate-web-installer\`，避免路径失效。
- 卸载：运行 `dsh plugin --profile web remove dsh-crate-web`（或 DSH 提供的插件管理入口）。
- npm 发布与 EXE 安装是两条独立路径：EXE 完全不依赖 npm 发布。