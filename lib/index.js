import { randomUUID } from "node:crypto";
import { createReadStream, readFileSync } from "node:fs";
import { access, cp, mkdir, readFile, readdir, rename, stat, unlink, writeFile } from "node:fs/promises";
import { platform } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
//#region src/history.ts
const historyLocks = /* @__PURE__ */ new Map();
async function withHistoryLock(path, operation) {
	const previous = historyLocks.get(path) ?? Promise.resolve();
	let release;
	const current = new Promise((resolve) => {
		release = resolve;
	});
	historyLocks.set(path, current);
	await previous;
	try {
		return await operation();
	} finally {
		release();
		if (historyLocks.get(path) === current) historyLocks.delete(path);
	}
}
async function readHistoryUnlocked(path) {
	try {
		const value = JSON.parse(await readFile(path, "utf8"));
		return Array.isArray(value) ? value.filter((item) => item !== null && typeof item === "object" && !Array.isArray(item)) : [];
	} catch (error) {
		if (error.code === "ENOENT") return [];
		throw error;
	}
}
async function writeHistoryAtomically(path, entries) {
	const temporary = `${path}.${randomUUID()}.tmp`;
	await writeFile(temporary, `${JSON.stringify(entries, null, 2)}\n`, {
		encoding: "utf8",
		flag: "wx"
	});
	try {
		await rename(temporary, path);
	} catch (error) {
		await unlink(temporary).catch(() => void 0);
		throw error;
	}
}
async function readHistory(path) {
	return withHistoryLock(path, () => readHistoryUnlocked(path));
}
async function record(path, item) {
	return withHistoryLock(path, async () => {
		await writeHistoryAtomically(path, [...await readHistoryUnlocked(path), item].slice(-100));
		return item;
	});
}
//#endregion
//#region src/index.ts
/** Host half: a small local HTTP bridge to the installed dsh-crate Core CLI. */
const API_PATH = "/dsh-crate/api";
const DOWNLOAD_PATH = "/dsh-crate/download";
const MAX_BODY_BYTES = 67108864;
const SAFE_NAME = /^[A-Za-z0-9._-]+$/;
const SAFE_PLUGIN_NAME = /^@?[A-Za-z0-9._-]+(?:\/[A-Za-z0-9._-]+)?$/;
const SAFE_OPERATION_ID = /^[0-9a-f-]{36}$/i;
const CRATE_PACKAGE_NAME = "dsh-crate-web";
const DIAGNOSTIC_PRODUCER = "dsh-crate";
const DIAGNOSTIC_SCHEMA_VERSION = 1;
function crateVersion() {
	try {
		const packageRoot = dirname(dirname(fileURLToPath(import.meta.url)));
		const manifest = JSON.parse(readFileSync(join(packageRoot, "package.json"), "utf8"));
		if (typeof manifest.version === "string" && manifest.version !== "") return manifest.version;
	} catch {}
	return "";
}
const CRATE_VERSION = crateVersion();
function diagnosticEnvelope(operation, status) {
	return {
		producer: DIAGNOSTIC_PRODUCER,
		crateVersion: CRATE_VERSION,
		diagnosticSchemaVersion: DIAGNOSTIC_SCHEMA_VERSION,
		operation,
		status
	};
}
/** Cordis FiberState enum values; mirrors dsh-host-plugin-inventory phases. */
const RUNTIME_FIBER_PHASE = {
	0: "pending",
	1: "loading",
	2: "active",
	3: "failed",
	4: null,
	5: "unloading"
};
/** Read-only projection of the currently running Loader's non-group entries. */
function listRuntimePlugins(ctx) {
	const loader = ctx.loader;
	if (!loader || typeof loader.entries !== "function") return [];
	const rows = [];
	try {
		for (const entry of loader.entries()) {
			if (entry.options.group) continue;
			if (entry.options.name.startsWith("cordis:")) continue;
			rows.push({
				id: entry.id,
				name: entry.options.name,
				enabled: entry.disabled !== true,
				phase: entry.fiber ? RUNTIME_FIBER_PHASE[entry.fiber.state] ?? null : null
			});
		}
	} catch {}
	return rows;
}
function json(res, status, body) {
	const payload = JSON.stringify(body);
	res.writeHead(status, {
		"content-type": "application/json; charset=utf-8",
		"cache-control": "no-store"
	});
	res.end(payload);
}
function failMessage(error) {
	return error instanceof Error ? error.message : String(error);
}
function safeName(value, label) {
	if (typeof value !== "string" || !SAFE_NAME.test(value)) throw new Error(`${label} must be a simple file or Profile name`);
	return value;
}
function safePluginName(value, label) {
	if (typeof value !== "string" || !SAFE_PLUGIN_NAME.test(value)) throw new Error(`${label} must be a valid package name`);
	return value;
}
async function readRequest(req) {
	const chunks = [];
	let length = 0;
	for await (const chunk of req) {
		const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
		length += bytes.length;
		if (length > MAX_BODY_BYTES) throw new Error("request body is too large");
		chunks.push(bytes);
	}
	if (length === 0) return {};
	const value = JSON.parse(Buffer.concat(chunks).toString("utf8"));
	if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error("request body must be a JSON object");
	return value;
}
function decodePack(value) {
	if (typeof value !== "string" || value.length === 0) throw new Error("packBase64 is required");
	const pack = Buffer.from(value, "base64");
	if (pack.length === 0) throw new Error("packBase64 is empty");
	return pack;
}
async function ensureWorkspace(home) {
	const root = join(home, ".dsh-pack");
	const exports = join(root, "exports");
	const work = join(root, "ui-work");
	const history = join(root, "ui-history.json");
	await mkdir(exports, { recursive: true });
	await mkdir(work, { recursive: true });
	return {
		root,
		exports,
		work,
		history
	};
}
async function bundledCorePath() {
	const packageRoot = dirname(dirname(fileURLToPath(import.meta.url)));
	const core = join(packageRoot, "core");
	try {
		await access(join(core, "dsh_pack", "__main__.py"));
		return core;
	} catch {
		return;
	}
}
async function bundledRuntimeCommand() {
	const packageRoot = dirname(dirname(fileURLToPath(import.meta.url)));
	const command = join(packageRoot, "runtime", "python", "python.exe");
	try {
		await access(command);
		return {
			command,
			prefix: [
				"-B",
				"-m",
				"dsh_pack"
			]
		};
	} catch {
		return;
	}
}
function configuredCoreCommand() {
	if (!process.env.DSH_PACK_CLI) return void 0;
	let prefix = [];
	if (process.env.DSH_PACK_CLI_PREFIX) {
		const parsed = JSON.parse(process.env.DSH_PACK_CLI_PREFIX);
		if (!Array.isArray(parsed) || parsed.some((item) => typeof item !== "string")) throw new Error("DSH_PACK_CLI_PREFIX must be a JSON string array");
		prefix = parsed;
	}
	return {
		command: process.env.DSH_PACK_CLI,
		prefix
	};
}
function isCommandNotFound(error) {
	return isObject(error) && error.code === "ENOENT";
}
async function spawnCore(home, command, args) {
	return await new Promise((resolveRun, reject) => {
		const child = spawn(command.command, [...command.prefix, ...args], {
			cwd: home,
			env: {
				...process.env,
				...command.env,
				DSH_HOME: home,
				DSH_PACK_CORE_MODE: "1",
				PYTHONDONTWRITEBYTECODE: "1"
			},
			shell: false,
			windowsHide: true
		});
		const stdout = [];
		const stderr = [];
		child.stdout.on("data", (chunk) => stdout.push(Buffer.from(chunk)));
		child.stderr.on("data", (chunk) => stderr.push(Buffer.from(chunk)));
		child.once("error", reject);
		child.once("close", (code) => resolveRun({
			code: code ?? 1,
			stdout: Buffer.concat(stdout).toString("utf8"),
			stderr: Buffer.concat(stderr).toString("utf8")
		}));
	});
}
async function runCore(home, args) {
	const configured = configuredCoreCommand();
	if (configured) return spawnCore(home, configured, args);
	const candidates = [];
	const bundledRuntime = await bundledRuntimeCommand();
	if (bundledRuntime) candidates.push(bundledRuntime);
	candidates.push({
		command: "dsh-crate",
		prefix: []
	});
	const bundled = await bundledCorePath();
	if (bundled) {
		const pythonPath = [bundled, process.env.PYTHONPATH].filter(Boolean).join(process.platform === "win32" ? ";" : ":");
		candidates.push({
			command: "python",
			prefix: [
				"-B",
				"-m",
				"dsh_pack"
			],
			env: { PYTHONPATH: pythonPath }
		}, {
			command: "python3",
			prefix: [
				"-B",
				"-m",
				"dsh_pack"
			],
			env: { PYTHONPATH: pythonPath }
		}, {
			command: "py",
			prefix: [
				"-3",
				"-B",
				"-m",
				"dsh_pack"
			],
			env: { PYTHONPATH: pythonPath }
		});
	}
	let lastError;
	for (const candidate of candidates) try {
		return await spawnCore(home, candidate, args);
	} catch (error) {
		lastError = error;
		if (!isCommandNotFound(error)) throw error;
	}
	throw new Error(`DSH Crate Core is unavailable: ${failMessage(lastError)}. Install dsh-crate or keep the bundled Core runner in the plugin package.`);
}
function parseCore(stdout) {
	return JSON.parse(stdout);
}
function isObject(value) {
	return value !== null && typeof value === "object" && !Array.isArray(value);
}
function coreDiagnostic(result, fallback, operation) {
	if (isObject(result) && isObject(result.error)) return result.error;
	return {
		message: fallback,
		...diagnosticEnvelope(operation, "FAIL")
	};
}
function runtimeCoreArgs() {
	const args = [
		"--node-version",
		process.version.replace(/^v/, ""),
		"--os-name",
		platform() === "win32" ? "windows" : platform()
	];
	if (process.env.DSH_VERSION) args.push("--dsh-version", process.env.DSH_VERSION);
	return args;
}
function argumentValue(args, flag) {
	const index = args.indexOf(flag);
	return index >= 0 && typeof args[index + 1] === "string" ? args[index + 1] : void 0;
}
function replaceArgument(args, flag, value) {
	const next = [...args];
	const index = next.indexOf(flag);
	if (index >= 0 && index + 1 < next.length) next[index + 1] = value;
	else next.push(flag, value);
	return next;
}
function currentRuntime(home) {
	const args = process.argv.slice(2);
	const portValue = argumentValue(args, "--port") ?? process.env.DSH_PACK_PORT;
	const port = portValue !== void 0 && /^\d+$/.test(portValue) ? Number(portValue) : void 0;
	return {
		currentProfile: argumentValue(args, "--profile") ?? process.env.DSH_PACK_ACTIVE_PROFILE ?? null,
		pid: process.pid,
		dshHome: home,
		port: port ?? null,
		restartConfigured: typeof process.argv[1] === "string" && port !== void 0
	};
}
function operationDiagnostic(code, stage, item, message, impact, suggestedNextStep, operation) {
	return {
		code,
		stage,
		severity: "BLOCKER",
		item,
		expected: "the requested Profile operation completes safely",
		observed: message,
		evidence: {
			code,
			stage,
			item
		},
		impact,
		canContinue: false,
		suggestedNextStep,
		suggestedChecks: [
			"confirm the exact Profile name and operation evidence above",
			"verify the target DSH_HOME and Profile path are correct",
			"retry after correcting the reported item"
		],
		message,
		...diagnosticEnvelope(operation, "FAIL")
	};
}
async function savePack(work, action, value) {
	const path = join(work, `${action}-${randomUUID()}.dshcrate`);
	await writeFile(path, decodePack(value), { flag: "wx" });
	return path;
}
async function readInstalledBundle(packagePath, location) {
	try {
		const packageJson = JSON.parse(await readFile(join(packagePath, "package.json"), "utf8"));
		if (!isObject(packageJson)) return void 0;
		const dsh = packageJson.dsh;
		const bundle = dsh !== null && typeof dsh === "object" && !Array.isArray(dsh) ? dsh.bundle : void 0;
		if (bundle === null || typeof bundle !== "object" || Array.isArray(bundle)) return void 0;
		const patch = bundle.patch;
		if (typeof packageJson.name !== "string" || typeof packageJson.version !== "string" || typeof patch !== "string" || patch.trim() === "") return void 0;
		return {
			name: packageJson.name,
			version: packageJson.version,
			patch,
			location
		};
	} catch {
		return;
	}
}
let profileInvariantPromise;
async function ensureCrateBundleInAllProfilesOnce(home) {
	const profilesRoot = join(home, "profiles");
	let entries;
	try {
		entries = await readdir(profilesRoot, { withFileTypes: true });
	} catch (error) {
		if (error.code === "ENOENT") return;
		throw error;
	}
	const packageRoot = dirname(dirname(fileURLToPath(import.meta.url)));
	const sourceManifest = JSON.parse(await readFile(join(packageRoot, "package.json"), "utf8"));
	const sourceVersion = typeof sourceManifest.version === "string" ? sourceManifest.version : void 0;
	if (sourceVersion === void 0) throw new Error("DSH Crate package version is missing");
	const anchorPackage = join(profilesRoot, "node_modules", ...CRATE_PACKAGE_NAME.split("/"));
	let anchorManifest;
	try {
		const value = JSON.parse(await readFile(join(anchorPackage, "package.json"), "utf8"));
		if (isObject(value)) anchorManifest = value;
	} catch (error) {
		if (error.code !== "ENOENT") throw error;
	}
	if (anchorManifest === void 0 && resolve(packageRoot) !== resolve(anchorPackage)) {
		try {
			await stat(anchorPackage);
			throw new Error(`DSH Crate installation anchor exists but has no valid package.json: ${anchorPackage}`);
		} catch (error) {
			if (error.code !== "ENOENT") throw error;
		}
		await mkdir(dirname(anchorPackage), { recursive: true });
		await cp(packageRoot, anchorPackage, { recursive: true });
		const value = JSON.parse(await readFile(join(anchorPackage, "package.json"), "utf8"));
		if (isObject(value)) anchorManifest = value;
	}
	const crateVersion = typeof anchorManifest?.version === "string" ? anchorManifest.version : sourceVersion;
	for (const entry of entries) {
		if (!entry.isDirectory() || !SAFE_NAME.test(entry.name)) continue;
		const manifestPath = join(profilesRoot, entry.name, "package.json");
		let manifest;
		try {
			const value = JSON.parse(await readFile(manifestPath, "utf8"));
			if (!isObject(value)) continue;
			manifest = value;
		} catch {
			continue;
		}
		const dependenciesValue = manifest.dependencies;
		if (dependenciesValue !== void 0 && !isObject(dependenciesValue)) continue;
		const dependencies = isObject(dependenciesValue) ? dependenciesValue : {};
		const dshValue = manifest.dsh;
		if (dshValue !== void 0 && !isObject(dshValue)) continue;
		const dsh = isObject(dshValue) ? dshValue : {};
		const profileValue = dsh.profile;
		if (profileValue !== void 0 && !isObject(profileValue)) continue;
		const profile = isObject(profileValue) ? profileValue : {};
		const bundlesValue = profile.bundles;
		if (bundlesValue !== void 0 && (!Array.isArray(bundlesValue) || bundlesValue.some((item) => typeof item !== "string"))) continue;
		const bundles = Array.isArray(bundlesValue) ? [...bundlesValue] : [];
		let changed = false;
		if (typeof dependencies[CRATE_PACKAGE_NAME] !== "string") {
			dependencies[CRATE_PACKAGE_NAME] = crateVersion;
			changed = true;
		}
		if (!bundles.includes(CRATE_PACKAGE_NAME)) {
			bundles.push(CRATE_PACKAGE_NAME);
			changed = true;
		}
		if (!changed) continue;
		manifest.dependencies = dependencies;
		manifest.dsh = {
			...dsh,
			profile: {
				...profile,
				bundles
			}
		};
		await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
	}
}
async function ensureCrateBundleInAllProfiles(home) {
	if (profileInvariantPromise !== void 0) return profileInvariantPromise;
	profileInvariantPromise = ensureCrateBundleInAllProfilesOnce(home);
	try {
		await profileInvariantPromise;
	} finally {
		profileInvariantPromise = void 0;
	}
}
async function listInstalledBundles(profileModules, anchorModules) {
	const bundles = /* @__PURE__ */ new Map();
	const addBundle = (bundle) => {
		if (bundle === void 0 || typeof bundle.name !== "string" || bundles.has(bundle.name)) return;
		bundles.set(bundle.name, bundle);
	};
	const scanRoot = async (root, location) => {
		let entries;
		try {
			entries = await readdir(root, { withFileTypes: true });
		} catch (error) {
			if (error.code === "ENOENT") return;
			throw error;
		}
		for (const entry of entries) {
			if (entry.name.startsWith(".")) continue;
			const candidate = join(root, entry.name);
			const direct = await readInstalledBundle(candidate, location);
			if (direct !== void 0) {
				addBundle(direct);
				continue;
			}
			if (!entry.name.startsWith("@")) continue;
			let scopedEntries;
			try {
				scopedEntries = await readdir(candidate, { withFileTypes: true });
			} catch (error) {
				if (error.code === "ENOENT") continue;
				throw error;
			}
			for (const scopedEntry of scopedEntries) {
				if (scopedEntry.name.startsWith(".")) continue;
				addBundle(await readInstalledBundle(join(candidate, scopedEntry.name), location));
			}
		}
	};
	await scanRoot(profileModules, "profile");
	await scanRoot(anchorModules, "installation-anchor");
	return [...bundles.values()].sort((left, right) => String(left.name).localeCompare(String(right.name)));
}
/**
* Packages published by the DSH project are treated as official built-ins.
* This is the single source of truth for the official/user split used by the
* plugin inventory UI: a runtime loader row is official only when the package
* itself is an official bundle, or when an official bundle's patch inserts it
* as a built-in loader row (for example the official web-app bundle composes
* `dsh-better-sidebar` under its own package name). Loader row ids are
* deliberately NOT used, because a user plugin may register a row id that
* collides with an official built-in (for example a custom sidebar) and must
* stay in the user group.
*/
function isOfficialPackage(name) {
	return name.startsWith("@deepseek-ai/");
}
/** Loader row identities (`id`/`name`) registered by an ``insert`` block. */
function insertedLoaderRows(patchText) {
	const rows = [];
	let inInsert = false;
	let insertIndent;
	let fieldIndent;
	for (const raw of patchText.split(/\r?\n/)) {
		const line = raw.replace(/\s+$/, "");
		const stripped = line.trim();
		if (!stripped || stripped.startsWith("#")) continue;
		const indent = line.length - line.trimStart().length;
		if (indent === 0 && stripped.startsWith("- ")) {
			inInsert = stripped.slice(2).trim() === "insert:";
			insertIndent = void 0;
			fieldIndent = void 0;
			continue;
		}
		if (!inInsert) continue;
		if (stripped.startsWith("- ")) {
			if (insertIndent === void 0) insertIndent = indent;
			if (indent !== insertIndent) continue;
			fieldIndent = indent + 2;
			const row = stripped.slice(2).trim();
			const match = /^([a-zA-Z][a-zA-Z0-9_-]*):\s*(.*)$/.exec(row);
			if (match === null) continue;
			const value = match[2].trim().replace(/^["']|["']$/g, "");
			if (value === "") continue;
			if (match[1] === "id") rows.push({ id: value });
			if (match[1] === "name") rows.push({ name: value });
			continue;
		}
		if (fieldIndent === void 0 || indent !== fieldIndent) continue;
		const field = /^([a-zA-Z][a-zA-Z0-9_-]*):\s*(.*)$/.exec(stripped);
		if (field === null) continue;
		const value = field[2].trim().replace(/^["']|["']$/g, "");
		if (value === "") continue;
		if (field[1] === "id") rows.push({ id: value });
		if (field[1] === "name") rows.push({ name: value });
	}
	return rows;
}
/** Loader row ids registered via top-level ``insert`` blocks. */
function insertedLoaderIds(patchText) {
	return insertedLoaderRows(patchText).filter((row) => row.id !== void 0).map((row) => row.id);
}
/** Loader row package names registered via top-level ``insert`` blocks. */
function insertedLoaderNames(patchText) {
	return insertedLoaderRows(patchText).filter((row) => row.name !== void 0).map((row) => row.name);
}
/** Read one installed Bundle's patch text from either resolution root. */
async function readInstalledBundlePatch(home, profileName, bundleName, patch) {
	const segments = bundleName.split("/");
	const candidates = [join(home, "profiles", profileName, "node_modules", ...segments), join(home, "profiles", "node_modules", ...segments)];
	for (const candidate of candidates) try {
		return await readFile(join(candidate, patch), "utf8");
	} catch {}
}
/** Loader row ids registered by one installed Bundle patch. */
async function installedBundlePatchIds(home, profileName, bundleName, patch) {
	const ids = /* @__PURE__ */ new Set();
	const patchText = await readInstalledBundlePatch(home, profileName, bundleName, patch);
	if (patchText === void 0) return ids;
	for (const id of insertedLoaderIds(patchText)) ids.add(id);
	return ids;
}
/**
* The set of package names treated as official built-ins for a Profile:
* every @deepseek-ai/* bundle plus every loader row name its patches insert.
*/
async function officialBundleNames(home, profileName, bundles) {
	const official = /* @__PURE__ */ new Set();
	const pending = [];
	for (const bundle of bundles) {
		if (typeof bundle.name !== "string" || !bundle.name.startsWith("@deepseek-ai/")) continue;
		official.add(bundle.name);
		if (typeof bundle.patch === "string" && bundle.patch.trim() !== "") pending.push({
			name: bundle.name,
			patch: bundle.patch
		});
	}
	for (const item of pending) {
		const patchText = await readInstalledBundlePatch(home, profileName, item.name, item.patch);
		if (patchText === void 0) continue;
		for (const name of insertedLoaderNames(patchText)) official.add(name);
	}
	return official;
}
async function listProfiles(home) {
	const root = join(home, "profiles");
	try {
		const entries = await readdir(root, { withFileTypes: true });
		const profiles = [];
		for (const entry of entries) {
			if (!entry.isDirectory() || !SAFE_NAME.test(entry.name)) continue;
			try {
				const packageJson = JSON.parse(await readFile(join(root, entry.name, "package.json"), "utf8"));
				if (packageJson === null || typeof packageJson !== "object" || Array.isArray(packageJson)) continue;
				const manifest = packageJson;
				const dsh = manifest.dsh;
				const profile = dsh !== null && typeof dsh === "object" && !Array.isArray(dsh) ? dsh.profile : void 0;
				const bundles = profile !== null && typeof profile === "object" && !Array.isArray(profile) ? profile.bundles : [];
				const dependencies = manifest.dependencies;
				const dependencyNames = dependencies !== null && typeof dependencies === "object" && !Array.isArray(dependencies) ? Object.keys(dependencies) : [];
				const composedBundles = Array.isArray(bundles) ? bundles.filter((name) => typeof name === "string") : [];
				const activePlugins = new Set(composedBundles);
				const scannedBundles = await listInstalledBundles(join(root, entry.name, "node_modules"), join(root, "node_modules"));
				const officialNames = await officialBundleNames(home, entry.name, scannedBundles);
				const installedBundles = scannedBundles.map((bundle) => ({
					...bundle,
					active: activePlugins.has(String(bundle.name)),
					official: officialNames.has(String(bundle.name))
				})).filter((bundle) => bundle.active === true || dependencyNames.includes(String(bundle.name)));
				const activeRowIds = /* @__PURE__ */ new Set();
				const installedRowIds = /* @__PURE__ */ new Map();
				for (const bundle of installedBundles) {
					if (typeof bundle.patch !== "string") continue;
					const rowIds = await installedBundlePatchIds(home, entry.name, String(bundle.name), bundle.patch);
					installedRowIds.set(String(bundle.name), rowIds);
					if (bundle.active === true) for (const id of rowIds) activeRowIds.add(id);
				}
				const conflicts = /* @__PURE__ */ new Map();
				for (const bundle of installedBundles) {
					if (bundle.active === true) continue;
					const rowIds = installedRowIds.get(String(bundle.name)) ?? /* @__PURE__ */ new Set();
					for (const id of rowIds) if (activeRowIds.has(id)) {
						conflicts.set(String(bundle.name), true);
						break;
					}
				}
				const composedInstalledBundles = installedBundles.map((bundle) => ({
					...bundle,
					conflict: conflicts.get(String(bundle.name)) === true
				}));
				profiles.push({
					name: entry.name,
					plugins: [...activePlugins],
					installedBundles: composedInstalledBundles
				});
			} catch {}
		}
		return profiles.sort((a, b) => String(a.name).localeCompare(String(b.name)));
	} catch (error) {
		if (error.code === "ENOENT") return [];
		throw error;
	}
}
const PROFILE_PATCH_TEMPLATE = `# Your patch layer for this dsh profile, applied after every bundle layer:
# a top-level YAML array of loader patch entries (id-targeted config
# overrides, disables, and insert lists; \`!!js\` expressions allowed).
[]
`;
const PROFILE_PNPM_WORKSPACE = `packages:
  - .

nodeLinker: hoisted
autoInstallPeers: false
`;
/** Official bundles every newly created Profile composes by default. */
const DEFAULT_CREATE_BUNDLES = [
	"@deepseek-ai/dsh-base",
	"@deepseek-ai/dsh-web-app",
	CRATE_PACKAGE_NAME
];
async function readInstalledVersion(packageRoot) {
	try {
		const value = JSON.parse(await readFile(join(packageRoot, "package.json"), "utf8"));
		if (isObject(value) && typeof value.version === "string" && value.version !== "") return value.version;
		return;
	} catch {
		return;
	}
}
async function createProfile(home, body, workspace) {
	const profileName = safeName(body.profileName, "profileName");
	if (profileName === "." || profileName === ".." || profileName === "node_modules") return {
		status: "failed",
		command: "create-profile",
		exitCode: 2,
		error: operationDiagnostic("PROFILE_NAME_RESERVED", "planning", profileName, `Profile name is reserved: ${profileName}`, "The requested Profile was not created.", "Choose another Profile name and retry.", "create-profile")
	};
	const profilesRoot = join(home, "profiles");
	const profileDir = join(profilesRoot, profileName);
	const profileRelative = relative(profilesRoot, resolve(profileDir));
	if (!profileRelative || profileRelative.startsWith("..") || profileRelative.includes("\\")) throw new Error("profileName escaped DSH_HOME");
	try {
		await access(join(profileDir, "package.json"));
		return {
			status: "failed",
			command: "create-profile",
			exitCode: 2,
			error: operationDiagnostic("PROFILE_EXISTS", "planning", profileName, `Profile already exists: ${profileName}`, "No Profile was created or modified.", "Choose a different Profile name, or delete the existing Profile first.", "create-profile")
		};
	} catch {}
	const officialBase = await readInstalledVersion(join(profilesRoot, "node_modules", "@deepseek-ai", "dsh-base"));
	const officialWeb = await readInstalledVersion(join(profilesRoot, "node_modules", "@deepseek-ai", "dsh-web-app"));
	if (officialBase === void 0 || officialWeb === void 0) return {
		status: "failed",
		command: "create-profile",
		exitCode: 2,
		error: operationDiagnostic("OFFICIAL_BUNDLE_MISSING", "planning", profileName, `cannot resolve official bundle version: ${officialBase === void 0 ? "@deepseek-ai/dsh-base" : "@deepseek-ai/dsh-web-app"}`, "The requested Profile was not created.", `Install the official DSH bundles into this DSH_HOME first (${profilesRoot}/node_modules), then retry.`, "create-profile")
	};
	const packageRoot = dirname(dirname(fileURLToPath(import.meta.url)));
	const sourceManifest = JSON.parse(await readFile(join(packageRoot, "package.json"), "utf8"));
	const crateVersion = typeof sourceManifest.version === "string" ? sourceManifest.version : void 0;
	if (crateVersion === void 0) return {
		status: "failed",
		command: "create-profile",
		exitCode: 2,
		error: operationDiagnostic("CRATE_VERSION_MISSING", "planning", profileName, "DSH Crate package version is missing", "The requested Profile was not created.", "Repair the DSH Crate installation and retry.", "create-profile")
	};
	await mkdir(profileDir, { recursive: true });
	const manifest = {
		name: `dsh-profile-${profileName}`,
		private: true,
		dependencies: {
			"@deepseek-ai/dsh-base": officialBase,
			"@deepseek-ai/dsh-web-app": officialWeb,
			[CRATE_PACKAGE_NAME]: crateVersion
		},
		dsh: { profile: { bundles: [...DEFAULT_CREATE_BUNDLES] } }
	};
	await writeFile(join(profileDir, "package.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
	await writeFile(join(profileDir, "cordis.patch.yml"), PROFILE_PATCH_TEMPLATE, "utf8");
	await writeFile(join(profileDir, "pnpm-workspace.yaml"), PROFILE_PNPM_WORKSPACE, "utf8");
	await ensureCrateBundleInAllProfiles(home);
	const item = await record(workspace.history, {
		time: (/* @__PURE__ */ new Date()).toISOString(),
		action: "create-profile",
		status: "PASS",
		profile: profileName
	});
	return {
		status: "ok",
		command: "create-profile",
		exitCode: 0,
		profile: (await listProfiles(home)).find((candidate) => candidate.name === profileName) ?? {
			name: profileName,
			plugins: DEFAULT_CREATE_BUNDLES,
			installedBundles: []
		},
		history: item
	};
}
async function handleApi(home, body, runtimePlugins = []) {
	const action = body.action;
	const workspace = await ensureWorkspace(home);
	await ensureCrateBundleInAllProfiles(home);
	if (action === "profiles") {
		const runtime = currentRuntime(home);
		const profiles = await listProfiles(home);
		const runtimeOfficialNames = /* @__PURE__ */ new Set();
		const runtimeRow = typeof runtime.currentProfile === "string" ? profiles.find((candidate) => candidate.name === runtime.currentProfile) : void 0;
		if (runtimeRow !== void 0 && Array.isArray(runtimeRow.installedBundles)) {
			const names = await officialBundleNames(home, String(runtimeRow.name), runtimeRow.installedBundles);
			for (const name of names) runtimeOfficialNames.add(name);
		}
		const isOfficialRow = (row) => {
			const name = typeof row.name === "string" ? row.name : "";
			return isOfficialPackage(name) || runtimeOfficialNames.has(name);
		};
		return {
			status: "ok",
			profiles,
			runtimePlugins: runtimePlugins.map((row) => ({
				...row,
				official: isOfficialRow(row)
			})),
			runtime
		};
	}
	if (action === "create-profile") return createProfile(home, body, workspace);
	if (action === "history") return {
		status: "ok",
		history: await readHistory(workspace.history)
	};
	if (action === "inspect") {
		const pack = await savePack(workspace.work, "inspect", body.packBase64);
		const run = await runCore(home, [
			"inspect",
			pack,
			"--json",
			"--allow-network-reference-install",
			...runtimeCoreArgs()
		]);
		try {
			const result = parseCore(run.stdout);
			let targetProfile;
			let requestedProfileName;
			try {
				const planArgs = [
					"import",
					pack,
					"--dsh-home",
					home,
					"--plan-only",
					"--json",
					...runtimeCoreArgs()
				];
				if (typeof body.targetProfile === "string") planArgs.push("--target-profile", safeName(body.targetProfile, "targetProfile"));
				if (body.overwrite === true) planArgs.push("--overwrite");
				const planRun = await runCore(home, planArgs);
				if (planRun.code === 0) {
					const planned = parseCore(planRun.stdout);
					if (isObject(planned) && isObject(planned.plan)) {
						if (typeof planned.plan.profileName === "string") targetProfile = planned.plan.profileName;
						if (typeof planned.plan.requestedProfileName === "string") requestedProfileName = planned.plan.requestedProfileName;
					}
				}
			} catch {}
			const enriched = isObject(result) ? {
				...result,
				...targetProfile ? { targetProfile } : {},
				...requestedProfileName ? { requestedProfileName } : {}
			} : result;
			return {
				status: "ok",
				command: action,
				exitCode: run.code,
				result: enriched
			};
		} catch {
			return {
				status: "failed",
				command: action,
				exitCode: run.code,
				error: coreDiagnostic(void 0, run.stderr || run.stdout || "dsh-crate inspect failed", action)
			};
		}
	}
	if (action === "export") {
		const profileName = safeName(body.profileName, "profileName");
		const profile = join(home, "profiles", profileName);
		const profileRelative = relative(join(home, "profiles"), resolve(profile));
		if (!profileRelative || profileRelative.startsWith("..") || profileRelative.includes("\\")) throw new Error("profileName escaped DSH_HOME");
		const outputName = `${profileName}-${(/* @__PURE__ */ new Date()).toISOString().replace(/[:.]/g, "-")}-${randomUUID()}.dshcrate`;
		const args = [
			"export",
			"--profile",
			profile,
			"--output",
			join(workspace.exports, outputName),
			"--json",
			...runtimeCoreArgs()
		];
		if (body.includeInstalledBundles === true) args.push("--include-installed-bundles");
		const embed = Array.isArray(body.embed) ? body.embed : [];
		const referenceOnly = Array.isArray(body.referenceOnly) ? body.referenceOnly : [];
		for (const name of embed) args.push("--embed", safePluginName(name, "embed plugin"));
		for (const name of referenceOnly) args.push("--reference-only", safePluginName(name, "reference-only plugin"));
		const requiredSecrets = Array.isArray(body.requiredSecrets) ? body.requiredSecrets : [];
		for (const name of requiredSecrets) args.push("--required-secret", safeName(name, "required Secret"));
		const run = await runCore(home, args);
		let result;
		try {
			result = parseCore(run.stdout);
		} catch {
			result = void 0;
		}
		if (run.code !== 0 || result === void 0) {
			const failure = {
				status: "failed",
				action,
				exitCode: run.code,
				error: coreDiagnostic(result, run.stderr || run.stdout || "dsh-crate export failed", action),
				result
			};
			await record(workspace.history, {
				time: (/* @__PURE__ */ new Date()).toISOString(),
				action,
				status: "FAIL",
				profile: profileName,
				message: String(failure.error.message ?? "dsh-crate export failed"),
				code: failure.error.code,
				stage: failure.error.stage
			});
			return failure;
		}
		const item = await record(workspace.history, {
			time: (/* @__PURE__ */ new Date()).toISOString(),
			action,
			status: "PASS",
			profile: profileName,
			pack: outputName
		});
		return {
			status: "ok",
			command: action,
			exitCode: run.code,
			result,
			downloadName: outputName,
			history: item
		};
	}
	if (action === "import") {
		const args = [
			"import",
			await savePack(workspace.work, "import", body.packBase64),
			"--dsh-home",
			home,
			"--json",
			...runtimeCoreArgs()
		];
		if (typeof body.targetProfile === "string") args.push("--target-profile", safeName(body.targetProfile, "targetProfile"));
		if (body.overwrite === true) args.push("--overwrite");
		if (body.confirmOverwrite === true) args.push("--confirm-overwrite");
		const run = await runCore(home, args);
		let result;
		try {
			result = parseCore(run.stdout);
		} catch {
			result = void 0;
		}
		if (run.code !== 0 || result === void 0) {
			const message = run.stderr || run.stdout || "dsh-crate import failed";
			const failure = {
				status: "failed",
				action,
				exitCode: run.code,
				error: coreDiagnostic(result, message, action),
				result
			};
			await record(workspace.history, {
				time: (/* @__PURE__ */ new Date()).toISOString(),
				action,
				status: "FAIL",
				message: String(failure.error.message ?? message),
				code: failure.error.code,
				stage: failure.error.stage
			});
			return failure;
		}
		await ensureCrateBundleInAllProfiles(home);
		const plan = result.plan;
		const profileName = plan !== null && typeof plan === "object" && !Array.isArray(plan) && typeof plan.profileName === "string" ? plan.profileName : void 0;
		const item = await record(workspace.history, {
			time: (/* @__PURE__ */ new Date()).toISOString(),
			action,
			status: "PASS",
			...profileName ? { profile: profileName } : {}
		});
		let profileRow;
		if (profileName !== void 0) try {
			profileRow = (await listProfiles(home)).find((candidate) => candidate.name === profileName);
		} catch {}
		return {
			status: "ok",
			command: action,
			exitCode: run.code,
			result,
			...profileRow !== void 0 ? { profile: profileRow } : {},
			history: item
		};
	}
	if (action === "delete-profile") {
		const profileName = safeName(body.profileName, "profileName");
		if (currentRuntime(home).currentProfile === profileName) return {
			status: "failed",
			command: action,
			exitCode: 2,
			error: operationDiagnostic("ACTIVE_PROFILE", "planning", profileName, `cannot delete the active Profile: ${profileName}`, "The running DSH process would lose its Profile files.", "Switch to another Profile first, then delete this Profile.", "delete-profile")
		};
		const args = [
			"delete-profile",
			"--dsh-home",
			home,
			"--profile",
			profileName,
			"--json"
		];
		if (body.confirmDelete === true) args.push("--confirm-delete");
		const run = await runCore(home, args);
		let result;
		try {
			result = parseCore(run.stdout);
		} catch {
			result = void 0;
		}
		if (run.code !== 0 || result === void 0) {
			const message = run.stderr || run.stdout || "dsh-crate Profile deletion failed";
			const failure = {
				status: "failed",
				action,
				exitCode: run.code,
				error: coreDiagnostic(result, message, action),
				result
			};
			await record(workspace.history, {
				time: (/* @__PURE__ */ new Date()).toISOString(),
				action,
				status: "FAIL",
				profile: profileName,
				message: String(failure.error.message ?? message),
				code: failure.error.code,
				stage: failure.error.stage
			});
			return failure;
		}
		const item = await record(workspace.history, {
			time: (/* @__PURE__ */ new Date()).toISOString(),
			action,
			status: "PASS",
			profile: profileName
		});
		return {
			status: "ok",
			command: action,
			exitCode: run.code,
			result,
			history: item
		};
	}
	if (action === "switch-status") {
		const operationId = typeof body.operationId === "string" && SAFE_OPERATION_ID.test(body.operationId) ? body.operationId : (() => {
			throw new Error("operationId is invalid");
		})();
		const reportPath = join(workspace.work, `switch-${operationId}.json`);
		try {
			const value = JSON.parse(await readFile(reportPath, "utf8"));
			return {
				status: "ok",
				command: action,
				operationId,
				result: isObject(value) ? value : {
					status: "failed",
					message: "switch report is malformed"
				}
			};
		} catch (error) {
			if (error.code === "ENOENT") return {
				status: "ok",
				command: action,
				operationId,
				result: {
					status: "pending",
					operationId,
					message: "Switch operation has not produced a report yet."
				}
			};
			throw error;
		}
	}
	if (action === "switch-profile") {
		const profileName = safeName(body.profileName, "profileName");
		if (body.confirmSwitch !== true) return {
			status: "failed",
			command: action,
			exitCode: 2,
			error: operationDiagnostic("SWITCH_CONFIRMATION_REQUIRED", "planning", profileName, "switching Profile requires explicit confirmation", "The current DSH process was not changed.", "Confirm the switch and retry.", "switch-profile")
		};
		if (!(await listProfiles(home)).some((profile) => profile.name === profileName)) return {
			status: "failed",
			command: action,
			exitCode: 2,
			error: operationDiagnostic("PROFILE_MISSING", "planning", profileName, `Profile does not exist: ${profileName}`, "The current DSH process was not changed.", "Choose an existing Profile and retry.", "switch-profile")
		};
		const runtime = currentRuntime(home);
		const oldProfile = typeof runtime.currentProfile === "string" ? runtime.currentProfile : void 0;
		if (oldProfile === profileName) {
			const item = await record(workspace.history, {
				time: (/* @__PURE__ */ new Date()).toISOString(),
				action,
				status: "PASS",
				profile: profileName,
				message: "Profile is already active; no restart was needed"
			});
			return {
				status: "ok",
				command: action,
				exitCode: 0,
				result: {
					status: "already-active",
					profileName,
					message: `Profile is already active: ${profileName}`,
					impact: "The current DSH process was not changed; the requested Profile is already running.",
					canContinue: true
				},
				history: item
			};
		}
		if (runtime.restartConfigured !== true || typeof process.argv[1] !== "string" || typeof runtime.port !== "number") return {
			status: "failed",
			command: action,
			exitCode: 2,
			error: operationDiagnostic("RESTART_NOT_CONFIGURED", "planning", profileName, "the current DSH launch command cannot be safely reconstructed", "The current DSH process was not changed.", "Start DSH with an explicit --profile and --port, or configure the DSH Crate restart launcher.", "switch-profile")
		};
		const operationId = randomUUID();
		const reportPath = join(workspace.work, `switch-${operationId}.json`);
		const args = replaceArgument(replaceArgument(process.argv.slice(2), "--profile", profileName), "--port", String(runtime.port));
		const helperPath = join(dirname(fileURLToPath(import.meta.url)), "..", "restart-helper.mjs");
		try {
			await access(helperPath);
		} catch {
			throw new Error(`restart helper is missing: ${helperPath}`);
		}
		const spec = {
			operationId,
			reportPath,
			oldPid: process.pid,
			oldProfile,
			targetProfile: profileName,
			nodePath: process.execPath,
			scriptPath: resolve(process.argv[1]),
			args,
			cwd: process.cwd(),
			env: {
				...process.env,
				DSH_HOME: home,
				DSH_PACK_ACTIVE_PROFILE: profileName,
				DSH_PACK_PORT: String(runtime.port)
			},
			url: `http://127.0.0.1:${runtime.port}/`
		};
		await writeFile(reportPath, `${JSON.stringify({
			status: "pending",
			operationId,
			stage: "scheduled",
			oldProfile,
			targetProfile: profileName,
			message: "Switch scheduled."
		}, null, 2)}\n`, {
			encoding: "utf8",
			flag: "wx"
		});
		const encoded = Buffer.from(JSON.stringify(spec), "utf8").toString("base64url");
		spawn(process.execPath, [helperPath, encoded], {
			detached: true,
			windowsHide: true,
			stdio: "ignore"
		}).unref();
		const item = await record(workspace.history, {
			time: (/* @__PURE__ */ new Date()).toISOString(),
			action,
			status: "PASS",
			profile: profileName,
			oldProfile,
			operationId,
			message: "Switch scheduled; waiting for the target Profile to become ready."
		});
		setTimeout(() => process.exit(0), 650);
		return {
			status: "ok",
			command: action,
			operationId,
			history: item,
			result: {
				status: "pending",
				operationId,
				oldProfile,
				targetProfile: profileName,
				message: "Switch scheduled; waiting for the target Profile to become ready."
			}
		};
	}
	if (action === "verify") {
		const profileName = safeName(body.profileName, "profileName");
		const mode = body.mode === void 0 ? "web" : body.mode;
		if (mode !== "web" && mode !== "headless") throw new Error("mode must be web or headless");
		const args = [
			"verify",
			"--dsh-home",
			home,
			"--profile",
			profileName,
			"--mode",
			mode,
			"--json",
			...runtimeCoreArgs()
		];
		let runnerConfigPath;
		if (body.runnerConfig !== void 0) {
			if (!isObject(body.runnerConfig)) throw new Error("runnerConfig must be a JSON object");
			const verifyDir = join(workspace.work, "verify");
			await mkdir(verifyDir, { recursive: true });
			runnerConfigPath = join(verifyDir, "verify-" + randomUUID() + ".json");
			await writeFile(runnerConfigPath, JSON.stringify(body.runnerConfig, null, 2) + "\n", {
				encoding: "utf8",
				flag: "wx"
			});
			args.push("--runner-config", runnerConfigPath);
		}
		const run = await runCore(home, args);
		let result;
		try {
			result = parseCore(run.stdout);
		} catch {
			result = void 0;
		}
		if (result === void 0) return {
			status: "failed",
			action,
			exitCode: run.code,
			error: coreDiagnostic(void 0, run.stderr || run.stdout || "dsh-crate verify failed", action)
		};
		const resultObject = isObject(result) ? result : {};
		const status = typeof resultObject.status === "string" ? resultObject.status : "FAIL";
		const success = status === "PASS";
		const item = await record(workspace.history, {
			time: (/* @__PURE__ */ new Date()).toISOString(),
			action,
			status,
			profile: profileName
		});
		return {
			status: "ok",
			command: action,
			exitCode: run.code,
			result,
			history: item,
			success
		};
	}
	throw new Error(`unsupported DSH Crate action: ${String(action)}`);
}
async function handleDownload(home, req, res) {
	if (req.method !== "GET" && req.method !== "HEAD") {
		res.writeHead(405);
		res.end();
		return;
	}
	const safe = safeName(new URL(req.url ?? DOWNLOAD_PATH, "http://dsh.local").searchParams.get("name"), "download name");
	const root = resolve(join(home, ".dsh-pack", "exports"));
	const path = resolve(join(root, safe));
	if (dirname(path) !== root) throw new Error("download path escaped export directory");
	const info = await stat(path);
	res.writeHead(200, {
		"content-type": "application/octet-stream",
		"content-length": info.size,
		"content-disposition": `attachment; filename="${safe}"`
	});
	if (req.method === "HEAD") {
		res.end();
		return;
	}
	createReadStream(path).pipe(res);
}
/** Register the host bridge. The Core executable is intentionally external. */
const inject = ["webServer"];
function apply(ctx) {
	const home = resolve(process.env.DSH_HOME || process.cwd());
	ensureCrateBundleInAllProfiles(home).catch((error) => console.error(`dsh-crate-web: failed to ensure Profile invariant: ${failMessage(error)}`));
	ctx.effect(() => {
		const disposeApi = ctx.webServer.register({
			kind: "exact",
			path: API_PATH,
			handler: async (req, res) => {
				if (req.method !== "POST") {
					res.writeHead(405);
					res.end();
					return;
				}
				try {
					json(res, 200, await handleApi(home, await readRequest(req), listRuntimePlugins(ctx)));
				} catch (error) {
					json(res, 400, {
						status: "failed",
						error: { message: failMessage(error) }
					});
				}
			}
		});
		const disposeDownload = ctx.webServer.register({
			kind: "exact",
			path: DOWNLOAD_PATH,
			handler: (req, res) => {
				handleDownload(home, req, res).catch((error) => json(res, 404, {
					status: "failed",
					error: { message: failMessage(error) }
				}));
			}
		});
		return () => {
			disposeApi();
			disposeDownload();
		};
	}, "dsh-crate-web: local Core bridge");
}
//#endregion
export { apply, inject };
