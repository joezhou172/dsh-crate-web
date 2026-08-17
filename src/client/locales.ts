export type DshCrateLocaleKey =
  | 'nav' | 'title' | 'intro' | 'export' | 'import' | 'inspect' | 'history'
  | 'profile' | 'noProfiles' | 'artifactMode' | 'embedded' | 'referenceOnly'
  | 'exportButton' | 'exporting' | 'choosePack' | 'inspectButton' | 'importButton'
  | 'confirmImport' | 'working' | 'noReport' | 'noHistory' | 'download'
  | 'plugins' | 'findings' | 'coreStatus' | 'rawJson' | 'diagnostic' | 'copyDiagnostic'
  | 'diagnosticCopied' | 'fullDiagnostic' | 'importPreview' | 'targetProfile' | 'warningCount'
  | 'requiredPlugins' | 'optionalPlugins' | 'environment' | 'coreDecision' | 'safety'
  | 'willNotOverwrite' | 'none' | 'verify' | 'verifyButton' | 'error'
  | 'installedBundles' | 'active' | 'installationAnchor' | 'anchorOnlyNote' | 'exportPlugins' | 'bundle' | 'notBundle'
  | 'importSuccess' | 'preparedProfile' | 'installedPlugins' | 'importMode' | 'newProfile'
  | 'overwriteProfile' | 'newProfileName' | 'overwriteWarning' | 'overwritePreview'
  | 'confirmOverwrite' | 'overwriteCanceled' | 'deleteProfile' | 'deleteProfileWarning'
  | 'confirmDelete' | 'deleteSuccess' | 'profileNameRequired' | 'profileNameExists'
  | 'cancel'
  | 'createProfile' | 'createProfilePlaceholder' | 'createProfileHint' | 'createPending' | 'createSuccess'
  | 'profileManagement' | 'currentRunningProfile' | 'switchProfile' | 'switchProfileWarning'
  | 'switchCanceled' | 'switchSuccess' | 'switchPending' | 'switchAlreadyActive'
  | 'exportSuccess' | 'inspectSuccess' | 'verifySuccess' | 'verifyFailed' | 'verifyFinished' | 'verifyUntestedNote' | 'importOverwritten'
  | 'declaredBundles' | 'runtimePlugins' | 'runtimeEnabled' | 'runtimeDisabled' | 'runtimePluginsInactive' | 'updatedAt' | 'refresh'
  | 'pluginListTab' | 'pluginListLoading' | 'pluginListError' | 'retry'
  | 'officialPlugins' | 'userPlugins' | 'officialBadge' | 'conflictWarning' | 'conflictBundles' | 'collapse' | 'expand'
  | 'confirmImportAction'
  | 'diagCode' | 'diagStage' | 'diagItem' | 'diagExpected' | 'diagObserved' | 'diagEvidence' | 'diagImpact'
  | 'diagOriginalProfile' | 'diagFailedProfile' | 'diagTemporaryProfile' | 'diagCanContinue' | 'diagSuggestedNext'

