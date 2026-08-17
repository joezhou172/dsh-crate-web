window.__ModuleLoader__.load({
	id: "dsh-crate-web",
	factory: (require) => {
		var module = { exports: {} };
		var exports = module.exports;
		Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
		let react = require("react");
		let _deepseek_ai_dsh_client_ui_primitives = require("@deepseek-ai/dsh-client-ui-primitives");
		let react_jsx_runtime = require("react/jsx-runtime");
		//#region src/client/DshCratePage.tsx
		const css = {
			section: "dsh-crate-section",
			heading: "dsh-crate-heading",
			intro: "dsh-crate-intro",
			muted: "dsh-crate-muted",
			tabs: "dsh-crate-tabs",
			tab: "dsh-crate-tab",
			form: "dsh-crate-form",
			label: "dsh-crate-label",
			select: "dsh-crate-select",
			file: "dsh-crate-file",
			plugin: "dsh-crate-plugin",
			button: "dsh-crate-button",
			report: "dsh-crate-report",
			finding: "dsh-crate-finding",
			history: "dsh-crate-history",
			historyItem: "dsh-crate-history-item",
			error: "dsh-crate-error",
			preview: "dsh-crate-preview",
			previewRow: "dsh-crate-preview-row",
			diagnostic: "dsh-crate-diagnostic",
			diagnosticGrid: "dsh-crate-diagnostic-grid",
			step: "dsh-crate-step",
			stepStatus: "dsh-crate-step-status",
			inventory: "dsh-crate-inventory",
			inventoryItem: "dsh-crate-inventory-item",
			success: "dsh-crate-success",
			modalBackdrop: "dsh-crate-modal-backdrop",
			modal: "dsh-crate-modal",
			modalActions: "dsh-crate-modal-actions",
			group: "dsh-crate-group",
			groupHead: "dsh-crate-group-head",
			groupToggle: "dsh-crate-group-toggle",
			groupBody: "dsh-crate-group-body",
			badge: "dsh-crate-badge",
			conflict: "dsh-crate-conflict",
			toneOk: "dsh-crate-tone-ok",
			toneBad: "dsh-crate-tone-bad",
			toneNeutral: "dsh-crate-tone-neutral"
		};
		const STYLE = `
.dsh-crate-section{display:flex;flex-direction:column;gap:12px;max-width:760px;color:var(--dsw-alias-label-primary)}
.dsh-crate-heading{margin:0;font-size:18px;font-weight:600}.dsh-crate-intro,.dsh-crate-muted{margin:0;font-size:13px;color:var(--dsw-alias-label-tertiary)}
.dsh-crate-tabs{display:flex;gap:20px;border-bottom:1px solid var(--dsw-alias-border-l2);overflow:auto}.dsh-crate-tab{border:0;padding:7px 1px 9px;background:transparent;color:var(--dsw-alias-label-tertiary);font:inherit;cursor:pointer;white-space:nowrap}
.dsh-crate-tab[data-active=true]{color:var(--dsw-alias-label-primary);border-bottom:2px solid var(--dsw-alias-label-primary)}.dsh-crate-form{display:flex;flex-direction:column;gap:10px}
.dsh-crate-label{display:flex;flex-direction:column;gap:5px;font-size:13px}.dsh-crate-select,.dsh-crate-file{max-width:100%;padding:7px 8px;border:1px solid var(--dsw-alias-border-l2,#3a3a40);border-radius:6px;background-color:var(--dsw-alias-fill-secondary,rgba(255,255,255,.08));color:var(--dsw-alias-label-primary,#f9fafb);color-scheme:dark}.dsh-crate-select option{background-color:#242428;color:#f9fafb}@media (prefers-color-scheme:light){.dsh-crate-select,.dsh-crate-file{background-color:var(--dsw-alias-fill-secondary,#fff);color:var(--dsw-alias-label-primary,#111827);color-scheme:light}.dsh-crate-select option{background-color:#fff;color:#111827}}
.dsh-crate-plugin{display:grid;grid-template-columns:minmax(0,1fr) 150px;gap:8px;align-items:center}.dsh-crate-button{align-self:flex-start;border:0;border-radius:6px;padding:8px 13px;background:var(--dsw-alias-state-business-primary);color:white;cursor:pointer}.dsh-crate-button:disabled{cursor:default;opacity:.5}
.dsh-crate-report,.dsh-crate-preview,.dsh-crate-diagnostic{display:flex;flex-direction:column;gap:8px;padding:10px;border:1px solid var(--dsw-alias-border-l2);border-radius:8px;overflow-wrap:anywhere;font-size:12px}.dsh-crate-finding,.dsh-crate-step{padding:7px;border-radius:5px;background:var(--dsw-alias-fill-tertiary)}
.dsh-crate-preview-row{display:grid;grid-template-columns:170px minmax(0,1fr);gap:8px}.dsh-crate-preview-row pre{margin:0;white-space:pre-wrap}.dsh-crate-diagnostic-grid{display:grid;grid-template-columns:150px minmax(0,1fr);gap:6px}.dsh-crate-diagnostic-grid dt{font-weight:600}.dsh-crate-diagnostic-grid dd{margin:0;white-space:pre-wrap}.dsh-crate-step{display:flex;gap:8px;align-items:flex-start}.dsh-crate-step-status{min-width:80px;font-weight:600}
.dsh-crate-history{list-style:none;display:flex;flex-direction:column;gap:8px;padding:0;margin:0}.dsh-crate-history-item{display:flex;justify-content:space-between;gap:10px;padding:8px;border-bottom:1px solid var(--dsw-alias-border-l2);font-size:12px}.dsh-crate-error{color:var(--dsw-alias-label-negative)}
.dsh-crate-inventory{display:flex;flex-direction:column;gap:6px;padding:8px;border:1px solid var(--dsw-alias-border-l2);border-radius:8px;font-size:12px}.dsh-crate-inventory-item{display:flex;justify-content:space-between;gap:8px;padding:4px 0;border-bottom:1px solid var(--dsw-alias-border-l2)}.dsh-crate-inventory-item:last-child{border-bottom:0}
.dsh-crate-success{display:flex;flex-direction:column;gap:8px;padding:10px;border:1px solid var(--dsw-alias-label-positive);border-radius:8px;background:var(--dsw-alias-fill-positive);font-size:12px}
.dsh-crate-group{display:flex;flex-direction:column;gap:6px}.dsh-crate-group-head{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:2px 0}.dsh-crate-group-toggle{border:0;background:transparent;color:var(--dsw-alias-state-business-primary,#4f8cff);font:inherit;font-size:12px;cursor:pointer;padding:2px 4px}.dsh-crate-group-body{display:flex;flex-direction:column;gap:6px}
.dsh-crate-badge{margin-left:6px;padding:1px 5px;border-radius:4px;background:var(--dsw-alias-fill-tertiary);color:var(--dsw-alias-label-tertiary);font-size:11px;border:1px solid var(--dsw-alias-border-l2)}.dsh-crate-conflict{color:var(--dsw-alias-label-negative)}
.dsh-crate-modal-backdrop{position:fixed;inset:0;z-index:1000;display:flex;align-items:center;justify-content:center;padding:24px;background:rgba(0,0,0,.58)}.dsh-crate-modal{display:flex;flex-direction:column;gap:12px;width:min(420px,calc(100vw - 48px));padding:18px;border:1px solid var(--dsw-alias-border-l2,#3a3a40);border-radius:10px;background:var(--dsw-alias-fill-primary,#1d1d20);color:var(--dsw-alias-label-primary,#f9fafb);box-shadow:0 18px 50px rgba(0,0,0,.45)}.dsh-crate-modal h3{margin:0;font-size:16px}.dsh-crate-modal p{margin:0;font-size:13px;color:var(--dsw-alias-label-tertiary,#b6b6bd)}.dsh-crate-modal-actions{display:flex;justify-content:flex-end;gap:8px}.dsh-crate-modal-actions button:last-child{background:var(--dsw-alias-state-business-primary,#4b7bec);color:#fff}
.dsh-crate-tone-ok{color:var(--dsw-alias-label-positive)}.dsh-crate-tone-bad{color:var(--dsw-alias-label-negative)}.dsh-crate-tone-neutral{color:var(--dsw-alias-label-tertiary)}
`;
		function isObject(value) {
			return value !== null && typeof value === "object" && !Array.isArray(value);
		}
		function formatTime(value) {
			if (typeof value !== "string" || !value) return "";
			const date = new Date(value);
			return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
		}
		function toneOf(status) {
			const text = String(status ?? "").toUpperCase();
			if (text.includes("FAIL") || text.includes("ERROR") || text === "BLOCKER" || text === "UNKNOWN") return css.toneBad;
			if (text.includes("PASS") || text === "READY" || text === "PREPARED" || text === "OK") return css.toneOk;
			return css.toneNeutral;
		}
		const FIELD_LABELS = {
			code: "diagCode",
			stage: "diagStage",
			item: "diagItem",
			expected: "diagExpected",
			observed: "diagObserved",
			evidence: "diagEvidence",
			impact: "diagImpact",
			originalProfileStatus: "diagOriginalProfile",
			failedProfileStatus: "diagFailedProfile",
			temporaryProfileStatus: "diagTemporaryProfile",
			canContinue: "diagCanContinue",
			suggestedNextStep: "diagSuggestedNext"
		};
		function resultOf(value) {
			return isObject(value.result) ? value.result : value;
		}
		function objects(value) {
			return Array.isArray(value) ? value.filter(isObject) : [];
		}
		function failMessage(value) {
			const error = diagnosticOf(value);
			if (error !== void 0 && typeof error.message === "string" && error.message) return error.message;
			const result = resultOf(value);
			if (typeof result.message === "string" && result.message) return result.message;
			return "";
		}
		function display(value) {
			if (typeof value === "string") return value;
			const encoded = JSON.stringify(value, null, 2);
			return encoded === void 0 ? String(value) : encoded;
		}
		function pluginLabel(plugin) {
			const resolved = isObject(plugin.resolved) ? plugin.resolved : {};
			return `${String(plugin.name ?? "unknown")}@${String(resolved.version ?? "unknown")}`;
		}
		function upsertProfileRow(list, row) {
			const name = typeof row.name === "string" ? row.name : "";
			if (!name) return list;
			const entry = {
				name,
				installedBundles: objects(row.installedBundles)
			};
			return [...list.filter((item) => item.name !== name), entry].sort((a, b) => a.name.localeCompare(b.name));
		}
		function installedBundleLabel(bundle, t) {
			return `${String(bundle.name ?? "unknown")}@${String(bundle.version ?? "unknown")} · ${bundle.active === true ? t("active") : t("installationAnchor")}${bundle.official === true ? ` · ${t("officialBadge")}` : ""}`;
		}
		function splitOfficial(items) {
			const official = [];
			const user = [];
			for (const item of items) (item.official === true ? official : user).push(item);
			return {
				official,
				user
			};
		}
		function PluginName({ name, official, t }) {
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", { children: [name, official ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
				className: css.badge,
				"data-kind": "official",
				children: t("officialBadge")
			}) : null] });
		}
		function PluginGroup({ label, count, defaultOpen = true, t, children }) {
			const [open, setOpen] = (0, react.useState)(defaultOpen);
			if (count === 0) return null;
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				className: css.group,
				"data-open": open,
				children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					className: css.groupHead,
					children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("strong", { children: [
						label,
						" · ",
						count
					] }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
						className: css.groupToggle,
						type: "button",
						"aria-expanded": open,
						onClick: () => setOpen((value) => !value),
						children: open ? t("collapse") : t("expand")
					})]
				}), open ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
					className: css.groupBody,
					children
				}) : null]
			});
		}
		function ExportPlugins({ value, t }) {
			if (value === void 0) return null;
			const plugins = objects(resultOf(value).plugins);
			if (plugins.length === 0) return null;
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				className: css.inventory,
				"data-field": "exportPlugins",
				children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: t("exportPlugins") }), plugins.map((plugin, index) => {
					const bundle = isObject(plugin.bundle) ? plugin.bundle : {};
					const artifact = isObject(plugin.artifact) ? plugin.artifact : {};
					const runtime = isObject(plugin.runtime) ? plugin.runtime : {};
					const bundleLabel = bundle.enabled === true ? `${t("bundle")} #${String(bundle.order ?? "?")}` : t("notBundle");
					return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: css.inventoryItem,
						"data-field": "exportPlugin",
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: pluginLabel(plugin) }), /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", { children: [
							bundleLabel,
							" · ",
							String(artifact.mode ?? "unknown"),
							" · ",
							String(runtime.source ?? "unknown")
						] })]
					}, `${String(plugin.name)}-${index}`);
				})]
			});
		}
		async function request(action, body = {}) {
			const value = await (await fetch("/dsh-crate/api", {
				method: "POST",
				headers: { "content-type": "application/json" },
				body: JSON.stringify({
					action,
					...body
				})
			})).json();
			if (!isObject(value)) throw new Error("DSH Crate returned a malformed response");
			return value;
		}
		async function toBase64(file) {
			const bytes = new Uint8Array(await file.arrayBuffer());
			let binary = "";
			const chunk = 32768;
			for (let index = 0; index < bytes.length; index += chunk) binary += String.fromCharCode(...bytes.subarray(index, index + chunk));
			return btoa(binary);
		}
		function diagnosticOf(value) {
			if (isObject(value.error)) return value.error;
			const result = resultOf(value);
			return isObject(result.error) ? result.error : void 0;
		}
		function Diagnostic({ value, t }) {
			const [copied, setCopied] = (0, react.useState)(false);
			const diagnostic = diagnosticOf(value);
			if (diagnostic === void 0) return null;
			const copy = async () => {
				try {
					await navigator.clipboard.writeText(JSON.stringify(diagnostic, null, 2));
					setCopied(true);
				} catch {
					setCopied(false);
				}
			};
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				className: css.diagnostic,
				role: "alert",
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: t("diagnostic") }),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("dl", {
						className: css.diagnosticGrid,
						children: [
							"code",
							"stage",
							"item",
							"expected",
							"observed",
							"evidence",
							"impact",
							"originalProfileStatus",
							"failedProfileStatus",
							"temporaryProfileStatus",
							"canContinue",
							"suggestedNextStep"
						].filter((field) => diagnostic[field] !== void 0).map((field) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("dt", { children: t(FIELD_LABELS[field] ?? field) }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("dd", { children: display(diagnostic[field]) })] }, field))
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", { children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
						className: css.button,
						type: "button",
						onClick: () => void copy(),
						children: copied ? t("diagnosticCopied") : t("copyDiagnostic")
					}) }),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("details", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("summary", { children: t("fullDiagnostic") }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("pre", { children: JSON.stringify(diagnostic, null, 2) })] })
				]
			});
		}
		function Report({ value, t }) {
			if (value === void 0) return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
				className: css.muted,
				children: t("noReport")
			});
			const result = resultOf(value);
			const findings = objects(result.findings);
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				className: css.report,
				"data-status": String(result.status ?? "UNKNOWN"),
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", { children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: t("coreStatus") }),
						" · ",
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							className: toneOf(result.status),
							children: String(result.status ?? "UNKNOWN")
						})
					] }),
					findings.length > 0 ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: t("findings") }), findings.map((finding, index) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: css.finding,
						children: [
							String(finding.severity ?? ""),
							" / ",
							String(finding.code ?? ""),
							": ",
							String(finding.message ?? "")
						]
					}, `${String(finding.code)}-${index}`))] }) : null,
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Diagnostic, {
						value,
						t
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("details", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("summary", { children: t("rawJson") }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("pre", { children: JSON.stringify(result, null, 2) })] })
				]
			});
		}
		function ImportPreview({ value, t, targetProfile, overwrite }) {
			const result = resultOf(value);
			const pack = isObject(result.pack) ? result.pack : {};
			const profile = isObject(pack.profile) ? pack.profile : {};
			const requiredPlugins = objects(result.requiredPlugins);
			const optionalPlugins = objects(result.optionalPlugins);
			const warningCount = typeof result.warningCount === "number" ? result.warningCount : 0;
			const environment = isObject(result.environment) ? result.environment : {};
			const target = targetProfile?.trim() || String(result.targetProfile ?? profile.name ?? "UNKNOWN");
			const safety = overwrite ? t("overwritePreview") : t("willNotOverwrite");
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				className: css.preview,
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: t("importPreview") }),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: css.previewRow,
						"data-field": "targetProfile",
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: t("targetProfile") }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: target })]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: css.previewRow,
						"data-field": "warningCount",
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: t("warningCount") }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: warningCount })]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: css.previewRow,
						"data-field": "requiredPlugins",
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: t("requiredPlugins") }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: requiredPlugins.map(pluginLabel).join(", ") || t("none") })]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: css.previewRow,
						"data-field": "optionalPlugins",
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: t("optionalPlugins") }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: optionalPlugins.map(pluginLabel).join(", ") || t("none") })]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: css.previewRow,
						"data-field": "environment",
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: t("environment") }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("pre", { children: display(environment) })]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: css.previewRow,
						"data-field": "coreDecision",
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: t("coreDecision") }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: display(result.canContinue) })]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: css.previewRow,
						"data-field": "safety",
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: t("safety") }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: safety })]
					})
				]
			});
		}
		function ImportSuccess({ value, t }) {
			if (value === void 0) return null;
			const result = resultOf(value);
			if (result.status !== "prepared") return null;
			const plan = isObject(result.plan) ? result.plan : {};
			const installed = objects(result.installedPlugins);
			const profileName = String(plan.profileName ?? "UNKNOWN");
			const overwritten = plan.overwrite === true;
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				className: css.success,
				"data-field": "importSuccess",
				role: "status",
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: t("importSuccess") }),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						"data-field": "preparedProfile",
						children: [
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: t("preparedProfile") }),
							" · ",
							profileName
						]
					}),
					overwritten ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						"data-field": "overwriteConfirmed",
						children: t("overwritePreview")
					}) : null,
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						"data-field": "installedPlugins",
						children: [
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: t("installedPlugins") }),
							" · ",
							installed.map((plugin) => `${String(plugin.name ?? "unknown")}@${String(plugin.version ?? "unknown")}`).join(", ") || t("none")
						]
					})
				]
			});
		}
		function VerifyReport({ value, t }) {
			if (value === void 0) return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
				className: css.muted,
				children: t("noReport")
			});
			const result = resultOf(value);
			const steps = objects(result.steps);
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				className: css.report,
				"data-status": String(result.status ?? "UNKNOWN"),
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", { children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: t("coreStatus") }),
						" · ",
						String(result.status ?? "UNKNOWN")
					] }),
					String(result.status ?? "") === "UNTESTED" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
						className: css.muted,
						children: t("verifyUntestedNote")
					}) : null,
					steps.map((step, index) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: css.step,
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							className: `${css.stepStatus} ${toneOf(step.status)}`,
							children: String(step.status ?? "UNKNOWN")
						}), /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", { children: [
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: String(step.name ?? "unknown") }),
							" — ",
							String(step.message ?? ""),
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("br", {}),
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("small", { children: display(step.evidence ?? {}) })
						] })]
					}, `${String(step.name)}-${index}`)),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Diagnostic, {
						value,
						t
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("details", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("summary", { children: t("rawJson") }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("pre", { children: JSON.stringify(result, null, 2) })] })
				]
			});
		}
		function DshCratePage({ t }) {
			const [tab, setTab] = (0, react.useState)("export");
			const [profiles, setProfiles] = (0, react.useState)([]);
			const [profile, setProfile] = (0, react.useState)("");
			const [modes, setModes] = (0, react.useState)({});
			const [file, setFile] = (0, react.useState)();
			const [report, setReport] = (0, react.useState)();
			const [history, setHistory] = (0, react.useState)([]);
			const [busy, setBusy] = (0, react.useState)(false);
			const busyRef = (0, react.useRef)(false);
			const [error, setError] = (0, react.useState)("");
			const [importMode, setImportMode] = (0, react.useState)("new");
			const [importTarget, setImportTarget] = (0, react.useState)("");
			const [deleteTarget, setDeleteTarget] = (0, react.useState)("");
			const [deleteReport, setDeleteReport] = (0, react.useState)();
			const [switchTarget, setSwitchTarget] = (0, react.useState)("");
			const [switchReport, setSwitchReport] = (0, react.useState)();
			const [runtime, setRuntime] = (0, react.useState)();
			const [runtimePlugins, setRuntimePlugins] = (0, react.useState)([]);
			const [updatedAt, setUpdatedAt] = (0, react.useState)("");
			const [toast, setToast] = (0, react.useState)();
			const toastSeq = (0, react.useRef)(0);
			const showToast = (text) => {
				toastSeq.current += 1;
				setToast({
					key: toastSeq.current,
					text
				});
			};
			const [createTarget, setCreateTarget] = (0, react.useState)("");
			const [newProfileDialogOpen, setNewProfileDialogOpen] = (0, react.useState)(false);
			const [newProfileDraft, setNewProfileDraft] = (0, react.useState)("");
			const [newProfileDialogError, setNewProfileDialogError] = (0, react.useState)("");
			const selectedProfile = (0, react.useMemo)(() => profiles.find((item) => item.name === profile), [profiles, profile]);
			const installedBundles = selectedProfile?.installedBundles ?? [];
			const exportBundles = installedBundles.filter((bundle) => bundle.active === true);
			const conflictBundles = installedBundles.filter((bundle) => bundle.conflict === true);
			const exportNames = exportBundles.map((bundle) => String(bundle.name ?? "")).filter(Boolean);
			const canImport = isObject(report?.result) && report.result.canContinue === true;
			const currentRuntimeProfile = typeof runtime?.currentProfile === "string" ? runtime.currentProfile : "";
			const loadProfiles = async () => {
				const value = await request("profiles");
				const rows = objects(value.profiles).map((item) => ({
					name: String(item.name ?? ""),
					installedBundles: objects(item.installedBundles)
				}));
				const runtimeValue = isObject(value.runtime) ? value.runtime : void 0;
				const activeName = typeof runtimeValue?.currentProfile === "string" ? runtimeValue.currentProfile : "";
				const switchable = rows.filter((item) => item.name !== activeName);
				setProfiles(rows);
				setProfile((current) => rows.some((item) => item.name === current) ? current : rows[0]?.name || "");
				setDeleteTarget((current) => rows.some((item) => item.name === current) ? current : rows[0]?.name || "");
				setSwitchTarget((current) => switchable.some((item) => item.name === current) ? current : switchable[0]?.name || "");
				if (runtimeValue) setRuntime(runtimeValue);
				setRuntimePlugins(objects(value.runtimePlugins));
				setUpdatedAt((/* @__PURE__ */ new Date()).toLocaleTimeString());
			};
			(0, react.useEffect)(() => {
				loadProfiles().catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)));
			}, []);
			(0, react.useEffect)(() => {
				busyRef.current = busy;
			}, [busy]);
			const loadProfilesRef = (0, react.useRef)(() => Promise.resolve());
			(0, react.useEffect)(() => {
				loadProfilesRef.current = loadProfiles;
			});
			(0, react.useEffect)(() => {
				let disposed = false;
				const refresh = () => {
					if (disposed || busyRef.current) return;
					loadProfilesRef.current().catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)));
				};
				const onVisibility = () => {
					if (document.visibilityState === "visible") refresh();
				};
				const timer = window.setInterval(refresh, 1e4);
				window.addEventListener("focus", refresh);
				document.addEventListener("visibilitychange", onVisibility);
				return () => {
					disposed = true;
					window.clearInterval(timer);
					window.removeEventListener("focus", refresh);
					document.removeEventListener("visibilitychange", onVisibility);
				};
			}, []);
			(0, react.useEffect)(() => {
				if (tab !== "history") return;
				request("history").then((value) => {
					setHistory(objects(value.history));
				}).catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)));
			}, [tab]);
			const run = async (action, body) => {
				setBusy(true);
				setError("");
				try {
					const value = await request(action, body);
					setReport(value);
					const result = resultOf(value);
					const profileLabel = String(body.profileName ?? "");
					if (value.status === "failed" || result.status === "failed" || result.status === "FAIL") showToast(`${t("error")}: ${failMessage(value) || t("error")}`);
					else if (action === "export" && typeof value.downloadName === "string") showToast(`${t("exportSuccess")} ${profileLabel}`.trim());
					else if (action === "inspect") showToast(t("inspectSuccess"));
					else if (action === "verify") {
						if (value.success === true) showToast(`${t("verifySuccess")} ${profileLabel}`.trim());
						else if (result.status === "FAIL") showToast(`${t("error")}: ${failMessage(value) || t("verifyFailed")}`);
						else showToast(`${t("verifyFinished")} ${profileLabel} · ${String(result.status ?? "")}`.trim());
					}
				} catch (caught) {
					const message = caught instanceof Error ? caught.message : String(caught);
					setError(message);
					showToast(`${t("error")}: ${message}`);
				} finally {
					setBusy(false);
				}
			};
			const createSelectedProfile = async () => {
				const target = createTarget.trim();
				if (!target) {
					showToast(t("profileNameRequired"));
					return;
				}
				if (profiles.some((item) => item.name === target)) {
					showToast(t("profileNameExists"));
					return;
				}
				setBusy(true);
				setError("");
				try {
					const value = await request("create-profile", { profileName: target });
					if (value.status === "failed") showToast(`${t("error")}: ${failMessage(value) || t("error")}`);
					else {
						setCreateTarget("");
						await loadProfiles();
						showToast(`${t("createSuccess")} ${target}`);
					}
				} catch (caught) {
					const message = caught instanceof Error ? caught.message : String(caught);
					setError(message);
					showToast(`${t("error")}: ${message}`);
				} finally {
					setBusy(false);
				}
			};
			const deleteSelectedProfile = async () => {
				const target = deleteTarget.trim();
				if (!target) return;
				if (!window.confirm(`${t("deleteProfileWarning")}\n\n${target}`)) return;
				setBusy(true);
				setError("");
				try {
					const value = await request("delete-profile", {
						profileName: target,
						confirmDelete: true
					});
					setDeleteReport(value);
					if (value.status === "failed") showToast(`${t("error")}: ${failMessage(value) || t("error")}`);
					else {
						await loadProfiles();
						showToast(`${t("deleteSuccess")} ${target}`);
					}
				} catch (caught) {
					const message = caught instanceof Error ? caught.message : String(caught);
					setError(message);
					showToast(`${t("error")}: ${message}`);
				} finally {
					setBusy(false);
				}
			};
			const switchSelectedProfile = async () => {
				const target = switchTarget.trim();
				if (!target) return;
				if (target === currentRuntimeProfile) {
					setSwitchReport({
						status: "ok",
						result: {
							status: "already-active",
							profileName: target,
							message: `Profile is already active: ${target}`,
							impact: "The current DSH process was not changed; the requested Profile is already running.",
							canContinue: true
						}
					});
					showToast(`${t("switchAlreadyActive")} ${target}`);
					return;
				}
				if (!window.confirm(`${t("switchProfileWarning")}\n\n${target}`)) {
					setSwitchReport({
						status: "failed",
						error: {
							code: "SWITCH_CANCELED",
							stage: "planning",
							item: target,
							message: t("switchCanceled")
						}
					});
					showToast(t("switchCanceled"));
					return;
				}
				setBusy(true);
				setError("");
				setSwitchReport(void 0);
				try {
					const scheduled = await request("switch-profile", {
						profileName: target,
						confirmSwitch: true
					});
					if (scheduled.status === "failed") {
						setSwitchReport(scheduled);
						showToast(`${t("error")}: ${failMessage(scheduled) || t("error")}`);
						return;
					}
					const operationId = typeof scheduled.operationId === "string" ? scheduled.operationId : "";
					let last = scheduled;
					if (!operationId) {
						setSwitchReport({
							status: "failed",
							error: {
								code: "SWITCH_REPORT_MISSING",
								stage: "scheduling",
								message: "Switch operation did not return an operation ID."
							}
						});
						showToast(`${t("error")}: ${t("error")}`);
						return;
					}
					for (let attempt = 0; attempt < 130; attempt += 1) {
						await new Promise((resolve) => setTimeout(resolve, 500));
						try {
							const value = await request("switch-status", { operationId });
							last = value;
							const result = resultOf(value);
							if (result.status === "ready" || result.status === "failed") break;
						} catch {}
					}
					setSwitchReport(last);
					const result = resultOf(last);
					if (result.status === "ready") {
						await loadProfiles();
						showToast(`${t("switchSuccess")} ${target}`);
					} else if (result.status === "failed") showToast(`${t("error")}: ${failMessage(last) || t("error")}`);
				} catch (caught) {
					const message = caught instanceof Error ? caught.message : String(caught);
					setError(message);
					showToast(`${t("error")}: ${message}`);
				} finally {
					setBusy(false);
				}
			};
			const importPack = async () => {
				if (!file) return;
				if (importMode === "new") {
					const packResult = resultOf(report ?? {});
					const pack = isObject(packResult.pack) ? packResult.pack : {};
					const packProfile = isObject(pack.profile) ? pack.profile : {};
					setNewProfileDraft(importTarget.trim() || String(packProfile.name ?? ""));
					setNewProfileDialogError("");
					setNewProfileDialogOpen(true);
					return;
				}
				const target = importTarget.trim() || profiles[0]?.name || "";
				if (!target) {
					setError(t("noProfiles"));
					return;
				}
				if (!window.confirm(`${t("overwriteWarning")}\n\n${target}`)) {
					showToast(t("overwriteCanceled"));
					setError("");
					return;
				}
				setBusy(true);
				setError("");
				try {
					const value = await request("import", {
						packBase64: await toBase64(file),
						targetProfile: target,
						overwrite: true,
						confirmOverwrite: true
					});
					setReport(value);
					if (value.status === "failed" || !(isObject(value.result) && value.result.status === "prepared")) showToast(`${t("error")}: ${failMessage(value) || t("error")}`);
					else {
						await loadProfiles();
						setProfiles((current) => isObject(value.profile) ? upsertProfileRow(current, value.profile) : current);
						showToast(`${t("importOverwritten")} ${target}`);
					}
				} catch (caught) {
					const message = caught instanceof Error ? caught.message : String(caught);
					setError(message);
					showToast(`${t("error")}: ${message}`);
				} finally {
					setBusy(false);
				}
			};
			const confirmNewProfileImport = async () => {
				if (!file) return;
				const target = newProfileDraft.trim();
				if (!target) {
					setNewProfileDialogError(t("profileNameRequired"));
					return;
				}
				if (profiles.some((item) => item.name === target)) {
					setNewProfileDialogError(t("profileNameExists"));
					return;
				}
				setImportTarget(target);
				setNewProfileDialogOpen(false);
				setNewProfileDialogError("");
				setBusy(true);
				setError("");
				try {
					const value = await request("import", {
						packBase64: await toBase64(file),
						targetProfile: target,
						overwrite: false,
						confirmOverwrite: false
					});
					setReport(value);
					if (value.status === "failed" || !(isObject(value.result) && value.result.status === "prepared")) showToast(`${t("error")}: ${failMessage(value) || t("error")}`);
					else {
						await loadProfiles();
						setProfiles((current) => isObject(value.profile) ? upsertProfileRow(current, value.profile) : current);
						setProfile(target);
						showToast(`${t("importSuccess")} ${target}`);
					}
				} catch (caught) {
					const message = caught instanceof Error ? caught.message : String(caught);
					setError(message);
					showToast(`${t("error")}: ${message}`);
				} finally {
					setBusy(false);
				}
			};
			const inspectFile = async (nextFile) => {
				setFile(nextFile);
				setReport(void 0);
				setError("");
				if (nextFile === void 0) return;
				await run("inspect", { packBase64: await toBase64(nextFile) });
			};
			const input = /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
				className: css.label,
				children: [t("choosePack"), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("input", {
					className: css.file,
					type: "file",
					accept: ".dshcrate,application/zip",
					onChange: (event) => {
						inspectFile(event.target.files?.[0]);
					}
				})]
			});
			const profileSelect = /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
				className: css.label,
				children: [t("profile"), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("select", {
					className: css.select,
					value: profile,
					onChange: (event) => setProfile(event.target.value),
					children: profiles.map((item) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
						value: item.name,
						children: item.name
					}, item.name))
				})]
			});
			const profileManager = /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				className: css.inventory,
				"data-field": "profileManagement",
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: t("profileManagement") }),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
						className: css.muted,
						children: [
							t("currentRunningProfile"),
							": ",
							currentRuntimeProfile || t("none")
						]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
						className: css.label,
						children: [t("createProfile"), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("input", {
							className: css.file,
							value: createTarget,
							placeholder: t("createProfilePlaceholder"),
							onChange: (event) => setCreateTarget(event.target.value)
						})]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
						className: css.muted,
						children: t("createProfileHint")
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
						className: css.button,
						type: "button",
						disabled: busy || !createTarget.trim(),
						onClick: () => void createSelectedProfile(),
						children: busy ? t("createPending") : t("createProfile")
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
						className: css.label,
						children: [t("switchProfile"), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("select", {
							className: css.select,
							value: switchTarget && switchTarget !== currentRuntimeProfile ? switchTarget : profiles.find((item) => item.name !== currentRuntimeProfile)?.name || "",
							onChange: (event) => setSwitchTarget(event.target.value),
							children: profiles.filter((item) => item.name !== currentRuntimeProfile).map((item) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
								value: item.name,
								children: item.name
							}, item.name))
						})]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
						className: css.button,
						type: "button",
						disabled: busy || !switchTarget,
						onClick: () => void switchSelectedProfile(),
						children: busy ? t("switchPending") : t("switchProfile")
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
						className: css.label,
						children: [t("deleteProfile"), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("select", {
							className: css.select,
							value: deleteTarget || profiles[0]?.name || "",
							onChange: (event) => setDeleteTarget(event.target.value),
							children: profiles.map((item) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
								value: item.name,
								children: item.name
							}, item.name))
						})]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
						className: css.muted,
						children: t("deleteProfileWarning")
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
						className: css.button,
						type: "button",
						disabled: busy || !deleteTarget,
						onClick: () => void deleteSelectedProfile(),
						children: t("confirmDelete")
					}),
					switchReport ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Report, {
						value: switchReport,
						t
					}) : null,
					deleteReport ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Report, {
						value: deleteReport,
						t
					}) : null
				]
			});
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				className: css.section,
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("style", { children: STYLE }),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h2", {
						className: css.heading,
						children: t("title")
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
						className: css.intro,
						children: t("intro")
					}),
					profiles.length > 0 ? profileManager : null,
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						className: css.tabs,
						role: "tablist",
						children: [
							"export",
							"import",
							"inspect",
							"verify",
							"history"
						].map((item) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							className: css.tab,
							"data-active": tab === item,
							type: "button",
							role: "tab",
							onClick: () => setTab(item),
							children: t(item)
						}, item))
					}),
					error ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("p", {
						className: css.error,
						role: "alert",
						children: [
							t("error"),
							": ",
							error
						]
					}) : null,
					tab === "export" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						className: css.form,
						children: profiles.length === 0 ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
							className: css.muted,
							children: t("noProfiles")
						}) : /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [
							profileSelect,
							/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
								className: css.inventory,
								"data-field": "runtimePlugins",
								children: [
									/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("strong", { children: [t("runtimePlugins"), runtimePlugins.length > 0 ? ` · ${runtimePlugins.length}` : ""] }),
									/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
										className: css.muted,
										children: [
											t("updatedAt"),
											": ",
											updatedAt || t("none")
										]
									}),
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
										className: css.button,
										type: "button",
										disabled: busy,
										onClick: () => {
											loadProfiles().catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)));
										},
										children: t("refresh")
									}),
									currentRuntimeProfile && selectedProfile?.name !== currentRuntimeProfile ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
										className: css.muted,
										children: t("runtimePluginsInactive")
									}) : runtimePlugins.length === 0 ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
										className: css.muted,
										children: t("none")
									}) : (() => {
										const groups = splitOfficial(runtimePlugins);
										const row = (plugin) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
											className: css.inventoryItem,
											"data-field": "runtimePlugin",
											children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(PluginName, {
												name: String(plugin.name ?? "unknown"),
												official: plugin.official === true,
												t
											}), /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", { children: [
												plugin.enabled === true ? t("runtimeEnabled") : t("runtimeDisabled"),
												" · ",
												String(plugin.phase ?? "—")
											] })]
										}, `${String(plugin.id ?? plugin.name)}`);
										return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(PluginGroup, {
											label: t("userPlugins"),
											count: groups.user.length,
											defaultOpen: true,
											t,
											children: groups.user.map(row)
										}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(PluginGroup, {
											label: t("officialPlugins"),
											count: groups.official.length,
											defaultOpen: false,
											t,
											children: groups.official.map(row)
										})] });
									})()
								]
							}),
							/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
								className: css.inventory,
								children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: t("declaredBundles") }), exportBundles.length === 0 ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
									className: css.muted,
									children: t("none")
								}) : (() => {
									const groups = splitOfficial(exportBundles);
									const row = (bundle) => {
										const name = String(bundle.name ?? "");
										const conflict = bundle.conflict === true;
										return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
											className: css.inventoryItem,
											children: [
												/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", { children: [installedBundleLabel(bundle, t), conflict ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
													className: css.conflict,
													children: [" · ", t("conflictWarning")]
												}) : null] }),
												/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: String(bundle.patch ?? "") }),
												/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("select", {
													"aria-label": `${name} ${t("artifactMode")}`,
													className: css.select,
													disabled: conflict,
													value: modes[name] ?? "embedded",
													onChange: (event) => setModes((current) => ({
														...current,
														[name]: event.target.value
													})),
													children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
														value: "embedded",
														children: t("embedded")
													}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
														value: "reference-only",
														children: t("referenceOnly")
													})]
												})
											]
										}, `${name}-${String(bundle.version)}`);
									};
									return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(PluginGroup, {
										label: t("userPlugins"),
										count: groups.user.length,
										defaultOpen: true,
										t,
										children: groups.user.map(row)
									}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(PluginGroup, {
										label: t("officialPlugins"),
										count: groups.official.length,
										defaultOpen: false,
										t,
										children: groups.official.map(row)
									})] });
								})()]
							}),
							conflictBundles.length > 0 ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
								className: css.inventory,
								"data-field": "conflictBundles",
								children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: t("conflictBundles") }), conflictBundles.map((bundle) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
									className: css.inventoryItem,
									children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: installedBundleLabel(bundle, t) }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
										className: css.conflict,
										children: t("conflictWarning")
									})]
								}, `conflict-${String(bundle.name)}`))]
							}) : null,
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
								className: css.button,
								type: "button",
								disabled: busy || !profile,
								onClick: () => void run("export", {
									profileName: profile,
									includeInstalledBundles: true,
									embed: exportNames.filter((name) => (modes[name] ?? "embedded") === "embedded"),
									referenceOnly: exportNames.filter((name) => (modes[name] ?? "embedded") === "reference-only")
								}),
								children: busy ? t("exporting") : t("exportButton")
							}),
							isObject(report) && typeof report.downloadName === "string" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("a", {
								href: `/dsh-crate/download?name=${encodeURIComponent(report.downloadName)}`,
								children: t("download")
							}) : null,
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)(ExportPlugins, {
								value: report,
								t
							}),
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Report, {
								value: report,
								t
							})
						] })
					}) : null,
					tab === "import" ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: css.form,
						children: [
							input,
							/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
								className: css.label,
								children: [t("importMode"), /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("select", {
									className: css.select,
									value: importMode,
									onChange: (event) => setImportMode(event.target.value),
									children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
										value: "new",
										children: t("newProfile")
									}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
										value: "overwrite",
										children: t("overwriteProfile")
									})]
								})]
							}),
							importMode === "new" ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
								className: css.label,
								children: [t("newProfileName"), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("input", {
									className: css.file,
									value: importTarget,
									placeholder: t("newProfileName"),
									onChange: (event) => setImportTarget(event.target.value)
								})]
							}) : /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
								className: css.label,
								children: [t("targetProfile"), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("select", {
									className: css.select,
									value: importTarget || profiles[0]?.name || "",
									onChange: (event) => setImportTarget(event.target.value),
									children: profiles.map((item) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
										value: item.name,
										children: item.name
									}, item.name))
								})]
							}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
								className: css.error,
								children: t("overwriteWarning")
							})] }),
							report ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(ImportPreview, {
								value: report,
								t,
								targetProfile: (importMode === "overwrite" ? importTarget || profiles[0]?.name : importTarget) || void 0,
								overwrite: importMode === "overwrite"
							}) : null,
							report ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(ImportSuccess, {
								value: report,
								t
							}) : null,
							report ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Report, {
								value: report,
								t
							}) : null,
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
								className: css.button,
								type: "button",
								disabled: busy || !file || !canImport || importMode === "overwrite" && !importTarget && profiles.length === 0,
								onClick: () => void importPack(),
								children: busy ? t("working") : t("importButton")
							})
						]
					}) : null,
					tab === "inspect" ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: css.form,
						children: [
							input,
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Report, {
								value: report,
								t
							}),
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
								className: css.button,
								type: "button",
								disabled: busy || !file,
								onClick: async () => {
									if (file) await run("inspect", { packBase64: await toBase64(file) });
								},
								children: busy ? t("working") : t("inspectButton")
							})
						]
					}) : null,
					tab === "verify" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						className: css.form,
						children: profiles.length === 0 ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
							className: css.muted,
							children: t("noProfiles")
						}) : /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [
							profileSelect,
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
								className: css.button,
								type: "button",
								disabled: busy || !profile,
								onClick: () => void run("verify", {
									profileName: profile,
									mode: "web"
								}),
								children: busy ? t("working") : t("verifyButton")
							}),
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)(VerifyReport, {
								value: report,
								t
							})
						] })
					}) : null,
					tab === "history" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("ul", {
						className: css.history,
						children: history.length === 0 ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("li", {
							className: css.muted,
							children: t("noHistory")
						}) : history.map((item, index) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("li", {
							className: css.historyItem,
							children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", { children: [
								formatTime(item.time),
								" · ",
								item.action,
								" · ",
								item.profile ?? item.pack ?? ""
							] }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", {
								className: toneOf(item.status),
								children: item.status
							})]
						}, `${item.time}-${index}`))
					}) : null,
					newProfileDialogOpen ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						className: css.modalBackdrop,
						role: "presentation",
						children: /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
							className: css.modal,
							role: "dialog",
							"aria-modal": "true",
							"aria-labelledby": "dsh-crate-new-profile-title",
							children: [
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h3", {
									id: "dsh-crate-new-profile-title",
									children: t("newProfileName")
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: t("confirmImport") }),
								/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
									className: css.label,
									children: [t("newProfileName"), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("input", {
										autoFocus: true,
										className: css.file,
										value: newProfileDraft,
										onChange: (event) => {
											setNewProfileDraft(event.target.value);
											setNewProfileDialogError("");
										}
									})]
								}),
								newProfileDialogError ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
									className: css.error,
									role: "alert",
									children: newProfileDialogError
								}) : null,
								/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
									className: css.modalActions,
									children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
										className: css.button,
										type: "button",
										onClick: () => setNewProfileDialogOpen(false),
										children: t("cancel")
									}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
										className: css.button,
										type: "button",
										onClick: () => void confirmNewProfileImport(),
										children: t("confirmImportAction")
									})]
								})
							]
						})
					}) : null,
					toast ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Toast, {
						text: toast.text,
						onDone: () => setToast(void 0)
					}, toast.key) : null
				]
			});
		}
		//#endregion
		//#region src/client/PluginListTab.tsx
		/**
		* Plugins settings tab replacing the official read-only inventory list.
		* Official DSH built-ins are collapsed into their own group while plugins
		* installed or authored by the user stay expanded, so the two kinds are
		* visually separated instead of mixed into one flat list.
		*/
		function PluginListTab({ t }) {
			const [plugins, setPlugins] = (0, react.useState)([]);
			const [status, setStatus] = (0, react.useState)("loading");
			const [tick, setTick] = (0, react.useState)(0);
			(0, react.useEffect)(() => {
				let current = true;
				setStatus("loading");
				request("profiles").then((value) => {
					if (!current) return;
					setPlugins(objects(value.runtimePlugins));
					setStatus("ready");
				}).catch(() => {
					if (current) setStatus("error");
				});
				return () => {
					current = false;
				};
			}, [tick]);
			const retry = () => setTick((value) => value + 1);
			const row = (plugin) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				className: css.inventoryItem,
				"data-field": "runtimePlugin",
				children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(PluginName, {
					name: String(plugin.name ?? "unknown"),
					official: plugin.official === true,
					t
				}), /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", { children: [
					plugin.enabled === true ? t("runtimeEnabled") : t("runtimeDisabled"),
					" · ",
					String(plugin.phase ?? "—")
				] })]
			}, `${String(plugin.id ?? plugin.name)}`);
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				className: css.section,
				"data-field": "pluginListTab",
				children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("style", { children: STYLE }), /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					className: css.inventory,
					"data-field": "runtimePlugins",
					children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("strong", { children: [t("runtimePlugins"), plugins.length > 0 ? ` · ${plugins.length}` : ""] }),
						/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
							className: css.muted,
							children: [
								t("updatedAt"),
								": ",
								status === "ready" ? (/* @__PURE__ */ new Date()).toLocaleTimeString() : t("none")
							]
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							className: css.button,
							type: "button",
							disabled: status === "loading",
							onClick: retry,
							children: t("refresh")
						}),
						status === "loading" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
							className: css.muted,
							children: t("pluginListLoading")
						}) : null,
						status === "error" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
							className: css.error,
							role: "alert",
							children: t("pluginListError")
						}) : null,
						status === "ready" ? (() => {
							const groups = splitOfficial(plugins);
							return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(PluginGroup, {
								label: t("userPlugins"),
								count: groups.user.length,
								defaultOpen: true,
								t,
								children: groups.user.map(row)
							}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(PluginGroup, {
								label: t("officialPlugins"),
								count: groups.official.length,
								defaultOpen: false,
								t,
								children: groups.official.map(row)
							})] });
						})() : null
					]
				})]
			});
		}
		//#endregion
		//#region src/client/locales.ts
		const en = {
			nav: "DSH Crate",
			title: "DSH Crate",
			intro: "Export, inspect, and import a tested DSH environment Crate.",
			export: "Export",
			import: "Import",
			inspect: "Inspect",
			history: "History",
			profile: "Profile",
			noProfiles: "No selectable Profiles were found in this DSH_HOME.",
			artifactMode: "Artifact mode",
			embedded: "Embedded",
			referenceOnly: "Reference-only",
			exportButton: "Export Crate",
			exporting: "Exporting…",
			choosePack: "Choose a .dshcrate file",
			inspectButton: "Run Preflight",
			importButton: "Import Crate",
			confirmImportAction: "Confirm Import",
			confirmImport: "Imports as a new Profile after a Preflight check. Continue?",
			working: "Working…",
			noReport: "No report yet.",
			noHistory: "No DSH Crate operations have been recorded.",
			download: "Download Crate",
			plugins: "Plugins",
			findings: "Findings",
			coreStatus: "Core status",
			rawJson: "Raw JSON",
			diagnostic: "Failure diagnostic",
			copyDiagnostic: "Copy full diagnostic",
			diagnosticCopied: "Copied",
			fullDiagnostic: "View full diagnostic",
			importPreview: "Import preview",
			targetProfile: "Target Profile",
			warningCount: "Warnings",
			requiredPlugins: "Required packages",
			optionalPlugins: "Optional packages",
			environment: "Environment required/current",
			coreDecision: "Core canContinue",
			safety: "Import safety",
			willNotOverwrite: "Creates a new Profile only; it will not overwrite the original Profile.",
			none: "None",
			verify: "Verify",
			verifyButton: "Run Verify",
			error: "Operation failed",
			installedBundles: "Installed Bundles",
			active: "Active in this Profile",
			installationAnchor: "Installation anchor only",
			anchorOnlyNote: "Installed but not composed in this Profile (installation anchor only; not exported): ",
			exportPlugins: "Exported plugins",
			bundle: "Bundle",
			notBundle: "Not a Bundle",
			importSuccess: "Import successful",
			preparedProfile: "Prepared Profile",
			installedPlugins: "Installed plugins",
			importMode: "Import mode",
			newProfile: "Add new Profile",
			overwriteProfile: "Overwrite existing Profile",
			newProfileName: "New Profile name",
			overwriteWarning: "This replaces all files in the selected Profile.",
			overwritePreview: "Existing Profile will be replaced after confirmation.",
			confirmOverwrite: "Confirm overwrite",
			overwriteCanceled: "Overwrite canceled.",
			deleteProfile: "Delete Profile",
			deleteProfileWarning: "This permanently deletes the selected Profile.",
			confirmDelete: "Confirm deletion",
			deleteSuccess: "Profile deleted.",
			profileNameRequired: "Profile name is required.",
			profileNameExists: "That Profile name already exists.",
			cancel: "Cancel",
			createProfile: "New Profile",
			createProfilePlaceholder: "new profile name",
			createProfileHint: "A new Profile includes the official DSH bundles and the DSH Crate plugin by default.",
			createPending: "Creating…",
			createSuccess: "Profile created.",
			profileManagement: "Profile management",
			currentRunningProfile: "Currently running",
			switchProfile: "Switch and restart Profile",
			switchProfileWarning: "DSH will stop and restart using the selected Profile.",
			switchCanceled: "Profile switch canceled.",
			switchSuccess: "Profile switched and DSH restarted.",
			switchAlreadyActive: "Profile is already running.",
			declaredBundles: "Declared Bundles (Profile)",
			runtimePlugins: "Runtime plugins (currently running Profile)",
			runtimeEnabled: "enabled",
			runtimeDisabled: "disabled",
			runtimePluginsInactive: "Select the currently running Profile to see its live runtime plugin list.",
			updatedAt: "Last refreshed",
			refresh: "Refresh",
			pluginListTab: "Plugin list",
			pluginListLoading: "Reading plugins…",
			pluginListError: "Plugins are temporarily unavailable.",
			retry: "Retry",
			officialPlugins: "Official built-in plugins",
			userPlugins: "User-installed & written plugins",
			officialBadge: "Official",
			conflictWarning: "Conflicts with an official built-in; excluded from export",
			conflictBundles: "Conflicted Bundles (not exported)",
			collapse: "Collapse",
			expand: "Expand",
			exportSuccess: "Crate exported successfully.",
			inspectSuccess: "Preflight finished.",
			verifySuccess: "Verification passed.",
			verifyFailed: "Verification failed.",
			verifyFinished: "Verification finished.",
			verifyUntestedNote: "UNTESTED means composition was checked only; runtime, model, session, and plugin behavior were NOT actually verified.",
			importOverwritten: "Profile overwritten.",
			switchPending: "Switching Profile and waiting for DSH ready…",
			diagCode: "Code",
			diagStage: "Stage",
			diagItem: "Item",
			diagExpected: "Expected",
			diagObserved: "Observed",
			diagEvidence: "Evidence",
			diagImpact: "Impact",
			diagOriginalProfile: "Original Profile",
			diagFailedProfile: "Failed Profile",
			diagTemporaryProfile: "Temporary Profile",
			diagCanContinue: "Can continue",
			diagSuggestedNext: "Suggested next step"
		};
		const zh = {
			nav: "DSH Crate",
			title: "DSH Crate",
			intro: "导出、检查和导入经过测试的 DSH 环境 Crate。",
			export: "导出",
			import: "导入",
			inspect: "检查",
			history: "历史",
			profile: "Profile",
			noProfiles: "当前 DSH_HOME 没有可选择的 Profile。",
			artifactMode: "Artifact 模式",
			embedded: "内嵌",
			referenceOnly: "仅引用",
			exportButton: "导出 Crate",
			exporting: "导出中…",
			choosePack: "选择 .dshcrate 文件",
			inspectButton: "运行 Preflight",
			importButton: "导入 Crate",
			confirmImportAction: "确认导入",
			confirmImport: "将作为新 Profile 导入，导入前会先执行 Preflight 检查。是否继续？",
			working: "处理中…",
			noReport: "暂无报告。",
			noHistory: "还没有 DSH Crate 操作记录。",
			download: "下载 Crate",
			plugins: "插件",
			findings: "诊断项",
			coreStatus: "Core 状态",
			rawJson: "原始 JSON",
			diagnostic: "失败诊断",
			copyDiagnostic: "复制完整诊断",
			diagnosticCopied: "已复制",
			fullDiagnostic: "查看完整诊断",
			importPreview: "导入预览",
			targetProfile: "目标 Profile",
			warningCount: "WARNING 数量",
			requiredPlugins: "required 包",
			optionalPlugins: "optional 包",
			environment: "环境要求/当前值",
			coreDecision: "Core canContinue",
			safety: "导入安全",
			willNotOverwrite: "只创建新 Profile；不会覆盖原 Profile。",
			none: "无",
			verify: "验证",
			verifyButton: "运行 Verify",
			error: "操作失败",
			installedBundles: "已安装 Bundle",
			active: "当前 Profile 已组合",
			installationAnchor: "仅安装锚点",
			anchorOnlyNote: "已安装但未组合进当前 Profile（仅安装锚点，不导出）：",
			exportPlugins: "导出插件",
			bundle: "Bundle",
			notBundle: "普通依赖",
			importSuccess: "导入成功",
			preparedProfile: "已准备 Profile",
			installedPlugins: "已安装插件",
			importMode: "导入模式",
			newProfile: "添加新 Profile",
			overwriteProfile: "覆盖已有 Profile",
			newProfileName: "新 Profile 名称",
			overwriteWarning: "这会替换所选 Profile 中的全部文件。",
			overwritePreview: "确认后将替换已有 Profile。",
			confirmOverwrite: "确认覆盖",
			overwriteCanceled: "已取消覆盖。",
			deleteProfile: "删除 Profile",
			deleteProfileWarning: "这会永久删除所选 Profile。",
			confirmDelete: "确认删除",
			deleteSuccess: "Profile 已删除。",
			profileNameRequired: "必须填写 Profile 名称。",
			profileNameExists: "该 Profile 名称已存在。",
			cancel: "取消",
			createProfile: "新建 Profile",
			createProfilePlaceholder: "新 Profile 名称",
			createProfileHint: "新 Profile 默认包含官方插件与本插件（DSH Crate）。",
			createPending: "创建中…",
			createSuccess: "Profile 已创建。",
			profileManagement: "Profile 管理",
			currentRunningProfile: "当前运行 Profile",
			switchProfile: "切换并重启 Profile",
			switchProfileWarning: "DSH 将停止当前进程，并使用所选 Profile 重新启动。",
			switchCanceled: "已取消 Profile 切换。",
			switchSuccess: "Profile 已切换并完成 DSH 重启。",
			switchAlreadyActive: "该 Profile 已在运行。",
			declaredBundles: "声明 Bundle（Profile）",
			runtimePlugins: "运行时插件（当前运行 Profile）",
			runtimeEnabled: "已启用",
			runtimeDisabled: "已禁用",
			runtimePluginsInactive: "选择当前运行的 Profile 以查看其实时运行的插件列表。",
			updatedAt: "最近刷新",
			refresh: "刷新",
			pluginListTab: "插件列表",
			pluginListLoading: "正在读取插件…",
			pluginListError: "暂时无法读取插件。",
			retry: "重试",
			officialPlugins: "官方内置插件",
			userPlugins: "用户安装与编写的插件",
			officialBadge: "官方",
			conflictWarning: "与官方内置插件冲突，已排除导出",
			conflictBundles: "冲突 Bundle（未导出）",
			collapse: "折叠",
			expand: "展开",
			exportSuccess: "Crate 导出成功。",
			inspectSuccess: "Preflight 检查完成。",
			verifySuccess: "验证通过。",
			verifyFailed: "验证未通过。",
			verifyFinished: "验证完成。",
			verifyUntestedNote: "UNTESTED 表示仅验证了组合（composition），运行时、模型、会话、插件业务行为均未实际验证。",
			importOverwritten: "Profile 已覆盖。",
			switchPending: "正在切换 Profile，等待 DSH ready…",
			diagCode: "诊断代码",
			diagStage: "失败阶段",
			diagItem: "对象",
			diagExpected: "预期",
			diagObserved: "实际",
			diagEvidence: "证据",
			diagImpact: "影响",
			diagOriginalProfile: "原 Profile 状态",
			diagFailedProfile: "失败 Profile 状态",
			diagTemporaryProfile: "临时 Profile 状态",
			diagCanContinue: "是否可继续",
			diagSuggestedNext: "建议下一步"
		};
		//#endregion
		//#region src/client/index.tsx
		const NS = "dsh.crate";
		const inject = ["slots", "locale"];
		function apply(ctx) {
			ctx.effect(() => ctx.locale.register(NS, {
				en,
				zh
			}), "dsh-crate-web: dictionaries");
			const t = ctx.locale.bind(NS);
			ctx.slots.inject("settings.section", () => ctx.slots.register({
				name: "settings.section",
				id: "dsh-crate",
				order: 30,
				label: () => t("nav"),
				locale: NS
			}, DshCratePage));
			ctx.slots.inject("settings.plugins.tab", () => ctx.slots.register({
				name: "settings.plugins.tab",
				id: "crate",
				order: 10,
				label: () => t("pluginListTab"),
				locale: NS
			}, PluginListTab));
		}
		//#endregion
		exports.apply = apply;
		exports.inject = inject;
		return module.exports;
	}
});
