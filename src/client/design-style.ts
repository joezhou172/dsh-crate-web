// 依据 DSH rc.5 ui-theme 与 ui-primitives：由宿主提供主题变量，不设置独立主题。
export const DESIGN_STYLE = `
.dsh-crate-section{--crate-accent:var(--dsw-alias-brand-primary);--crate-border:var(--dsw-alias-border-l2);--crate-muted:var(--dsw-alias-label-tertiary);--crate-surface:var(--dsw-alias-bg-layer-1);font-family:var(--dsw-font-family);font-size:14px;gap:24px;color:var(--dsw-alias-label-primary)}
.dsh-crate-section *{box-sizing:border-box}.dsh-crate-icon{flex:none;vertical-align:middle}
.dsh-crate-header{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:4px 0 0}
.dsh-crate-brand{display:flex;align-items:center;gap:14px;min-width:0}.dsh-crate-brand>.dsh-crate-icon{width:30px;height:30px;color:var(--crate-accent)}
.dsh-crate-heading{font-size:22px;letter-spacing:-.5px;font-weight:600;line-height:1.3}.dsh-crate-intro{font-size:13px;margin-top:4px;line-height:1.5}
.dsh-crate-manage{background:transparent;border:0;color:var(--crate-accent);font:inherit;font-weight:500;padding:10px 0 10px 12px;cursor:pointer;flex:none;min-height:44px}
.dsh-crate-section [data-field=profileManagement]>summary{display:none}.dsh-crate-section [hidden]{display:none!important}
.dsh-crate-tabs{gap:28px;min-height:48px;overflow-x:auto;border-color:var(--crate-border)}.dsh-crate-tab{padding:10px 4px 13px;font-size:15px;min-height:44px;border-bottom:3px solid transparent;color:var(--crate-muted)}.dsh-crate-tab[data-active=true]{border-bottom:3px solid var(--crate-accent);font-weight:600}
.dsh-crate-form{gap:22px}.dsh-crate-section-title{font-size:19px;line-height:1.4;margin:0 0 2px;font-weight:600}
.dsh-crate-label,.dsh-crate-preset{font-size:14px;gap:8px}.dsh-crate-select,.dsh-crate-file{min-height:44px;padding:10px 12px;font:inherit;border-color:var(--crate-border);border-radius:8px;background:var(--crate-surface)}
.dsh-crate-environment{display:flex;align-items:flex-end;gap:16px}.dsh-crate-environment>.dsh-crate-label{flex:1;min-width:0}.dsh-crate-running{display:flex;align-items:center;gap:8px;min-height:44px;flex:none;font-size:13px;color:var(--crate-muted)}.dsh-crate-running i{width:8px;height:8px;border-radius:50%;background:var(--dsw-alias-state-success-primary)}
.dsh-crate-disclosures{border:1px solid var(--crate-border);border-radius:10px;overflow:hidden}.dsh-crate-disclosures>.dsh-crate-inventory{border:0;border-radius:0;padding:0 16px;font-size:13px}.dsh-crate-disclosures>.dsh-crate-inventory+*{border-top:1px solid var(--crate-border)}
.dsh-crate-disclosures summary{padding:16px 0;font-size:14px;min-height:54px;list-style:none;display:flex;align-items:center;gap:10px}.dsh-crate-disclosures summary::-webkit-details-marker{display:none}.dsh-crate-disclosures summary::after{content:'›';margin-left:auto;font-size:22px;font-weight:400;color:var(--crate-muted)}.dsh-crate-disclosures details[open]>summary::after{transform:rotate(90deg)}.dsh-crate-disclosures details[open]{padding-bottom:16px}
.dsh-crate-count{display:inline-flex;align-items:center;justify-content:center;min-width:26px;padding:1px 8px;border-radius:20px;font-size:12px;font-weight:500;background:var(--dsw-alias-interactive-bg-hover)}
.dsh-crate-preset{display:flex;flex-direction:column;align-items:flex-start}.dsh-crate-preset select{width:min(100%,280px)}
.dsh-crate-export-actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding-top:22px;margin-top:8px;border-top:1px solid var(--crate-border)}.dsh-crate-export-actions .dsh-crate-muted{font-size:12px}
.dsh-crate-button,.dsh-crate-secondary{min-height:44px;font:inherit;font-size:14px;font-weight:500;padding:11px 16px;border-radius:8px;display:inline-flex;align-items:center;justify-content:center;gap:8px;line-height:1.4}
.dsh-crate-button{background:var(--crate-accent,#3865e8)}.dsh-crate-secondary{border-color:var(--crate-border,#d8dfea)}.dsh-crate-button:disabled{opacity:.45}
.dsh-crate-section :is(input,select):focus-visible{outline:2px solid var(--crate-accent);outline-offset:3px}.dsh-crate-history-item{flex-wrap:wrap;font-size:13px;padding:14px 0}.dsh-crate-inventory{font-size:13px;padding:14px;gap:10px}
.dsh-crate-report-dialog{font-family:var(--dsw-font-family);font-size:14px;width:min(660px,calc(100vw - 32px));padding:28px;border-color:var(--dsw-alias-border-l2);box-shadow:var(--dsw-shadow-lv3);line-height:1.55}
.dsh-crate-report-dialog::backdrop{background:var(--dsw-alias-bg-mask-1);backdrop-filter:var(--dsw-mask-blur)}.dsh-crate-report-dialog header{margin-bottom:24px}.dsh-crate-report-heading{display:flex;align-items:center;gap:12px;min-width:0}.dsh-crate-report-dialog h3{font-size:21px;line-height:1.4}.dsh-crate-report-heading>.dsh-crate-icon{color:var(--dsw-alias-brand-primary);width:28px;height:28px}
.dsh-crate-warning{width:36px;height:36px;display:inline-flex;align-items:center;justify-content:center;border-radius:50%;background:var(--dsw-alias-state-error-primary);color:white;font-size:25px;font-weight:600;flex:none}
.dsh-crate-close{display:inline-flex;justify-content:center;align-items:center;background:transparent;color:inherit;border:0;width:44px;height:44px;flex:none;border-radius:8px;cursor:pointer}.dsh-crate-close:hover{background:var(--dsw-alias-interactive-bg-hover)}.dsh-crate-close:disabled{opacity:.4;cursor:default}
.dsh-crate-diagnostic-label{display:block;font-weight:600;margin-bottom:8px}.dsh-crate-report-dialog pre{margin:0 0 24px;padding:16px;min-height:160px;max-height:38dvh;border-color:var(--dsw-alias-border-l2);border-radius:8px;background:var(--dsw-alias-bg-module-platform);font:12px/1.7 var(--ds-font-family-code);tab-size:2}
.dsh-crate-recipient{display:flex;align-items:center;gap:10px;padding-top:20px;border-top:1px solid var(--dsw-alias-border-l2);font-size:13px}.dsh-crate-recipient>.dsh-crate-icon{color:var(--dsw-alias-brand-primary)}.dsh-crate-recipient>span{flex:none}.dsh-crate-recipient strong{font-weight:500;min-width:0;overflow-wrap:anywhere;padding:10px 12px;background:var(--dsw-alias-bg-module-platform);border-radius:7px;flex:1}
.dsh-crate-dialog-actions{gap:12px;margin-top:20px}.dsh-crate-dialog-actions button{flex:1;align-self:stretch}.dsh-crate-dialog-actions .dsh-crate-secondary{color:inherit;border-color:var(--dsw-alias-border-l2)}.dsh-crate-report-dialog [role=status]{font-size:13px;margin:12px 0 0}.dsh-crate-report-dialog details{margin-top:12px}
.dsh-crate-error-summary{margin:0 0 12px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.dsh-crate-stage{display:inline-block;margin:0 0 20px;padding:3px 10px;border-radius:20px;color:inherit;background:var(--dsw-alias-interactive-bg-hover-danger);font-size:12px;max-width:100%;overflow-wrap:anywhere}
/* 与官方 Button / Input / Modal 的语义色和几何保持一致。 */
.dsh-crate-button{background:var(--dsw-alias-button-primary-fill);color:var(--dsw-alias-label-primary-foreground)}
.dsh-crate-button:not(:disabled):hover{background:var(--dsw-alias-button-primary-hover)}
.dsh-crate-button,.dsh-crate-secondary{min-height:36px;border-radius:18px;padding:7px 14px;line-height:22px;font-weight:400}
.dsh-crate-button:disabled,.dsh-crate-secondary:disabled{opacity:.4;cursor:not-allowed}
.dsh-crate-secondary:not(:disabled):hover,.dsh-crate-manage:not(:disabled):hover,.dsh-crate-close:not(:disabled):hover{background:var(--dsw-alias-interactive-bg-hover)}
.dsh-crate-secondary:not(:disabled):active,.dsh-crate-manage:not(:disabled):active{background:var(--dsw-alias-interactive-bg-active)}
.dsh-crate-select,.dsh-crate-file{min-height:32px;padding:5px 8px;line-height:22px}
.dsh-crate-report-dialog,.dsh-crate-modal{background:var(--dsw-alias-bg-layer-2);border:1px solid var(--dsw-alias-border-inverted);border-radius:24px;box-shadow:var(--dsw-shadow-lv3)}
.dsh-crate-report-dialog h3{font-size:16px;line-height:24px;font-weight:500}
.dsh-crate-warning{background:var(--dsw-alias-interactive-bg-hover-danger);color:var(--dsw-alias-state-error-primary)}
.dsh-crate-modal-backdrop{background:var(--dsw-alias-bg-mask-1);backdrop-filter:var(--dsw-mask-blur)}
.dsh-crate-section :focus-visible{outline-color:var(--dsw-alias-brand-primary)}
@media(max-width:600px){.dsh-crate-section{gap:18px}.dsh-crate-header{align-items:flex-start;gap:8px}.dsh-crate-brand{gap:10px}.dsh-crate-heading{font-size:20px}.dsh-crate-intro{font-size:12px}.dsh-crate-brand>.dsh-crate-icon{width:24px;height:24px}.dsh-crate-manage{font-size:12px;padding:4px 0;min-height:44px}.dsh-crate-tabs{gap:20px}.dsh-crate-form{gap:18px}.dsh-crate-environment{flex-wrap:wrap;gap:6px}.dsh-crate-environment>.dsh-crate-label{flex-basis:100%}.dsh-crate-running{min-height:24px}.dsh-crate-export-actions{gap:10px}.dsh-crate-export-actions>button{flex:1}.dsh-crate-export-actions>.dsh-crate-muted{flex-basis:100%}.dsh-crate-report-dialog{padding:20px}.dsh-crate-report-dialog h3{font-size:16px}.dsh-crate-dialog-actions{flex-direction:column}.dsh-crate-recipient{flex-wrap:wrap}.dsh-crate-recipient strong{flex-basis:100%}.dsh-crate-report-dialog pre{max-height:32dvh;min-height:100px}.dsh-crate-select,.dsh-crate-file{font-size:16px}}

/* Crate 主页与二级页共用宿主 options 滚动区域，不给列表另设滚动框。 */
.dsh-crate-section{flex-shrink:0;overflow:visible}
.dsh-crate-page{display:flex;flex-direction:column;gap:24px;min-width:0;overflow:visible}
.dsh-crate-subpage-header{display:flex;align-items:flex-start;flex-wrap:wrap;gap:16px}
.dsh-crate-subpage-header .dsh-crate-muted{margin-top:4px}
.dsh-crate-page-links{display:flex;flex-direction:column;border:1px solid var(--crate-border);border-radius:10px;overflow:hidden}
.dsh-crate-page-link{display:flex;align-items:center;gap:12px;width:100%;min-height:60px;padding:14px 16px;border:0;background:transparent;color:inherit;font:inherit;text-align:left;cursor:pointer}
.dsh-crate-page-link+*{border-top:1px solid var(--crate-border)}
.dsh-crate-page-link>span:first-child{flex:1;min-width:0;overflow-wrap:anywhere}
.dsh-crate-page-link>span:last-child{font-size:22px;color:var(--crate-muted)}
.dsh-crate-page-link:hover{background:var(--dsw-alias-interactive-bg-hover)}
.dsh-crate-page-link:disabled{opacity:.4;cursor:not-allowed}
[data-dsh-module=settings]:has(.dsh-crate-section)>div:last-child{min-height:0}
[data-dsh-module=settings]:has(.dsh-crate-section)>div:last-child>div:last-child{overflow-y:auto;min-height:0}
@media(max-width:600px){.dsh-crate-page{gap:18px}.dsh-crate-subpage-header{gap:12px}}

.dsh-crate-runtime-choice{display:flex;align-items:center;gap:8px;min-height:44px;cursor:pointer}
[data-field="runtimePlugin"]{flex-wrap:wrap;gap:8px 16px}

/* 所有页面共用排版层级；次要操作不与标题和主要动作争夺视觉重心。 */
.dsh-crate-section{font-size:14px;line-height:1.5}
.dsh-crate-page{gap:20px}
.dsh-crate-header{align-items:flex-start;gap:16px}
.dsh-crate-heading{font-size:21px;letter-spacing:-.3px}
.dsh-crate-brand{gap:10px}.dsh-crate-brand>.dsh-crate-icon{width:24px;height:24px}
.dsh-crate-manage{font-size:13px;color:var(--dsw-alias-label-secondary);padding:0 8px;min-height:36px}
.dsh-crate-tabs{gap:24px;min-height:44px}.dsh-crate-tab{font-size:14px;border-bottom-width:2px;padding:8px 0 10px}.dsh-crate-tab[data-active=true]{border-bottom-width:2px}
.dsh-crate-form{gap:18px}.dsh-crate-section-title{font-size:18px;font-weight:600;line-height:1.5}
.dsh-crate-label{font-size:13px;color:var(--dsw-alias-label-secondary)}
.dsh-crate-select,.dsh-crate-file{color:var(--dsw-alias-label-primary);min-height:36px;font-size:14px}
.dsh-crate-page-link{min-height:52px;padding:12px 14px;font-size:14px}
.dsh-crate-count{background:transparent;color:var(--crate-muted);padding:0;font-variant-numeric:tabular-nums}
.dsh-crate-running{min-height:36px;font-size:12px;gap:6px}
.dsh-crate-export-actions{padding-top:16px;margin-top:0;gap:10px}
.dsh-crate-section .dsh-crate-button:disabled{background:transparent;color:var(--crate-muted);border:1px solid var(--crate-border);opacity:1}
.dsh-crate-subpage-header{flex-direction:column;gap:12px}
.dsh-crate-text-button{border:0;background:transparent;color:var(--dsw-alias-label-secondary);padding:6px 8px;min-height:36px;font-size:13px;border-radius:8px}
.dsh-crate-subpage-header>.dsh-crate-text-button{margin-left:-8px}
.dsh-crate-subpage-header .dsh-crate-muted{margin:2px 0 0;font-size:13px}
.dsh-crate-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px}
.dsh-crate-selection{border:0;padding:0;border-radius:0;gap:12px;font-size:14px}
.dsh-crate-selection>strong{font-size:13px;font-weight:500;color:var(--dsw-alias-label-secondary)}
.dsh-crate-selection>p{margin:0;font-size:13px}
.dsh-crate-selection>.dsh-crate-choice-controls{display:flex;gap:8px;padding-bottom:8px}
.dsh-crate-selection>.dsh-crate-choice-controls>input{flex:1;min-width:0}
.dsh-crate-choice{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 0;margin:0;border-bottom:1px solid var(--crate-border)}
.dsh-crate-choice-name{display:flex;align-items:center;gap:12px;min-width:0;flex:1;cursor:pointer}
.dsh-crate-plugin-copy{display:flex;flex-direction:column;gap:4px;min-width:0;overflow-wrap:anywhere}
.dsh-crate-plugin-copy strong{font-size:14px;font-weight:500}.dsh-crate-plugin-copy>.dsh-crate-muted{font-size:12px}
.dsh-crate-choice>.dsh-crate-choice-controls{display:flex;gap:6px;align-items:center;flex-wrap:wrap;justify-content:flex-end;flex:none;max-width:48%}
.dsh-crate-choice-controls select{font-size:13px;max-width:100%}
.dsh-crate-section input[type=checkbox]{width:16px;height:16px;flex:none;margin:0;accent-color:var(--crate-accent)}
[data-field=runtimePlugin]{display:grid;grid-template-columns:20px minmax(0,1fr) auto;align-items:center;justify-content:initial;gap:12px;padding:12px 0;font-size:13px}
.dsh-crate-runtime-choice{min-height:36px;min-width:20px}
.dsh-crate-sr-only{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
.dsh-crate-group-head{font-size:13px}
@media(max-width:600px){
.dsh-crate-page{gap:18px}.dsh-crate-choice{flex-wrap:wrap;gap:10px}.dsh-crate-choice-name{flex-basis:100%}
.dsh-crate-choice>.dsh-crate-choice-controls{margin-left:28px;max-width:calc(100% - 28px);justify-content:flex-start}
[data-field=runtimePlugin]{grid-template-columns:20px minmax(0,1fr)}
[data-field=runtimePlugin]>.dsh-crate-muted{grid-column:2}
.dsh-crate-selection>.dsh-crate-choice-controls{flex-wrap:wrap}
.dsh-crate-select,.dsh-crate-file{font-size:16px}
}

.dsh-crate-file::file-selector-button{font:inherit;color:var(--dsw-alias-label-primary);background:var(--dsw-alias-interactive-bg-hover);border:0;border-radius:6px;padding:4px 10px;margin-right:10px;cursor:pointer}
.dsh-crate-file::file-selector-button:hover{background:var(--dsw-alias-interactive-bg-active)}

/* 与官方 PluginsSettingsSection、Button、Input 的实际样式对齐。 */
.dsh-crate-section{font-family:inherit;font-synthesis:inherit;line-height:22px;font-weight:400;gap:14px}
.dsh-crate-page{gap:14px}.dsh-crate-form{gap:14px}
.dsh-crate-heading,.dsh-crate-section-title{font-size:18px;line-height:26px;font-weight:600;letter-spacing:normal}
.dsh-crate-brand>.dsh-crate-icon{display:none}
.dsh-crate-header{padding:0;gap:12px}.dsh-crate-intro{font-size:13px;line-height:20px;margin-top:4px}
.dsh-crate-tabs{gap:22px;min-height:0;margin-top:2px;align-items:flex-end}
.dsh-crate-tab{font-size:13px;line-height:20px;padding:7px 1px 9px;min-height:36px;font-weight:400}
.dsh-crate-tab[data-active=true]{font-weight:400}
.dsh-crate-label{font-size:14px;line-height:22px;color:var(--dsw-alias-label-primary);gap:6px}
.dsh-crate-file,.dsh-crate-select{min-height:32px;padding:4px 8px;font-size:14px;line-height:22px;border-radius:8px;background:var(--dsw-alias-bg-layer-1)}
.dsh-crate-file::placeholder{color:var(--dsw-alias-label-dimmed)}
.dsh-crate-button,.dsh-crate-secondary{min-height:36px;padding:7px 14px;border-radius:18px;font-size:14px;line-height:22px;font-weight:400;gap:4px}
.dsh-crate-section .dsh-crate-button:disabled{background:var(--dsw-alias-button-primary-fill);color:var(--dsw-alias-label-primary-foreground);border:0;opacity:.4}
.dsh-crate-text-button{border:0;padding:7px 10px;background:transparent;color:var(--dsw-alias-label-primary);font-size:14px}
.dsh-crate-subpage-header{gap:8px}.dsh-crate-subpage-header>.dsh-crate-text-button{margin-left:-10px}
.dsh-crate-page-link{min-height:48px;padding:10px 12px}
.dsh-crate-selection{gap:12px}.dsh-crate-choice{padding:12px 0;gap:10px}
.dsh-crate-choice-name{gap:10px}.dsh-crate-plugin-copy{gap:2px}
.dsh-crate-plugin-copy strong{font-size:14px;line-height:22px;font-weight:500}
.dsh-crate-plugin-copy>.dsh-crate-muted{font-size:13px;line-height:20px}
.dsh-crate-choice>.dsh-crate-choice-controls{gap:4px}
.dsh-crate-choice-controls .dsh-crate-text-button{min-height:28px;font-size:12px;line-height:18px;padding:5px 10px;border-radius:14px}
[data-field=runtimePlugin]{padding:10px 0;gap:10px}
.dsh-crate-toolbar{min-height:36px;font-size:13px}
.dsh-crate-export-actions{padding-top:14px}
@media(max-width:600px){.dsh-crate-page,.dsh-crate-form{gap:14px}.dsh-crate-choice>.dsh-crate-choice-controls{margin-left:26px}.dsh-crate-file,.dsh-crate-select{font-size:16px}}

.dsh-crate-filters{display:flex;flex-direction:column;gap:8px;min-width:0}
.dsh-crate-filter-options{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.dsh-crate-filter-options select{flex:1;min-width:130px}
.dsh-crate-filters>input{width:100%}
.dsh-crate-filters [role=status]{font-size:12px;line-height:18px}
`