export const en: Record<DshCrateLocaleKey, string> = {
  nav: 'DSH Crate', title: 'DSH Crate', intro: 'Export, inspect, and import a tested DSH environment Crate.',
  export: 'Export', import: 'Import', inspect: 'Inspect', history: 'History', profile: 'Profile',
  noProfiles: 'No selectable Profiles were found in this DSH_HOME.', artifactMode: 'Artifact mode',
  embedded: 'Embedded', referenceOnly: 'Reference-only', exportButton: 'Export Crate', exporting: 'Exporting…',
  choosePack: 'Choose a .dshcrate file', inspectButton: 'Run Preflight', importButton: 'Import Crate',
  confirmImportAction: 'Confirm Import',
  confirmImport: 'Imports as a new Profile after a Preflight check. Continue?', working: 'Working…', noReport: 'No report yet.',
  noHistory: 'No DSH Crate operations have been recorded.', download: 'Download Crate', plugins: 'Plugins',
  findings: 'Findings', coreStatus: 'Core status', rawJson: 'Raw JSON', diagnostic: 'Failure diagnostic',
  copyDiagnostic: 'Copy full diagnostic', diagnosticCopied: 'Copied', fullDiagnostic: 'View full diagnostic',
  importPreview: 'Import preview', targetProfile: 'Target Profile', warningCount: 'Warnings',
  requiredPlugins: 'Required packages', optionalPlugins: 'Optional packages', environment: 'Environment required/current',
  coreDecision: 'Core canContinue', safety: 'Import safety', willNotOverwrite: 'Creates a new Profile only; it will not overwrite the original Profile.',
  none: 'None', verify: 'Verify', verifyButton: 'Run Verify', error: 'Operation failed',
  installedBundles: 'Installed Bundles', active: 'Active in this Profile', installationAnchor: 'Installation anchor only',
  anchorOnlyNote: 'Installed but not composed in this Profile (installation anchor only; not exported): ',
  exportPlugins: 'Exported plugins', bundle: 'Bundle', notBundle: 'Not a Bundle',
  importSuccess: 'Import successful', preparedProfile: 'Prepared Profile', installedPlugins: 'Installed plugins',
  importMode: 'Import mode', newProfile: 'Add new Profile', overwriteProfile: 'Overwrite existing Profile',
  newProfileName: 'New Profile name', overwriteWarning: 'This replaces all files in the selected Profile.',
  overwritePreview: 'Existing Profile will be replaced after confirmation.', confirmOverwrite: 'Confirm overwrite',
  overwriteCanceled: 'Overwrite canceled.', deleteProfile: 'Delete Profile', deleteProfileWarning: 'This permanently deletes the selected Profile.',
  confirmDelete: 'Confirm deletion', deleteSuccess: 'Profile deleted.', profileNameRequired: 'Profile name is required.',
  profileNameExists: 'That Profile name already exists.',
  cancel: 'Cancel',
  createProfile: 'New Profile', createProfilePlaceholder: 'new profile name', createProfileHint: 'A new Profile includes the official DSH bundles and the DSH Crate plugin by default.', createPending: 'Creating…', createSuccess: 'Profile created.',
  profileManagement: 'Profile management', currentRunningProfile: 'Currently running',
  switchProfile: 'Switch and restart Profile', switchProfileWarning: 'DSH will stop and restart using the selected Profile.',
  switchCanceled: 'Profile switch canceled.', switchSuccess: 'Profile switched and DSH restarted.',
  switchAlreadyActive: 'Profile is already running.',
  declaredBundles: 'Declared Bundles (Profile)', runtimePlugins: 'Runtime plugins (currently running Profile)', runtimeEnabled: 'enabled', runtimeDisabled: 'disabled', runtimePluginsInactive: 'Select the currently running Profile to see its live runtime plugin list.', updatedAt: 'Last refreshed', refresh: 'Refresh',
  pluginListTab: 'Plugin list', pluginListLoading: 'Reading plugins…', pluginListError: 'Plugins are temporarily unavailable.', retry: 'Retry',
  officialPlugins: 'Official built-in plugins', userPlugins: 'User-installed & written plugins', officialBadge: 'Official', conflictWarning: 'Conflicts with an official built-in; excluded from export', conflictBundles: 'Conflicted Bundles (not exported)', collapse: 'Collapse', expand: 'Expand',
  exportSuccess: 'Crate exported successfully.',
  inspectSuccess: 'Preflight finished.',
  verifySuccess: 'Verification passed.',
  verifyFailed: 'Verification failed.',
  verifyFinished: 'Verification finished.',
  verifyUntestedNote: 'UNTESTED means composition was checked only; runtime, model, session, and plugin behavior were NOT actually verified.',
  importOverwritten: 'Profile overwritten.',
  switchPending: 'Switching Profile and waiting for DSH ready…',
  diagCode: 'Code', diagStage: 'Stage', diagItem: 'Item', diagExpected: 'Expected', diagObserved: 'Observed',
  diagEvidence: 'Evidence', diagImpact: 'Impact', diagOriginalProfile: 'Original Profile', diagFailedProfile: 'Failed Profile',
  diagTemporaryProfile: 'Temporary Profile', diagCanContinue: 'Can continue', diagSuggestedNext: 'Suggested next step',
}

