# Preview.15 发布及下载复验

用户授权：发布 npm、配套桌面启动补丁、发布后下载验证、交付完整安全研究插件迁移包。本机日常安装不修改。

## 发布

- 包：dsh-crate-web@0.1.2-preview.15。
- 注册表标签：preview=0.1.2-preview.15，latest=0.1.1。
- 手动可信发布工作流：https://github.com/joezhou172/dsh-crate-web/actions/runs/42170269124，success。
- 源码分支：codex/release-preview15-20261106，发布提交 0c9d602；未合并 main，未更改仅手动触发策略。
- 制品 SHA256：55920102185abb689f865cb53c457fe7057a22ea7347e60af74c3f2f79331e5c。

## 下载后验证

work/release15-registry-consumer/download-verification.json：PASS。

- npm 下载内容与发布前验收 tgz 字节一致。
- 94 个安装文件与发布前制品逐一一致。
- 隔离空缓存普通 npm 安装 PASS，无 force/legacy-peer-deps/ignore-scripts；未自动安装另一套 DSH。
- 从下载后的安装目录生成完整安全研究候选包，运行实际 UI 全链路：36 项 PASS。
- 实际报告：work/release15-downloaded-ui-1793944115089/report.json；覆盖导入后确认切换、默认冷启动、替换快照、启动失败恢复、损坏默认自动回退；恢复核对 14 个关键文件 SHA256。
- 测试拥有的桌面进程已正常关闭，无模型调用。

## 配套工具与迁移包

桌面补丁使用自带 Python，只对用户显式指定的安装操作，要求目标进程关闭、原 ASAR 精确匹配。应用及恢复已在隔离副本测试，恢复哈希与官方原件一致；实际运行中拒绝修改，原文件哈希不变。

支持：Windows DSH 0.2.2-rc.1；原 ASAR SHA256 5fa8a6b21bceb8f3e99e30efa2270efd0cc773a11e42aa0488f804a64b34e637；补丁后 c81069977304e39bc8e5f1f43901afedb69a18f661d27b95c5da49ea4400b0dc。

完整插件迁移包：原 10 个包与配置不变，补入下载版 Crate Preview.15。迁移包 SHA256 d5f4455fa40c8ca1c772abdd0bbc7efdf90a217600793025b568ffe6413dcae0。与发布前正式版本候选迁移包字节一致。

交付目录：outputs/win10-preview15-20261106；ZIP：outputs/Crate-Win10-Preview15-20261106.zip。ZIP 生成后完整重读、CRC 与逐文件 SHA256 核对，最终哈希见 work/release15-package/delivery.json。

## 限制

另一台 Win10、其他 DSH 版本、全部插件业务、外部工具/MCP/技能迁移未验证。截图采集 DEGRADED，不作为视觉验收成功证据。npm 更新不会自动打官方桌面补丁。补丁/恢复不删除环境或会话，不携带个人凭据。