export const zh: Record<DshCrateLocaleKey, string> = {
  nav: 'DSH Crate', title: 'DSH Crate', intro: '导出、检查和导入经过测试的 DSH 环境 Crate。',
  export: '导出', import: '导入', inspect: '检查', history: '历史', profile: 'Profile',
  noProfiles: '当前 DSH_HOME 没有可选择的 Profile。', artifactMode: 'Artifact 模式',
  embedded: '内嵌', referenceOnly: '仅引用', exportButton: '导出 Crate', exporting: '导出中…',
  choosePack: '选择 .dshcrate 文件', inspectButton: '运行 Preflight', importButton: '导入 Crate',
  confirmImportAction: '确认导入',
  confirmImport: '将作为新 Profile 导入，导入前会先执行 Preflight 检查。是否继续？', working: '处理中…', noReport: '暂无报告。',
  noHistory: '还没有 DSH Crate 操作记录。', download: '下载 Crate', plugins: '插件',
  findings: '诊断项', coreStatus: 'Core 状态', rawJson: '原始 JSON', diagnostic: '失败诊断',
  copyDiagnostic: '复制完整诊断', diagnosticCopied: '已复制', fullDiagnostic: '查看完整诊断',
  importPreview: '导入预览', targetProfile: '目标 Profile', warningCount: 'WARNING 数量',
  requiredPlugins: 'required 包', optionalPlugins: 'optional 包', environment: '环境要求/当前值',
  coreDecision: 'Core canContinue', safety: '导入安全', willNotOverwrite: '只创建新 Profile；不会覆盖原 Profile。',
  none: '无', verify: '验证', verifyButton: '运行 Verify', error: '操作失败',
  installedBundles: '已安装 Bundle', active: '当前 Profile 已组合', installationAnchor: '仅安装锚点',
  anchorOnlyNote: '已安装但未组合进当前 Profile（仅安装锚点，不导出）：',
  exportPlugins: '导出插件', bundle: 'Bundle', notBundle: '普通依赖',
  importSuccess: '导入成功', preparedProfile: '已准备 Profile', installedPlugins: '已安装插件',
  importMode: '导入模式', newProfile: '添加新 Profile', overwriteProfile: '覆盖已有 Profile',
  newProfileName: '新 Profile 名称', overwriteWarning: '这会替换所选 Profile 中的全部文件。',
  overwritePreview: '确认后将替换已有 Profile。', confirmOverwrite: '确认覆盖',
  overwriteCanceled: '已取消覆盖。', deleteProfile: '删除 Profile', deleteProfileWarning: '这会永久删除所选 Profile。',
  confirmDelete: '确认删除', deleteSuccess: 'Profile 已删除。', profileNameRequired: '必须填写 Profile 名称。',
  profileNameExists: '该 Profile 名称已存在。',
  cancel: '取消',
  createProfile: '新建 Profile', createProfilePlaceholder: '新 Profile 名称', createProfileHint: '新 Profile 默认包含官方插件与本插件（DSH Crate）。', createPending: '创建中…', createSuccess: 'Profile 已创建。',
  profileManagement: 'Profile 管理', currentRunningProfile: '当前运行 Profile',
  switchProfile: '切换并重启 Profile', switchProfileWarning: 'DSH 将停止当前进程，并使用所选 Profile 重新启动。',
  switchCanceled: '已取消 Profile 切换。', switchSuccess: 'Profile 已切换并完成 DSH 重启。',
  switchAlreadyActive: '该 Profile 已在运行。',
  declaredBundles: '声明 Bundle（Profile）', runtimePlugins: '运行时插件（当前运行 Profile）', runtimeEnabled: '已启用', runtimeDisabled: '已禁用', runtimePluginsInactive: '选择当前运行的 Profile 以查看其实时运行的插件列表。', updatedAt: '最近刷新', refresh: '刷新',
  pluginListTab: '插件列表', pluginListLoading: '正在读取插件…', pluginListError: '暂时无法读取插件。', retry: '重试',
  officialPlugins: '官方内置插件', userPlugins: '用户安装与编写的插件', officialBadge: '官方', conflictWarning: '与官方内置插件冲突，已排除导出', conflictBundles: '冲突 Bundle（未导出）', collapse: '折叠', expand: '展开',
  exportSuccess: 'Crate 导出成功。',
  inspectSuccess: 'Preflight 检查完成。',
  verifySuccess: '验证通过。',
  verifyFailed: '验证未通过。',
  verifyFinished: '验证完成。',
  verifyUntestedNote: 'UNTESTED 表示仅验证了组合（composition），运行时、模型、会话、插件业务行为均未实际验证。',
  importOverwritten: 'Profile 已覆盖。',
  switchPending: '正在切换 Profile，等待 DSH ready…',
  diagCode: '诊断代码', diagStage: '失败阶段', diagItem: '对象', diagExpected: '预期', diagObserved: '实际', diagEvidence: '证据',
  diagImpact: '影响', diagOriginalProfile: '原 Profile 状态', diagFailedProfile: '失败 Profile 状态', diagTemporaryProfile: '临时 Profile 状态',
  diagCanContinue: '是否可继续', diagSuggestedNext: '建议下一步',
}
