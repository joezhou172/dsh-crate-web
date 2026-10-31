import { readRuntimeInventory } from "../runtime-inventory.mjs";
import { createHash, randomUUID } from "node:crypto";
import { access, lstat, mkdir, readFile, readdir, realpath, rename, rm, stat, unlink, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { createReadStream, readFileSync } from "node:fs";
import { platform } from "node:os";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
//#region src/desktop.ts
/** Read the official Desktop's bundled sources without changing its installation. */
function desktopRuntimeRoot(argv = process.argv) {
	return (argv[1] ?? "").replaceAll("\\", "/").includes("/@deepseek-ai/dsh-desktop-host/") && argv[2] ? resolve(argv[2]) : void 0;
}
function desktopRuntimeVersion() {
	const root = desktopRuntimeRoot();
	if (!root) return void 0;
	try {
		const pkg = JSON.parse(readFileSync(join(root, "node_modules", "@deepseek-ai", "dsh", "package.json"), "utf8"));
		return typeof pkg.version === "string" ? pkg.version : void 0;
	} catch {
		return;
	}
}
function rejectRequest(connection, req, res) {
	const status = connection?.requestRejection(req) ?? (connection ? void 0 : 503);
	if (status === void 0) return false;
	res.writeHead(status);
	res.end();
	return true;
}
async function copyPackage(source, target) {
	await mkdir(target, { recursive: true });
	for (const entry of await readdir(source, { withFileTypes: true })) {
		if ([
			"node_modules",
			".git",
			"cache",
			"logs"
		].includes(entry.name)) continue;
		const input = join(source, entry.name);
		const output = join(target, entry.name);
		if (entry.isDirectory()) await copyPackage(input, output);
		else if (entry.isFile()) await writeFile(output, await readFile(input));
		else throw new Error(`Unsupported link in Desktop package: ${entry.name}`);
	}
}
/** Public evidence for dependencies already supplied by this exact host. */
async function writeDesktopHostBundles(home, runtime = desktopRuntimeRoot()) {
	if (!runtime) return void 0;
	const modules = join(runtime, "node_modules");
	const bundles = {};
	const hashFiles = async (root, prefix = "") => {
		const result = {};
		for (const entry of await readdir(join(root, prefix), { withFileTypes: true })) {
			if ([
				"node_modules",
				".git",
				"cache",
				"logs"
			].includes(entry.name)) continue;
			const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
			if (entry.isDirectory()) Object.assign(result, await hashFiles(root, relative));
			else if (entry.isFile()) result[relative] = createHash("sha256").update(await readFile(join(root, relative))).digest("hex");
			else throw new Error("Unsupported link in official host Bundle evidence");
		}
		return result;
	};
	for (const entry of await readdir(join(modules, "@deepseek-ai"), { withFileTypes: true })) {
		if (!entry.isDirectory()) continue;
		const root = join(modules, "@deepseek-ai", entry.name);
		let manifest;
		try {
			manifest = JSON.parse(await readFile(join(root, "package.json"), "utf8"));
		} catch {
			continue;
		}
		if (!manifest.dsh?.bundle?.patch) continue;
		const dependencies = {};
		for (const name of Object.keys({
			...manifest.dependencies,
			...manifest.optionalDependencies
		})) try {
			const dependency = JSON.parse(await readFile(join(modules, ...name.split("/"), "package.json"), "utf8"));
			if (typeof dependency.version === "string") dependencies[name] = dependency.version;
		} catch {}
		bundles[`@deepseek-ai/${entry.name}`] = {
			manifest,
			dependencies,
			files: await hashFiles(root)
		};
	}
	const content = JSON.stringify({
		schemaVersion: 1,
		runtime,
		bundles
	});
	const destination = join(home, ".dsh-pack", "runtime-sources", `${createHash("sha256").update(content).digest("hex")}-host-bundles.json`);
	await mkdir(dirname(destination), { recursive: true });
	try {
		if (await readFile(destination, "utf8") === content) return destination;
	} catch {}
	const staging = `${destination}.${randomUUID()}.tmp`;
	await writeFile(staging, content, { flag: "wx" });
	try {
		await rename(staging, destination);
	} catch (error) {
		if (await readFile(destination, "utf8").catch(() => "") !== content) throw error;
	} finally {
		await rm(staging, { force: true });
	}
	return destination;
}
/** Electron can read ASAR; Python/npm cannot. Materialize only public package files. */
let materializing = Promise.resolve();
async function materializeDesktopModules(home, selectedNames = []) {
	const pending = materializing.then(() => materializeDesktopModulesOnce(home, selectedNames));
	materializing = pending.catch(() => void 0);
	return pending;
}
async function materializeDesktopModulesOnce(home, selectedNames) {
	const runtime = desktopRuntimeRoot();
	if (!runtime) return void 0;
	const modules = join(runtime, "node_modules");
	const version = await readFile(join(modules, "@deepseek-ai", "dsh", "package.json"), "utf8");
	const destination = join(home, ".dsh-pack", "runtime-sources", createHash("sha256").update(runtime).update(version).digest("hex").slice(0, 20), "node_modules");
	const names = new Set(selectedNames.filter((name) => /^@deepseek-ai\/[A-Za-z0-9._-]+$/.test(name)));
	const profiles = join(home, "profiles");
	for (const entry of await readdir(profiles, { withFileTypes: true })) {
		if (!entry.isDirectory() || entry.name === "node_modules" || entry.name.startsWith(".")) continue;
		try {
			const pkg = JSON.parse(await readFile(join(profiles, entry.name, "package.json"), "utf8"));
			for (const name of [...Object.keys(pkg.dependencies ?? {}), ...pkg.dsh?.profile?.bundles ?? []]) if (typeof name === "string" && /^@deepseek-ai\/[A-Za-z0-9._-]+$/.test(name)) names.add(name);
		} catch {
			continue;
		}
	}
	for (const name of names) {
		const source = join(modules, ...name.split("/"));
		let manifest;
		try {
			manifest = await readFile(join(source, "package.json"), "utf8");
		} catch (error) {
			if (error.code === "ENOENT") continue;
			throw error;
		}
		const target = join(destination, ...name.split("/"));
		try {
			if (await readFile(join(target, "package.json"), "utf8") === manifest) continue;
		} catch {}
		const staging = `${target}.staging-${process.pid}`;
		await rm(staging, {
			recursive: true,
			force: true
		});
		try {
			await copyPackage(source, staging);
			await mkdir(dirname(target), { recursive: true });
			await rm(target, {
				recursive: true,
				force: true
			});
			for (let attempt = 0;; attempt += 1) try {
				await rename(staging, target);
				break;
			} catch (error) {
				if (attempt >= 4 || ![
					"EPERM",
					"EACCES",
					"EBUSY"
				].includes(error.code ?? "")) throw error;
				await new Promise((done) => setTimeout(done, 100 * (attempt + 1)));
			}
		} finally {
			await rm(staging, {
				recursive: true,
				force: true
			});
		}
	}
	return destination;
}
//#endregion
//#region src/windows-runner-identity.ts
const windowsRunnerIdentity = {
	"version": "0.2.1-rc.3",
	"platform": "win32",
	"arch": "x64",
	"nodeSha256": "ba4e6d110e8c1592a1ecd390f6b05f3da124b13871a5be62b341a07a853c6c32",
	"providerSha256": "be6e1107871cf8d94c040090b13c405bc833822e2f51ed5280e93eececf762be",
	"files": {
		"node_modules/@deepseek-ai/cordis-plugin-loader/LICENSE": "034fb52b1d57360ecbae6cb1632a88f86fd7c3d3f5631a5f082710203dda0be7",
		"node_modules/@deepseek-ai/cordis-plugin-loader/README.md": "b73481e6c8503534d36197b64bdc604be126c466ea8ee9692812e6663ba218c4",
		"node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js": "638b9ad360e01236120772323f80a65570c4f3f42f4cfc6243330241025b6d72",
		"node_modules/@deepseek-ai/cordis-plugin-loader/package.json": "270d8d1ee5751e4173e7c4f9953bc19a1d370306d254c0ffaf21c37bc6deb78a",
		"node_modules/@deepseek-ai/cordis-plugin-loader/src/config/diff.ts": "6025a6b9798a0a16af017bb7d8d6394bbe345685b2ace56b15975add5843edb3",
		"node_modules/@deepseek-ai/cordis-plugin-loader/src/config/entry.ts": "6a061f1d3c2cdaac19409bf8ec6956ec5a0a457c4f1689be658d50af7c9ee294",
		"node_modules/@deepseek-ai/cordis-plugin-loader/src/config/group.ts": "5e138e8a8fad22e21d031859345797c445efbc380559fc32d35b03c835e60ccc",
		"node_modules/@deepseek-ai/cordis-plugin-loader/src/config/isolate.ts": "dfc9e961f61fe5f7701b5593f98902aa971884fb242e208fc0d5207794117094",
		"node_modules/@deepseek-ai/cordis-plugin-loader/src/config/tree.ts": "761889adfb6b8a164fb12a0cec49a6ef439598b9267e85073000cfa9b7d682c8",
		"node_modules/@deepseek-ai/cordis-plugin-loader/src/config/utils.ts": "d85b8ac1693af4667e9c0395cd1d6b15ec28387073a81f0d00bd38d909a05f8e",
		"node_modules/@deepseek-ai/cordis-plugin-loader/src/index.ts": "a135e2189a0feb0af08ff79de761698fb8ce7b41c96fefda1d4a299e5982fef3",
		"node_modules/@deepseek-ai/cordis-plugin-loader/src/internal.ts": "35a50d597fed58656a11e3c5294fdf99524ed8c106739b4fab522a288eefa877",
		"node_modules/@deepseek-ai/cordis/LICENSE": "034fb52b1d57360ecbae6cb1632a88f86fd7c3d3f5631a5f082710203dda0be7",
		"node_modules/@deepseek-ai/cordis/README.md": "4ed860307750b172e1176e476302174acacae2b0bb2b46479b4b9f6b336ecdcf",
		"node_modules/@deepseek-ai/cordis/bin.js": "cf84978c7e4165bf090b0d50c34c1986d06577f2ada27c902660783a142c3f81",
		"node_modules/@deepseek-ai/cordis/lib/index.js": "6a9394c0877ff45218818c6e815edd038f8057e1a1deb390a8d43ec81c57691e",
		"node_modules/@deepseek-ai/cordis/package.json": "b73831b926b16cbd684aa1b277461e7800a2b35e2dd351ad3c2c8c0db158589d",
		"node_modules/@deepseek-ai/cordis/src/context.ts": "96b388162d6013c1898de61e35f28917abb93809de24174980f2a1a348d0b115",
		"node_modules/@deepseek-ai/cordis/src/events.ts": "9aff93dcfcad98aebb692c19c36d3bf034a96f9085bc66900a997cda3f79e6fe",
		"node_modules/@deepseek-ai/cordis/src/fiber.ts": "b7661d6c19be76cef6b97d88719a8112c0f8b5abe65bd9e7d5947773fd4b96d4",
		"node_modules/@deepseek-ai/cordis/src/index.ts": "071fb226e9a21556625e4391b28e6641b9b34b1cd402155246e0437993d8b740",
		"node_modules/@deepseek-ai/cordis/src/logger.ts": "05cb6be3e4cf8d078185b5d10c87e536c7d2b2b3ad43c270a0dbafaa28f41fef",
		"node_modules/@deepseek-ai/cordis/src/reflect.ts": "6847b9781044023d65aebb5896a873b9f0a3d777eaf7fa0dd2a7a408eb6b74a6",
		"node_modules/@deepseek-ai/cordis/src/registry.ts": "34bbd60ae502b4f85201c204afb52a9acabde6878d9278493478c1b2183debd3",
		"node_modules/@deepseek-ai/cordis/src/service.ts": "614205c6ce7cf1a057b8b352e96aa4fcd734c967a3d2283a126c9c61f268e3be",
		"node_modules/@deepseek-ai/cordis/src/utils.ts": "8fe273424583d21267ef13f248840e97454d09d836a0ac08323a9482c2069263",
		"node_modules/@deepseek-ai/cosmokit/LICENSE": "034fb52b1d57360ecbae6cb1632a88f86fd7c3d3f5631a5f082710203dda0be7",
		"node_modules/@deepseek-ai/cosmokit/README.md": "fa0a17f50f83cda52ce623c9d42afb4eec1b33689285a0b9d2f655acbca13286",
		"node_modules/@deepseek-ai/cosmokit/lib/index.js": "ba44c0871656e4c7cac2c3c8a2ff644e0d2eb9d6bda7f6355866d686d513268e",
		"node_modules/@deepseek-ai/cosmokit/package.json": "70ef4acbb6f4186b9fd24d1e7f32457112179767cf42de849bf00ef7f63b0467",
		"node_modules/@deepseek-ai/cosmokit/src/array.ts": "cf4de899ecffd66a90d8cef6f4c7d127d31f77f776d8e173d41c30d2d7632cf7",
		"node_modules/@deepseek-ai/cosmokit/src/index.ts": "1087da74b9c461984e547d524ee766eebcf329a78e4720bff5b60a004ccf6e8c",
		"node_modules/@deepseek-ai/cosmokit/src/misc.ts": "117617943074ea57c15f216905dacd2f6d1c4c2ff16586f97a7a7a87dbf2141f",
		"node_modules/@deepseek-ai/cosmokit/src/string.ts": "5564272b3e15e49235cbe3a8b453f27306baf282d23a893982841670f65d3c04",
		"node_modules/@deepseek-ai/cosmokit/src/time.ts": "49957c4608465a1fbd738186a92c47fffcd1fc4ba59dbf89524f8a773fe16fe2",
		"node_modules/@deepseek-ai/cosmokit/src/types.ts": "cc49c12e4a637f7b0754ff78a8299e9c42fa40ee8c678550af0c538a80146a92",
		"node_modules/@deepseek-ai/cosmokit/src/volatile.ts": "937433215595f89da249ec7cabb89e331ff4135a40c6686a95666d2095315e55",
		"node_modules/@deepseek-ai/dsh-http-proxy/LICENSE": "ebb4f09972aee8608be255debaf78451a68e95c290f55c240dec2ecfa16ea6be",
		"node_modules/@deepseek-ai/dsh-http-proxy/README.i18n.yaml": "6411089157f986ec1f702f44bf2b713e167b81b2f59b68a1fd4bf279c8e86a51",
		"node_modules/@deepseek-ai/dsh-http-proxy/README.md": "0cc2ab58e8de7093ed6b9fe0a36f0a912950543c76c96a30cd8e8b510b9e18e4",
		"node_modules/@deepseek-ai/dsh-http-proxy/README.zh.md": "6ac5b9221f68f6c11fd2553caddc44eaa62366c8939ca8878ff469989cd8a15d",
		"node_modules/@deepseek-ai/dsh-http-proxy/lib/index.js": "5310861bc89788ea24be82a3b323e34cbd42b9e6214e2a179b2e6f92a8758cd5",
		"node_modules/@deepseek-ai/dsh-http-proxy/package.json": "e260d9e6c6dfbd0048d96e8b699909140ba54265db828a8c4b03cc68b2d85b30",
		"node_modules/@deepseek-ai/dsh-lazy-require/LICENSE": "ebb4f09972aee8608be255debaf78451a68e95c290f55c240dec2ecfa16ea6be",
		"node_modules/@deepseek-ai/dsh-lazy-require/README.i18n.yaml": "11345190fd51679a4bf9ae1e474b6e43152583732bcf249d5c8df537fd07a8e4",
		"node_modules/@deepseek-ai/dsh-lazy-require/README.md": "aacff96e3fa4502ad46fdceb12ca042833eb0356f918e099bf8be92b784f6ffd",
		"node_modules/@deepseek-ai/dsh-lazy-require/README.zh.md": "4a29f487e1a4531c98a6afd9711f92cebd9b870480cbba10588f230074dd0871",
		"node_modules/@deepseek-ai/dsh-lazy-require/lib/index.js": "eab2f914e4b5f54b2a1af5998eecd52f1b737146db44881ef51fb5e501e1faeb",
		"node_modules/@deepseek-ai/dsh-lazy-require/package.json": "7f1f25f58d4f2a6a493deec87fbbd9c3f5866ccf82ece9d06fa68b7b0639c002",
		"node_modules/@deepseek-ai/dsh-sandbox-windows-acl/LICENSE": "ebb4f09972aee8608be255debaf78451a68e95c290f55c240dec2ecfa16ea6be",
		"node_modules/@deepseek-ai/dsh-sandbox-windows-acl/README.i18n.yaml": "81c5f53c0a493dea7bfac547b8e85b568df678eb5d4f0924a287141f2ecf6d76",
		"node_modules/@deepseek-ai/dsh-sandbox-windows-acl/README.md": "346a18ad34ec0342dcbaf69cd473b62d5496907e7b6a4495a52a29bec702ee8f",
		"node_modules/@deepseek-ai/dsh-sandbox-windows-acl/README.zh.md": "d9c8d3e371162c10fdcf9595457944ef053db225875ae0a995ecfdb0620cc05c",
		"node_modules/@deepseek-ai/dsh-sandbox-windows-acl/assets/diagnose-windows-sandbox-acl/SKILL.md": "9c616c78892daeaea864a9b2d6baaea91ff133cf83cde0b725c6caee2d4933cb",
		"node_modules/@deepseek-ai/dsh-sandbox-windows-acl/assets/diagnose-windows-sandbox-acl/scripts/diagnose-windows-sandbox-acl.ps1": "adba89f3b10692302723d231d003cdf365311effaff996d32416f9531e3b63d9",
		"node_modules/@deepseek-ai/dsh-sandbox-windows-acl/lib/index.js": "83379e9c6e8bb725d0ed48ad086fc666bfe151c8c1a345e29e3da5b998aa4fd8",
		"node_modules/@deepseek-ai/dsh-sandbox-windows-acl/lib/runner.js": "9159aaa995d417e5948dd1cc3d8cd40616270e320048e577c58a1c65be3f3a2d",
		"node_modules/@deepseek-ai/dsh-sandbox-windows-acl/lib/types-Cl_DXjhk.js": "0bb3a34508785bdc34626542f9358d398fd9f60fdaf4b48201dfdff2122f25fc",
		"node_modules/@deepseek-ai/dsh-sandbox-windows-acl/package.json": "9f7060f0a08a1ffe5b92936eecda134867c126e2b976921ed9b02eedfd639a3f",
		"node_modules/@deepseek-ai/dsh-scope/LICENSE": "ebb4f09972aee8608be255debaf78451a68e95c290f55c240dec2ecfa16ea6be",
		"node_modules/@deepseek-ai/dsh-scope/README.i18n.yaml": "7d4492b76760378adf6b0c6e609ceca12a8ff6a074588c3c045cd33dd27b88fd",
		"node_modules/@deepseek-ai/dsh-scope/README.md": "a78f5ea99004e168a32e096b06d45c661736828c414123eba7f6104b55d64280",
		"node_modules/@deepseek-ai/dsh-scope/README.zh.md": "78012222db4f96c7b5b7446964d31745d5dcd32ab844c9af3a832cb8db9a0288",
		"node_modules/@deepseek-ai/dsh-scope/lib/index.js": "2829df71d76e08941457d4dd173eac60783e55354921137c8b75e8b5c0d2ecca",
		"node_modules/@deepseek-ai/dsh-scope/package.json": "560c62665b447f7bea0dc941231bbbe1408b095e9e86ce74062331f53a4895ac",
		"node_modules/@deepseek-ai/dsh-skill/LICENSE": "ebb4f09972aee8608be255debaf78451a68e95c290f55c240dec2ecfa16ea6be",
		"node_modules/@deepseek-ai/dsh-skill/README.i18n.yaml": "bbb855d83fff1eb3ecb5fdde7fde20e37c7af6e70c9a2952a30eefec83072144",
		"node_modules/@deepseek-ai/dsh-skill/README.md": "6717d6df2c778e4a1ba07afee30206f3a0f3c414e5f49725d755ab7ced9995bb",
		"node_modules/@deepseek-ai/dsh-skill/README.zh.md": "535cb17423807ad24fb1086aa0fa14374b196b9ebc48ab208475d0f52fc67a52",
		"node_modules/@deepseek-ai/dsh-skill/lib/index.js": "4b88621be4e7ff09b05c175fc6dcb67e77a22e5c5570e3aa603338b2937ea791",
		"node_modules/@deepseek-ai/dsh-skill/locale/en.json": "e1c7c827b300c0e91fa8ddb515854793261d4a100ac94b9558600008355cb4dc",
		"node_modules/@deepseek-ai/dsh-skill/locale/zh.json": "6b5a886c8434e2263d2b3166079df0120a465c11073eaa2824cf1e039dc65cf4",
		"node_modules/@deepseek-ai/dsh-skill/package.json": "74eef3a872ad31f83117f0562d940c59f67494b38a067079024e2bf70f0553f6",
		"node_modules/@deepseek-ai/dsh-subprocess/LICENSE": "ebb4f09972aee8608be255debaf78451a68e95c290f55c240dec2ecfa16ea6be",
		"node_modules/@deepseek-ai/dsh-subprocess/README.i18n.yaml": "bb932b67899e1f59d10e9138b606885faae7f4a9cb8c3d8d09172be6f3a662d4",
		"node_modules/@deepseek-ai/dsh-subprocess/README.md": "c25fd60d16fc4101855afe6d9b1c7ba39d07e21171987f02e82f5995c2dcf344",
		"node_modules/@deepseek-ai/dsh-subprocess/README.zh.md": "8841479aef5119a9776772eea7151b35dcbcc622aa7e39dcac332e3994691b8c",
		"node_modules/@deepseek-ai/dsh-subprocess/lib/control.js": "4afd0f7d7a7054b6fc8d727ea3f76731a78c9a972ddb6d5d2eef81cac4ffee3a",
		"node_modules/@deepseek-ai/dsh-subprocess/lib/index.js": "0ea9e95a73639f9e69b48aa48f373f34881adffa2ee2ac2acd4702728da9592b",
		"node_modules/@deepseek-ai/dsh-subprocess/package.json": "0a0ec0c96f8619681939bdd3cca22d5971d80a5594634e397f04678296936c9a",
		"node_modules/@deepseek-ai/dsh-util-values/LICENSE": "ebb4f09972aee8608be255debaf78451a68e95c290f55c240dec2ecfa16ea6be",
		"node_modules/@deepseek-ai/dsh-util-values/README.i18n.yaml": "930f4c21c65c91db734255d91a68fe2c22ef5509dd1f529e81f51f99af8dff03",
		"node_modules/@deepseek-ai/dsh-util-values/README.md": "724407eaec88db29a1d65ba411202f2545f57f08964a0f23eb191c6d260abbfe",
		"node_modules/@deepseek-ai/dsh-util-values/README.zh.md": "13cead4cc0a76a098c45d7a17d7825f75f1513a1ed453f0b9e260a9934ed2b33",
		"node_modules/@deepseek-ai/dsh-util-values/lib/index.js": "4322a2aacdfe38476d2bbc62338120beea1e1660346d7db5b6c1e1f927a26b7c",
		"node_modules/@deepseek-ai/dsh-util-values/package.json": "9d3fc5d25c5f5449a6188067204fef7e23c94326681ef4480377dfcdb832cfa8",
		"node_modules/@deepseek-ai/dsh-win32-process/LICENSE": "ebb4f09972aee8608be255debaf78451a68e95c290f55c240dec2ecfa16ea6be",
		"node_modules/@deepseek-ai/dsh-win32-process/README.i18n.yaml": "495793106a799f896540069cef7ca2b309f2d768c394ffc056fe7b3de80b516e",
		"node_modules/@deepseek-ai/dsh-win32-process/README.md": "52a5a71f80fc3468c38b4114df112d0f4e9044db5094dcb6f0262e41dbf220dd",
		"node_modules/@deepseek-ai/dsh-win32-process/README.zh.md": "7236ec5165c345c1e55abeea5a795dd93d067c14bdd6e97a4450a4b9ade99c63",
		"node_modules/@deepseek-ai/dsh-win32-process/lib/index.js": "622bc3a9e97c46e784fe41c9a0a8535da2808019e4ac3f66d17cdad70c9ac0c9",
		"node_modules/@deepseek-ai/dsh-win32-process/package.json": "44fc05024aa240124c8f2cf46c8fd8bbdcdce4120394ea510292586aaa8f050f",
		"node_modules/@deepseek-ai/schemastery/LICENSE": "034fb52b1d57360ecbae6cb1632a88f86fd7c3d3f5631a5f082710203dda0be7",
		"node_modules/@deepseek-ai/schemastery/README.md": "cdd54eece79b14c3672dfe94abb38b8d01c6ced57fb9975c4147fa17f81512d4",
		"node_modules/@deepseek-ai/schemastery/lib/index.cjs": "aca1c1a47c7b6034feee01501aefca3e6dd97a0bac4fe334fd30647ae5a9e480",
		"node_modules/@deepseek-ai/schemastery/lib/index.mjs": "cfcbe46c7416bdb35ce891c252152bbf519e08199bede5930dd7cb880c65f1ef",
		"node_modules/@deepseek-ai/schemastery/package.json": "3e7deee09015c7f7aa17ae6cecfb928985520baec66aa676dc3f4ed67d4231f0",
		"node_modules/@deepseek-ai/schemastery/src/index.ts": "a6647b515659cf439b701fa9f9574c9c310ce3872d26a13a81e9fa4d02ba10ad",
		"node_modules/@koromix/koffi-win32-x64/README.md": "4fc87635ba2ce995d9f91401e96c68dd0600ca3db25dae419a9abc4e8e11fcd0",
		"node_modules/@koromix/koffi-win32-x64/index.js": "632ab5a01dfc1b519b06275f490d6790100a2f8d71d8f56957091d0fcc5b3e0b",
		"node_modules/@koromix/koffi-win32-x64/package.json": "b38fcff8641d493656ef4153a37fd7389806ae621bb916aca536fd3bbc158690",
		"node_modules/@koromix/koffi-win32-x64/win32_x64/koffi.node": "b52ef88cf5e5926a09e5ed32e02a00f039b34d42501fc00e4344e84d93f994af",
		"node_modules/koffi/CHANGELOG.md": "a306af803dde65098fa651c713450c18bbaf5fbff3e09811d1e16d86a569e487",
		"node_modules/koffi/LICENSE.txt": "22bcbbbacd739b026a8dc484f62a31484ce4c4e31f3408b60b29b4e41d62b290",
		"node_modules/koffi/README.md": "f6ca5fa22abb0a8740fc40789ec161d46373eab1867a7e4d72fbe34f0d709b80",
		"node_modules/koffi/cnoke.cjs": "d0547e34c211e4c01914418b514bba0f141359324fe1369734660bd75f7ffafc",
		"node_modules/koffi/doc/benchmarks.md": "05f1b7b394380125a3d66b7bc05101f21980d8d78cf5c554d6e2c7f29120f5d8",
		"node_modules/koffi/doc/callbacks.md": "f1e3f14a1d84a5b6d6d7d6d3015a9859043f4d3773b932d361bc49f08a240284",
		"node_modules/koffi/doc/composites.md": "7160ecf9e4796d172de3e62cadf7759a299ec94515b3e6993a494ca50b70f389",
		"node_modules/koffi/doc/contribute.md": "72cecf31345e1d4e46d564bc4aa5020c5a445968cc2a818b337bf3a1019a4cbe",
		"node_modules/koffi/doc/index.md": "c996303cff3c3665b85f88f1f2ffdb67390077c14546eabf9d78ed3cf443e412",
		"node_modules/koffi/doc/load.md": "7b9d19a90f00c1cc47537ac65742e577fad22ec2fd18d400d4485fe4e00022c4",
		"node_modules/koffi/doc/migration.md": "b5b4d49ed4658000c6d406b6975c5a7eacce42f1ad3f94e936e1339890381bd3",
		"node_modules/koffi/doc/misc.md": "df10e522dd8c9512c949073d243cb9cff4dceaea69139c98c773ababb067f4c3",
		"node_modules/koffi/doc/output.md": "78a692be2e23954ad024345806b2d4937a45113be6c48cfc2fdd53dc49c32580",
		"node_modules/koffi/doc/pointers.md": "628890dec2cbe8304e006effaaead83e36d5e6b3695f3b7bf7e8add1d26f513c",
		"node_modules/koffi/doc/primitives.md": "3b4cab3721ecd6cad4ccc0ba251f9edae24e3b03bb94ac22234b5c8718a7f346",
		"node_modules/koffi/doc/start.md": "95c57729bd5b4477e39a8950fd4f1e6c8121cf5fba58907d16f2c8d5bdf92b8d",
		"node_modules/koffi/doc/types.md": "d8a1acfcc5f416038f05b6f53a93445e80cba70755592d6ceaf5b9df9b3c5440",
		"node_modules/koffi/doc/unions.md": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
		"node_modules/koffi/doc/values.md": "f712dc80674c1711b76edc64b1a55c06e5003e17b542afe071bc20cdfed161ba",
		"node_modules/koffi/index.cjs": "a200e15ec168d00cb3155794808a98243051c61dd7f6989c23c57ee220c918b9",
		"node_modules/koffi/index.js": "34508972d2e18b79fd4a289943568a68bbaf18badd2e82a25c8deb1af27f6225",
		"node_modules/koffi/indirect.cjs": "f36c7fd3caa9c43da3db45e1ee272892087b4001b6f575fffb76dd80574829b1",
		"node_modules/koffi/indirect.js": "5c5045c5b5ec2083535efdfdbd95f5212545ce29a4b7f33a683504a35e5b6a02",
		"node_modules/koffi/lib/native/base/base.cc": "b0fde2f2e68158cc496392a63ae3b84d88eac798ac0713f8acd1f897d936791f",
		"node_modules/koffi/lib/native/base/base.hh": "4da7737d98bdc8a0e85127d2b7b20c709b60aaf62975bada7c2b01e514c3ff33",
		"node_modules/koffi/lib/native/base/unicode.inc": "a337b5e53a6c72534fcf093c58d7fbf12f7b1075f068ea83a09c91e34373b5a4",
		"node_modules/koffi/package.json": "40285e315bc5b9b1d62aaaf9d6d76fb26456d12a75f3f136b9d230cfd36dad73",
		"node_modules/koffi/src/koffi/CMakeLists.txt": "99270ec05125659937f582c8bd4c2fc095fcc1a02b69bcbbebd7c6608a983749",
		"node_modules/koffi/src/koffi/index.cjs": "cfd8708a7016740afb0e9f0a1c669485ccf8be98e3f2ef0fd6a4be76f4986f03",
		"node_modules/koffi/src/koffi/index.js": "9c5a1590ca8ee32166477477b2639a55e91273674fa6d86da259d383918cd087",
		"node_modules/koffi/src/koffi/indirect.cjs": "379433ba1c4e79a90e6e599cf8d6ebe9f9a85fc272a635356f2cca62a93cc96c",
		"node_modules/koffi/src/koffi/indirect.js": "8d0f04482f762b6b460ec0f89f72dde9eff932a773ce71d43df0551c36fd2c80",
		"node_modules/koffi/src/koffi/src/abi/arm64.cc": "7c017aa1dbf8cfe1d89062a2244966cafab9ec2c2c832877966af6f5bdc5fa0a",
		"node_modules/koffi/src/koffi/src/abi/arm64_asm.S": "9ef4d4095faddda9e5807137cbfbf40908ec2b373e6f0e2e3ee70e7b919d37b4",
		"node_modules/koffi/src/koffi/src/abi/arm64_asm.asm": "58053bbdc192f2191fceaba048798d9862f2fffbca992cd09ad1bbed8c61d4d2",
		"node_modules/koffi/src/koffi/src/abi/loong64.cc": "dc53190f98c24d8f909358f23a20ce861d58124a232e87e8e2aeb3566ae02088",
		"node_modules/koffi/src/koffi/src/abi/loong64_asm.S": "5df3967e737eadd1509812e76b6ce4dcbfd8672797158a3fc37ac5f3755d14de",
		"node_modules/koffi/src/koffi/src/abi/riscv64.cc": "11a039d84a5f160fa7ebfeda4411904dcf36ce416aa0f0da79a0e5ef593408a7",
		"node_modules/koffi/src/koffi/src/abi/riscv64_asm.S": "46f910cc423ca39305b19a38db13a1480061735258f189ee631237ea13fd2ba7",
		"node_modules/koffi/src/koffi/src/abi/x64sysv.cc": "9b0d0128b739f9fc6761b8d00ddc075be385f8542bb24bfaddc67152b8642251",
		"node_modules/koffi/src/koffi/src/abi/x64sysv_asm.S": "822fc8d707b9e7ffd4fb4899d9d7bad2b2ee732f9e3203b9fcd367e750e2a08f",
		"node_modules/koffi/src/koffi/src/abi/x64win.cc": "f92cbee859064c255be527ee826457d8e29cc5b47a3269f213cf73ecd28b4ff6",
		"node_modules/koffi/src/koffi/src/abi/x64win_asm.S": "dcfd393d8605f97064e69fa31f2d533e2f62f1e0d378a85be7251952c679f9fe",
		"node_modules/koffi/src/koffi/src/abi/x64win_asm.asm": "227e656e5099b48550cee7f16efa9a2dfe2c58f3c46ae71e2f1ab9d80146ead0",
		"node_modules/koffi/src/koffi/src/abi/x86.cc": "9cb692230e073c56857b16f05b2237854b35df5b66897d7066475324fb710d48",
		"node_modules/koffi/src/koffi/src/abi/x86_asm.S": "d073e326858e5475575b66088a67f495b6fe26011e027b8ee86e4377872be25d",
		"node_modules/koffi/src/koffi/src/abi/x86_asm.asm": "3e59a94cb4ee78165f0545a68ce6c397103a106516fb7fe0c2f1e46471315767",
		"node_modules/koffi/src/koffi/src/call.cc": "e6eb347b2c2444f932daa4f00624421722edea94ac0cb9c1119c5daae12d373c",
		"node_modules/koffi/src/koffi/src/call.hh": "b202e8daad46c6734f9b566394179e53aded86983a4f0fe31ac0d8797f7ac1dd",
		"node_modules/koffi/src/koffi/src/errno.inc": "f2fea4a329fbf7aa7e5a6c52daacc480d70d782344e37fd7e62019f6b914201a",
		"node_modules/koffi/src/koffi/src/ffi.cc": "7da0f340eaa0aad0a09e67fe054a65c8ee05bacdcf6d9d015bfed5289013fd99",
		"node_modules/koffi/src/koffi/src/ffi.hh": "3ca1bb69f226dca6a992c434581ca7b4684635cb5c9d42a6345dbbc2e5d43879",
		"node_modules/koffi/src/koffi/src/parser.cc": "fdb030e06ffd83d3e5e0a1c037ad669c2e7d2fde8a831da1f35cd53df623adb1",
		"node_modules/koffi/src/koffi/src/parser.hh": "cfd9e374884cdc0f60716de41bbe110d361bc10d0a8539942e37d34c86b525ae",
		"node_modules/koffi/src/koffi/src/primitives.inc": "34f524982a6e921a63c6766619b337b6d15f0a5cdefbf252481dda4b4369afda",
		"node_modules/koffi/src/koffi/src/static.cjs": "25dff303c876cfdb531e2d9590ecbbb4928c8e60453c484faad66b2a3abd1556",
		"node_modules/koffi/src/koffi/src/static.js": "3f2b291e2129181c2984e6508b51efa5be30775afbdbafe6c0f4ed076d80d9d1",
		"node_modules/koffi/src/koffi/src/trampolines.cjs": "82895e2a78b911b297e7497d9d6033ab87a0afe64f4904615dacfa318d83adfa",
		"node_modules/koffi/src/koffi/src/type.cc": "b6ff93584362e61a73314b81fe468eb35985d28587461ff4a7ba19fdd8ab6f34",
		"node_modules/koffi/src/koffi/src/type.hh": "691479b990ddf7364c5f316d0a653d32f13181c1f5f68ad55d1db3ccb58f9b24",
		"node_modules/koffi/src/koffi/src/util.cc": "ab92522bf324140f3fe9e3032c3cb6770412d743b06746675afe7fe49716ba50",
		"node_modules/koffi/src/koffi/src/util.hh": "4aab905947a127652107e20016880d2d34ae46e3290705d8a485e01abd864360",
		"node_modules/koffi/src/koffi/src/uv.cc": "1da9e82cef92232daa4090415c66fba6c3584ee901550cc83978e363dcdd5c7c",
		"node_modules/koffi/src/koffi/src/uv.def": "4a40dc700dc66214fc1c464db8c4b78b82845e3b7b4e6103418ac519346ca4d2",
		"node_modules/koffi/src/koffi/src/uv.hh": "6ad3aeceec4070cbf5fe1f9e54a75b58dc57c2686174c654b341ff9215d70aca",
		"node_modules/koffi/src/koffi/src/win32.cc": "3bfa4a499afd5b1933882d09004f6168bb3ccf25ac0e42ce321d12dae67d8d6f",
		"node_modules/koffi/src/koffi/src/win32.hh": "eeec401597da546109b9729113ccb635c61db325f2d394f883c2293955f119a5",
		"node_modules/koffi/vendor/node-addon-api/LICENSE.md": "89024017b88a9f2b763f79b941a4f2db3b4428edfcacdc0b23866b2da633ad0c",
		"node_modules/koffi/vendor/node-addon-api/README.md": "fa7f9a510c5dc46161e8216dae94e3857e466d7552059baed3b6fb36874a14ad",
		"node_modules/koffi/vendor/node-addon-api/napi-inl.deprecated.h": "b66ed1e565e735bbfabcc2f72d466ab7c5414d3ef8851d1af440b81be7f2375c",
		"node_modules/koffi/vendor/node-addon-api/napi-inl.h": "384d2f7934e898e324560443a0cb76f6c1cfa086f0f6fdfdc643396177025bd1",
		"node_modules/koffi/vendor/node-addon-api/napi.h": "5b41d4d85e183e5c69b0e5dab5801dc1fb00fb72579f9b278bb7f70d412d8d38",
		"node_modules/koffi/vendor/node-api-headers/LICENSE": "a553508f516031c91f3af1148d44970cb81bbae6c4f091be6835d39cc252238c",
		"node_modules/koffi/vendor/node-api-headers/README.md": "63a4e81d19f02b164d51c4721ff3e88c81d410640de7e1d3520a2c406f0a7d83",
		"node_modules/koffi/vendor/node-api-headers/def/js_native_api.def": "77653a554fbb27f6c5666f4ba05f87d26f0de72bc3d0439961ac030030c2be66",
		"node_modules/koffi/vendor/node-api-headers/def/node_api.def": "e0d5e3da0520a42e26b563f6321291081bd15bdd20821d46818e5f47900f77d6",
		"node_modules/koffi/vendor/node-api-headers/include/js_native_api.h": "0953395662ea63697cd7a77a9320d94aa2829f9c9569abf3a74272b7a2923ce8",
		"node_modules/koffi/vendor/node-api-headers/include/js_native_api_types.h": "21eebde05d2ee59d315ac27d4aa82434ca88508a0b2cf5819802a00ca523831d",
		"node_modules/koffi/vendor/node-api-headers/include/node_api.h": "2d4560831e525b47b060ec8a0864ab73993df9e20215ce9f0fe7b24cd31af32a",
		"node_modules/koffi/vendor/node-api-headers/include/node_api_types.h": "a25356630d3058f0a0c8937d9f297e9471e037fda58c2696d8a505c2bd99cb00",
		"node_modules/node-addon-native-custom-loader/LICENSE": "75bd0a6d6b9f9f0a6c792ca89832360b19749ebe16af0222e34387f262baa95e",
		"node_modules/node-addon-native-custom-loader/README.md": "b825cee1efe6c18d38e434b9f72e5300ac29770d172eac1a5ce437358a96ba7f",
		"node_modules/node-addon-native-custom-loader/lib/index.js": "6d83f4e5426895d40820acf507146226a893c5aefba00a08bf0884446160049e",
		"node_modules/node-addon-native-custom-loader/package.json": "9ea26b5a9f3bc05fd4b0cdac638c152c30a3e5022696aa52020379f4eec6a398",
		"node_modules/node-addon-require-builtin/LICENSE": "75bd0a6d6b9f9f0a6c792ca89832360b19749ebe16af0222e34387f262baa95e",
		"node_modules/node-addon-require-builtin/README.md": "f4df420fb3ff53efab2b5ee3ab093d8a4344ff34063688eb306d611ad9a5e07a",
		"node_modules/node-addon-require-builtin/lib/index.js": "73966bb0f824b021f77b03f02e00905a532554aad3c6c5a14c2a743aeb4a34a9",
		"node_modules/node-addon-require-builtin/package.json": "a86eb361a884a2a0df00b81c4b21aec35ecfc5ccc43d0e9d289f6f44d7e9df2c",
		"node_modules/undici/LICENSE": "a6db8096b2707bc0102d256917d4d33f298ba36d8c3f25de067a2b5bb379db27",
		"node_modules/undici/README.md": "8d5fe4e7eecd5ea257ee637c131f228400649d3a8d2024555291237f46009872",
		"node_modules/undici/docs/docs/api/Agent.md": "d7528c0c1d3382e00599b22c53d63602299721ea6b0215767e5af4e03a4498b0",
		"node_modules/undici/docs/docs/api/BalancedPool.md": "639f6db33b169e444cde10f62a616e6b12cf68e94c4b3c5fedaa20aba095278a",
		"node_modules/undici/docs/docs/api/CacheStorage.md": "785b0a4fc5bf3f45c6289082f7bd2ed48d0e12212387ff67842c73ad7eff0633",
		"node_modules/undici/docs/docs/api/CacheStore.md": "df9e089c6ad493faf5bc9428fcd6302a8e5a644987b7b269ace5c299a98d1488",
		"node_modules/undici/docs/docs/api/Client.md": "65804161e424ed7b1506ab70a84e23331db8223001250f3059536ae13f17f2ec",
		"node_modules/undici/docs/docs/api/ClientStats.md": "643275cb1cf0414421fec969f797f8bcd2fb59d999e6657d265eab20f346ecfd",
		"node_modules/undici/docs/docs/api/Connector.md": "dbabff331d240ca9d674a720b86c044c90eef723a55fc3428f06cdc4b5452bff",
		"node_modules/undici/docs/docs/api/ContentType.md": "cbec09f61555173549ac806f6db263862c27e6530243fba7560b22e7747f9cde",
		"node_modules/undici/docs/docs/api/Cookies.md": "79462fdcc010075e5cd65a733aeec6225abbad4dd80469af26512f86acacd01f",
		"node_modules/undici/docs/docs/api/Debug.md": "4763197faf32b45265ca8f89b7686549410988aff2565d35057d379f62598255",
		"node_modules/undici/docs/docs/api/DiagnosticsChannel.md": "1f0468622e31bf79cdf20bcb8b2aa0771fd984eaaff710080b3ccf3093983483",
		"node_modules/undici/docs/docs/api/Dispatcher.md": "b341a990e4637689d2ab3affdafcdb4e66dcfccd2b82ec17ea39d934360fc30c",
		"node_modules/undici/docs/docs/api/EnvHttpProxyAgent.md": "44a69d50d50489dd1dc91c27446eac34b3dedbaed239dd8c49ccea00f1a402a3",
		"node_modules/undici/docs/docs/api/Errors.md": "0421b5c6ddbf89f14130966ed7f146320de7d4daf3e6df57d0fc45d601ed7fd3",
		"node_modules/undici/docs/docs/api/EventSource.md": "e4e9a1dffdc615332b5d25ca06e9f47e0e37f8313e640195440e81fd96117eb4",
		"node_modules/undici/docs/docs/api/Fetch.md": "3d0bddce408e3e30cd2b457d0728c2cb2929c9789aa81387eaae23f485f1a66d",
		"node_modules/undici/docs/docs/api/GlobalInstallation.md": "e38431026afde90f00c0d1492352bad46146b1b77f1d0dddf63c911039cae0b5",
		"node_modules/undici/docs/docs/api/H2CClient.md": "4c60bd41d43b7a298f5fac6d201a329d905bfaa639ed907ec800f1a47cb2713e",
		"node_modules/undici/docs/docs/api/Interceptors.md": "424f203619268944f6b94d3f4024f7067374a9fd0d7d69f32a2959bd0daabcbc",
		"node_modules/undici/docs/docs/api/MockAgent.md": "1a7000a273d8acddda3259ea0f926d77b709b7fc22075b764f89925c80e13963",
		"node_modules/undici/docs/docs/api/MockCallHistory.md": "be3a960e9146fbeb2319e913704f3161f3fcbe93e69ec6df0f597326f4505eef",
		"node_modules/undici/docs/docs/api/MockCallHistoryLog.md": "2a3ee870f741a0cfde4e18d14e6f9b4778ce72c3d79ab3dbbc2e55586a27e3ce",
		"node_modules/undici/docs/docs/api/MockClient.md": "a6dbb502a5a8bcdb359bc28509c8f001829fe40fd8419a5bf83cc5f2cf2c8646",
		"node_modules/undici/docs/docs/api/MockErrors.md": "7fb801dce6663e87fd87aa603af76ae3b4301bebcbfc607309742747908485d0",
		"node_modules/undici/docs/docs/api/MockPool.md": "6f5052224d7eacf0e24bae965f70df2138ba296551471891c4120b1850e9f0fb",
		"node_modules/undici/docs/docs/api/Pool.md": "1fe65246bf6716bead816a18cb04cb750ed5041d667324dc763d078b02d5b942",
		"node_modules/undici/docs/docs/api/PoolStats.md": "a656458a5940be068c66501d4f1dcc57b04063ac54c6d040a37dd6f3140d9e87",
		"node_modules/undici/docs/docs/api/ProxyAgent.md": "69db88244d7ac5bc01702b4196b1f908ec2215c41700671b4ae894a70817179b",
		"node_modules/undici/docs/docs/api/RedirectHandler.md": "63ca7a1a77f4c053715f5cc9860ff8a22cb65584d2479366b37f9aadee269c26",
		"node_modules/undici/docs/docs/api/RetryAgent.md": "783fad6b66a83b1cb31705772d389f97ed206a9c50d51cf03c57f707ca44ee13",
		"node_modules/undici/docs/docs/api/RetryHandler.md": "4f5a873ff4d4d5c48fe15092032a8e2aa45c86709871403de2afb534ab3943b5",
		"node_modules/undici/docs/docs/api/RoundRobinPool.md": "cc3c17338c746b7906b005160ed2abac7467c8b111956df4b3e213a560ae55ff",
		"node_modules/undici/docs/docs/api/SnapshotAgent.md": "0f2e8d6dbacca62b21d17fa3cf7d77afd6405ebdb5c25775c3e354029db07bc8",
		"node_modules/undici/docs/docs/api/Socks5ProxyAgent.md": "c9518591d0df4f741e0509383941f6bc3d8f53afda2e16eca64cb8eb3aac2b21",
		"node_modules/undici/docs/docs/api/Util.md": "eec121fd18ea3fed31a29eb2fb63efe75d0fcd7cefb4b620b787a2fd06fd4d67",
		"node_modules/undici/docs/docs/api/WebSocket.md": "932247f397b249201d7681c3965d28ce4bc80c15c3db8ede7423036b6256bbb7",
		"node_modules/undici/docs/docs/api/api-lifecycle.md": "d76f8c11596a813b595aaec24b07a7fc78c25b8e4322ea2db8695ffdcdc1673c",
		"node_modules/undici/docs/docs/best-practices/client-certificate.md": "3ded48c955cf868c99713f8a91a2cdf29192a85861ea372d4bfd7451b26d17e8",
		"node_modules/undici/docs/docs/best-practices/crawling.md": "6f569b129afcf3bcddd45b6e1a2b4179b310c0b103a9ab98fa07dcbd7161b8b6",
		"node_modules/undici/docs/docs/best-practices/migrating-from-v7-to-v8.md": "93b875fc847ee4dacdc7d7a36a8e1048ebb781e862098e7b9f31293155baa65e",
		"node_modules/undici/docs/docs/best-practices/mocking-request.md": "e3d94539e9c27fe2bd7bae15e93a429ee6b1d7467f921145f51730f3f6205b98",
		"node_modules/undici/docs/docs/best-practices/proxy.md": "256883541f6a7c784d4e87b8b5c5694ce47144612aed44c08627d0e1c17c2467",
		"node_modules/undici/docs/docs/best-practices/undici-vs-builtin-fetch.md": "86a1b8931d91f560ba4f9a2b55c5a3b931a6b5db2f2a51f4be42b17bb466028d",
		"node_modules/undici/docs/docs/best-practices/writing-tests.md": "1ff22158dfce7ebb5266eee14ddebec402287762c15e0a568ff7bbade4881c57",
		"node_modules/undici/docs/docs/getting-started.md": "5b68a83303f9c5315a40f007d8bf9536673826efd1047bc9aad95c1b27fcbcad",
		"node_modules/undici/docs/docs/index.md": "97f659475af39ff4666e3ca719fc173b595ee11302cb9385c38b1f331d3fd6b2",
		"node_modules/undici/docs/docs/site.json": "23b8d0999e92ec9480878c9aae6850f99bde88a546bf8d6054a952dde1fe18b4",
		"node_modules/undici/docs/docs/type-map.json": "6977d0239d1d7fad8186261ae277ebec62e2e9d7e46c56eb1a211772dd0adc7a",
		"node_modules/undici/index-fetch.js": "155df504376841f714239ffbb43c7fbbfe3532c44aafe19ca7fd1615a18d5f1d",
		"node_modules/undici/index.js": "93fc85c00a59b58f410c901e5477d56770de3816bfbe183e751624aeb4a5e6a5",
		"node_modules/undici/lib/api/abort-signal.js": "46ac3527affb69036384c8baec5bf34ba567adb336921c7a62e8f471bb827f37",
		"node_modules/undici/lib/api/api-connect.js": "4209dffaed12c9f000aa2bc554c70cc0cc5ea984869152422370a61bfbb1badc",
		"node_modules/undici/lib/api/api-pipeline.js": "5ad0c146a9d88c5087802df087901aa08a98e28d1ad600c33ee5601f699fbbcd",
		"node_modules/undici/lib/api/api-request.js": "f655a12aab11d2463cd947eff9b483fdaa22992a607b3c733479535c4ce6e662",
		"node_modules/undici/lib/api/api-stream.js": "1fe980698a643db9f228137c46fe07751bdd021bc5a1feafae88c51cc107d356",
		"node_modules/undici/lib/api/api-upgrade.js": "0c51297099a626e47163a7fbc56f01f1a895dc7914e8d91ea0885a9c7634a09a",
		"node_modules/undici/lib/api/index.js": "a7b4b74ea6b81b2401f8659c138df54fd3f2c45450741682c026abb4cf133096",
		"node_modules/undici/lib/api/readable.js": "35b6fc8cd20796a0b21944d68c09a86b209ffa7db9e3613626d28867c9166d45",
		"node_modules/undici/lib/cache/memory-cache-store.js": "b87fafa563690bb4ab6a7a50a5a040d3c6ef8a99ea65ea1ed16a544b1a6caf72",
		"node_modules/undici/lib/cache/sqlite-cache-store.js": "389b37a214dce9353079be0e0d7c7925ce981888f3646b1dc48bfe0c31d7e64d",
		"node_modules/undici/lib/core/connect.js": "4bf7ce84d6d31ffacebb0130164d50e619645b79cf6c4221ac374ab5ada677e3",
		"node_modules/undici/lib/core/constants.js": "a9c9c59d69a6db90fd3fdf46ebce943cbdc5da6e2acd143a00ed3282a8c65ca0",
		"node_modules/undici/lib/core/diagnostics.js": "907ce2d66cede91b860a1c1318ebdf0d9577c0f747a3b35510162c63489f28bc",
		"node_modules/undici/lib/core/errors.js": "47c1e438402a802f5132da4a2084e1294ad3fd1496f8f7b47117292165c17fd9",
		"node_modules/undici/lib/core/request.js": "ef5b4b9d34dde2ac2df21249228cd4d75f19f6c301307a84fda36fbd4bdee724",
		"node_modules/undici/lib/core/socks5-client.js": "5ee3d782919a74b4c0fc0aac0da1d39abd759f7c017f7b3d4b932ccafddd1be7",
		"node_modules/undici/lib/core/socks5-utils.js": "830467b148e86786f41c356667625721dfd9bef27fd85ada0fb498bda9a19016",
		"node_modules/undici/lib/core/symbols.js": "2fbebeafbc65374261b6cc10146a3cdc0083342a125b7e957afe2ecb4a4c41d0",
		"node_modules/undici/lib/core/tree.js": "c9fc9938718f33d77a6ed1abac5e564531ac9f9436cde2867243d50cd6c0b4e8",
		"node_modules/undici/lib/core/util.js": "cb110920638fb3e418a8e4ffc55b5e18a220e6bc08e2a0f6d8174029292cd8a2",
		"node_modules/undici/lib/dispatcher/agent.js": "b54f75ea0978a432484110017bb2eb4768c61d4bc68b3726d6f7f2399eb14649",
		"node_modules/undici/lib/dispatcher/balanced-pool.js": "0cb69083f49eb392baf0ce5e88dec9b610cfca47d03e12d5ca66ecf90d4cc5b0",
		"node_modules/undici/lib/dispatcher/client-h1.js": "e8eb930546e7f7755471c75069878e3584b50f2c9ec8468fc8f2a1d236dab9a4",
		"node_modules/undici/lib/dispatcher/client-h2.js": "2f848e5316242e9babf3f9fa81657e0b2b3f58b081b6c41585b19f536c3a9435",
		"node_modules/undici/lib/dispatcher/client.js": "05061b7d9f484d7db7894f9b5b1f9585f40af6a7eb26694a2b762084ffe2b461",
		"node_modules/undici/lib/dispatcher/dispatcher-base.js": "2796a3361c387a89abaf621b6666c1ea2b9ac808abff664fc5eb70539d19c989",
		"node_modules/undici/lib/dispatcher/dispatcher.js": "032235d0e70df874f87ea4df892b7404b0dbffd65a08b0720b99eed71c79635c",
		"node_modules/undici/lib/dispatcher/dispatcher1-wrapper.js": "9c4d64198b782a38f98fd8054eabc150694c791038a52e454da4cc1780d7d8e0",
		"node_modules/undici/lib/dispatcher/env-http-proxy-agent.js": "8d8eb0e7a71c9cd15498034188cd953887f85123d4c41041b077dd0b3941a6bb",
		"node_modules/undici/lib/dispatcher/fixed-queue.js": "5d72c9de20e74d2437afc97f9f9e8e202d79983a77d2a598ac9ab1e0a8d0052d",
		"node_modules/undici/lib/dispatcher/h2c-client.js": "898ffa9f31dc54f563192ef8f0d9dbdd28e8834034b5d034cafee3775af2b894",
		"node_modules/undici/lib/dispatcher/pool-base.js": "23792e58781239dee97bae8a849d14b1181836a6415c41fb9235ee23bd61dc44",
		"node_modules/undici/lib/dispatcher/pool.js": "a92d0f6144cc553357b1a18f47ffb6f6c850e43622dddda71dcad71cf0430393",
		"node_modules/undici/lib/dispatcher/proxy-agent.js": "63920d0209b6f69a874cabfa383084c2db537e88f1932b7c593132cacf0cd9bf",
		"node_modules/undici/lib/dispatcher/retry-agent.js": "1c3100b5bf5c808631710f7168650e4895fcacca8a8a8bf55803480f172a3bc2",
		"node_modules/undici/lib/dispatcher/round-robin-pool.js": "77c5c15e9c68a274f6c00847a1bbe54b71476e0aa8618aac5ed629194e54685c",
		"node_modules/undici/lib/dispatcher/socks5-proxy-agent.js": "fa8a243c5b9eb4b5de4e73ddbefe63426afc8a02743830a4f1e2142767817578",
		"node_modules/undici/lib/encoding/index.js": "7ea8fe81ff3c9d054f3ef8bb67bfe260b2e930c51d5d5563ca2ef19a218a5909",
		"node_modules/undici/lib/global.js": "ad78c73866021cae34d47f7896561c56294e5c1f15915d6ef1780f763a816b9d",
		"node_modules/undici/lib/handler/cache-handler.js": "7de20ca8ef41db87c4d5d452def61e0546082b3285c178c61dafb11f2a3ceaaf",
		"node_modules/undici/lib/handler/cache-revalidation-handler.js": "4610b09696d9a8b0927d7b98980cb64d7b2140095c115daeed51a57a92a5fea3",
		"node_modules/undici/lib/handler/decorator-handler.js": "0958e75d0310651e5db468bd67e6351d97183403181be669625ca67c55862f54",
		"node_modules/undici/lib/handler/deduplication-handler.js": "9f8f7081af3f5e01ff03254dab41c531ecafc9e222284dad57fbf971a9f05ae6",
		"node_modules/undici/lib/handler/redirect-handler.js": "383d7755878d4009b1df8962c32e08c805f9c04a8c7d0f639ba9ca1673fb62a5",
		"node_modules/undici/lib/handler/retry-handler.js": "23ac4cde79d4063ff74fd159d2c9d4f454dc1f14bd7b3dfbd3489f547c9a7e7e",
		"node_modules/undici/lib/interceptor/cache.js": "1c4bf1b8e9c5dae9b3bfc6949a880ab3fb03f51ea49997fb6645a35140872170",
		"node_modules/undici/lib/interceptor/decompress.js": "b5a5a621f7c9f7a73ba87aa3e8c86cff83267d06587f0ea8fa472d39a1b99e59",
		"node_modules/undici/lib/interceptor/deduplicate.js": "852211f635105d819b63e1e5b1f6abdc9d5356a1c1b2ec6444c54a8f888163ce",
		"node_modules/undici/lib/interceptor/dns.js": "c5397eac5d7813c863e7a6af87a24bd9eda0d7244f84c3e044ac0322913aa557",
		"node_modules/undici/lib/interceptor/dump.js": "30d035bae71552ef4cd19b264728482abb9a7b5f82af47ffb9ad81e2541ea4bc",
		"node_modules/undici/lib/interceptor/redirect.js": "b0d5f6f590ac86bf7d5b20a93af0303aab1680c1b7796ff9c487550dc542a3b4",
		"node_modules/undici/lib/interceptor/response-error.js": "9cb06334d1c1f791784005789cc5afb9daea396c7f5e0c962af90538b4843e10",
		"node_modules/undici/lib/interceptor/retry.js": "488cf270ae143cc13a6ecf82ba523314fdbb17fd9ee08677c4488d4410f047c3",
		"node_modules/undici/lib/llhttp/constants.js": "90c4858736745781548d464e51224ce9353162cd87bc8142be803bc2937184ba",
		"node_modules/undici/lib/llhttp/llhttp-wasm.js": "5d8313d6fe8145d832e6af9959b2810523c9a6993d5b93cee09bd7e5f1f2c085",
		"node_modules/undici/lib/llhttp/llhttp_simd-wasm.js": "a3f30f3307ab3c191720cb636d570febb3610c420bc7077f2e225dacfcad3295",
		"node_modules/undici/lib/llhttp/utils.js": "e21afcaf44b0fec37acfff86945e4526541e990ac0efd2f1efa2ea9f2b259b6b",
		"node_modules/undici/lib/mock/mock-agent.js": "0554f474e0d717d578412f512eb4ae5d270540104b6942c1a86e0dfba4ae5ce4",
		"node_modules/undici/lib/mock/mock-call-history.js": "6ad1c52ab1e5fd692a161d7f91bac080d24a0e05f34cd0460cb5a6668105fa6e",
		"node_modules/undici/lib/mock/mock-client.js": "108d91ef5f916d094a78d92a4d81f2cd4bfe20708ae6307d8197de81d826ce5c",
		"node_modules/undici/lib/mock/mock-errors.js": "b5bd959401de99d8129ba272dddfdb62708247f684a8186aa4d858e2780d64ee",
		"node_modules/undici/lib/mock/mock-interceptor.js": "59f75321c62504d83f84e2702b8dfcd7dfda3d994b62d9d62273653ab790bad2",
		"node_modules/undici/lib/mock/mock-pool.js": "763d77ce68f6315f384b5e897b87ea2e2034b69d29e2d6d2da37ae8a0679197c",
		"node_modules/undici/lib/mock/mock-symbols.js": "b90b7dc21d5a18c2e5255b0916bf75e880eef32ca45ab312a581547041638e20",
		"node_modules/undici/lib/mock/mock-utils.js": "36c267a79b3d035cb2f50b6da508c850f131deb2ef1a99bfb26d1801faf5db58",
		"node_modules/undici/lib/mock/pending-interceptors-formatter.js": "9d3737f40ba601fd7a9c6dd28a328e6797686ff08da712dcd0a0f011d5639f8d",
		"node_modules/undici/lib/mock/snapshot-agent.js": "85acfaa63be0ebd8bf8c12b927ee1adffa585c5753a53cb6fa21f06413eb5cb0",
		"node_modules/undici/lib/mock/snapshot-recorder.js": "ec7ea35855aad0fd471fc7c7f03075bb7586613dd6b9ecd9de181882ccd33c54",
		"node_modules/undici/lib/mock/snapshot-utils.js": "0971c847787d90abcb0bf4e1d76161a2f82651169cc8e637b26875fecab666f8",
		"node_modules/undici/lib/util/cache.js": "0818df2477bcab9b9c05ce4d89eb08e821af54904bb753695ce266ef17db36ee",
		"node_modules/undici/lib/util/date.js": "153ad641cbdb4cc5acacc8b50b79684166e29b838192bf98b2d32e2871ff7522",
		"node_modules/undici/lib/util/runtime-features.js": "d2161d6b59141370f3bb92bd9d950ef8caad083f6bfea4566c44a157996957de",
		"node_modules/undici/lib/util/stats.js": "d62ae00eaf72f33cc990a3a835d70b9c7d2f10d47acffa0e631ea82145b7c34e",
		"node_modules/undici/lib/util/timers.js": "4e5ef13ce9e1ca6de8a656b95e2425602bacbd6010af1da3ce573f8d8f573119",
		"node_modules/undici/lib/web/cache/cache.js": "495792112d34bac4c6288592e4c30f8f4e4f22fed27939fcceb0c9c1f5d2b252",
		"node_modules/undici/lib/web/cache/cachestorage.js": "be102dc4454e52aa65403e9c94220b61e0edc1008ee7eea14f1267e1e13a14af",
		"node_modules/undici/lib/web/cache/util.js": "638d5c2424a730e6d2400ac518765b3fc9b50e2b3816b65fb7b46f93c66a5930",
		"node_modules/undici/lib/web/cookies/constants.js": "85a24ae49eb5954e15363049bbc68967f01aae7260246daa3f49ad375429acb4",
		"node_modules/undici/lib/web/cookies/index.js": "17957b8b7a7302cd084140595486f58ef5c6fb346a61d8872c432dcbbe3f8901",
		"node_modules/undici/lib/web/cookies/parse.js": "bf045e5cd5dcc90dd7a6c80ec351ddce1555acc223b0e8cc49e90f006f3ea21b",
		"node_modules/undici/lib/web/cookies/util.js": "7ff71ceb2e25c6f06055c120eb09be938b2bef7af8a65703baf25bac6b74477c",
		"node_modules/undici/lib/web/eventsource/eventsource-stream.js": "098a79aa4af46a8ddfd8583be35510b6824b8fc513023c5b2295b5f3be474fe2",
		"node_modules/undici/lib/web/eventsource/eventsource.js": "64c11485baf8e397e379b9f0b336eabdfd57d124a692b75bf0bd903561f98442",
		"node_modules/undici/lib/web/eventsource/util.js": "b1c5b993196a38edd99da36075db58a280486a77a3ce8dfd289358b3de85905c",
		"node_modules/undici/lib/web/fetch/LICENSE": "a21d6c8d3fc631198b97e57584697f7f9c37805c71c6cf9a12e4442b40394b88",
		"node_modules/undici/lib/web/fetch/body.js": "19c019e31d5b472fcbc2feb6944a4c585965f28ba1e82b981a23c3403a917f22",
		"node_modules/undici/lib/web/fetch/constants.js": "2e0f11d1ba87ce83219dff50325be48704931af5cd03a749fe710590bfd5bfb5",
		"node_modules/undici/lib/web/fetch/data-url.js": "9f820a24256840c477d8f0630f9fae813f826e7644355933bb8ab66a59058a34",
		"node_modules/undici/lib/web/fetch/formdata-parser.js": "d5d048201a040865a4376e423fd78b102ad164cb51ad7b0ade56897c7318bd6b",
		"node_modules/undici/lib/web/fetch/formdata.js": "f1bc0c3e92ac8639f632d2b79e5502165cdfb273725dba197ea692aedd8a44fa",
		"node_modules/undici/lib/web/fetch/global.js": "6b38813b82ec8d5002009640515d35f83ab96d4f8e0066d71fae89324079a289",
		"node_modules/undici/lib/web/fetch/headers.js": "1fc876d1484319421fc2c840d616c5a0fffbf12cb66e66ee44b8383356dbebbb",
		"node_modules/undici/lib/web/fetch/index.js": "8269824463f434e3e15c5aad090e03f19aefe9d27b40efad9d8ef7ed308d1d27",
		"node_modules/undici/lib/web/fetch/request.js": "63fb5c976978e2b0f23b1064888c4775f9889a28e2422e0b2e1daa123c4420ac",
		"node_modules/undici/lib/web/fetch/response.js": "851520e91226ecfc8421037b6c5a894c3b7a91013e9988d74a32f08cb3ae94ad",
		"node_modules/undici/lib/web/fetch/util.js": "54b66da9dcf0e52fe761700bc5008b4bd2cb7ffe4490f6634c59ce7208505b44",
		"node_modules/undici/lib/web/infra/index.js": "ea89dc494e2c8cce88882ec7e9514d8df2883dca71e54f42f9ca45ad8db12d52",
		"node_modules/undici/lib/web/subresource-integrity/Readme.md": "0d3da607c6e6d7420679c47e869bdc926266cc94d39fb243d9cd3f9a217986f8",
		"node_modules/undici/lib/web/subresource-integrity/subresource-integrity.js": "65997037f348e22746f0852037998ba64fb83e6428485c6e200d42da8a154a75",
		"node_modules/undici/lib/web/webidl/index.js": "a6aa001f3a56d521cbee0a925e3a9d057079b76f5d9ea527a977605edcb2f811",
		"node_modules/undici/lib/web/websocket/connection.js": "4000792883e7b2f301b2418e32599d47cd1e74df2677909dc1f8d32d583f4055",
		"node_modules/undici/lib/web/websocket/constants.js": "e7b6d0550a367ba9edfb68b14bd3fbe44fd3042faf76901567b8c3ffc2ccfa84",
		"node_modules/undici/lib/web/websocket/events.js": "53f342e0641488a92835546c0d006d128cb5931fa358e72c9f80c5532c225fb2",
		"node_modules/undici/lib/web/websocket/frame.js": "883d40c52b86f43619074911d81830d80f29cb605a4e01a128b196e2ab666d63",
		"node_modules/undici/lib/web/websocket/permessage-deflate.js": "da8d8dc29515bce2ba4def5c3f811f8644eeb5d4819bc521d5811fbbdda4afb7",
		"node_modules/undici/lib/web/websocket/receiver.js": "94c44a1f59b99fd935f7fbbd95b02fc134f6b6afb9b8748259db2d4025f3177b",
		"node_modules/undici/lib/web/websocket/sender.js": "5c5e162f1252d9c91d5cd30ae59c722f1e1cd7df86f03bf45fe085915c2d72e9",
		"node_modules/undici/lib/web/websocket/stream/websocketerror.js": "3743ab3450453a754cdfaa49436314778d38a906a75508f701ca711daf05b43a",
		"node_modules/undici/lib/web/websocket/stream/websocketstream.js": "1e0f2b94400959221c16b6e6ea07a82dca3fbcde2be706b7287fb7d86f2e9d97",
		"node_modules/undici/lib/web/websocket/util.js": "bb4a7bd7f2bf57e45245e41e05cc8d0bdb55feabfd16bbaff7a381863ba5907f",
		"node_modules/undici/lib/web/websocket/websocket.js": "06f52bdada0d2f85f3fc8446639a9d472e88fa928e34d66c20450c951f9e03fe",
		"node_modules/undici/package.json": "da4165f30eff2268f693a567ffe9ab683e60109338deaeb1df91683fa353efa5",
		"node_modules/undici/scripts/strip-comments.js": "72257817367403f268d17f35d61030ec57698063c14e15b7133ac28850d9c7b5",
		"node_modules/undici/types/README.md": "c8cced6ec588c55b07e35733258cb7d6b63e3426ee7490aa9267aab4bda0fb20",
		"node_modules/yaml/LICENSE": "5bba27375d93e9119f76c1015f7672cf9ad5f70952296e0842fb2243d6376869",
		"node_modules/yaml/README.md": "c8aa393826fb1c55ae195399864e7f454a2c66c4d9491459545b26cac4b958e6",
		"node_modules/yaml/bin.mjs": "faebbf70669988b5be13130907adf7b788145960448eab08e92e66189e72f448",
		"node_modules/yaml/browser/dist/compose/compose-collection.js": "7fa2b7a37902d99bf924c3e4db7b003202837597a7815d9917736dbd1861b7f6",
		"node_modules/yaml/browser/dist/compose/compose-doc.js": "0ec9140185c6d965783c4d3e9ae427fb4a377935dd20d8872eb35b56ec461579",
		"node_modules/yaml/browser/dist/compose/compose-node.js": "c6ddd844d89a2086cc1c4cc643cae6361e7fae0728dc0f71066ded02bb7b5d12",
		"node_modules/yaml/browser/dist/compose/compose-scalar.js": "3b7d0f5876dd7c33b8f2bf896178008283be8e4a82495070dc638a922e202e07",
		"node_modules/yaml/browser/dist/compose/composer.js": "214e221c39346468e4b7713d775bfa9dca87695463ac795399e66b91a06540cc",
		"node_modules/yaml/browser/dist/compose/resolve-block-map.js": "ffa61d87f9f0e58a5e05c54073f67c34c4575234f357bcaba6fb164e36996b97",
		"node_modules/yaml/browser/dist/compose/resolve-block-scalar.js": "2a89c2b128e143a98f61751b9ab7dd08d140105c185ece6a687015ea8e0be036",
		"node_modules/yaml/browser/dist/compose/resolve-block-seq.js": "7905b607f90dc9078463fd40e3fbb22537e45e0ef2514fc6c662526b4cdc2ec6",
		"node_modules/yaml/browser/dist/compose/resolve-end.js": "e0a32e1b8c5649ea14152b0c0d45fbd64d46dbfa299a7328b71421e49ee48db2",
		"node_modules/yaml/browser/dist/compose/resolve-flow-collection.js": "957722ee22cb72b48e9d78ed6dabdca97fcbff188cad1f362864a959b184925f",
		"node_modules/yaml/browser/dist/compose/resolve-flow-scalar.js": "5516b92d61fedb6dbfb4523a7aa6c44c12b627e18da5178eafa28324aef4ff7d",
		"node_modules/yaml/browser/dist/compose/resolve-props.js": "4b6c34fe620ddaf31e06c44a1acbbbe8e49a617ae805bb8dca70a278812c16cb",
		"node_modules/yaml/browser/dist/compose/util-contains-newline.js": "4810ffba0d74ebb913731e1369ea17f6fef20df2feb2ef0bd8553e439f4a6b78",
		"node_modules/yaml/browser/dist/compose/util-empty-scalar-position.js": "571d615e24fd379998df23e29df09f127349f4757fc4cbad176aecbfe77b7d82",
		"node_modules/yaml/browser/dist/compose/util-flow-indent-check.js": "ebab50fc461c9eaffe07c807dde4aff4f8c5976f5aa4e8f02608ed57ef52a690",
		"node_modules/yaml/browser/dist/compose/util-map-includes.js": "584a79bdaf93b530fee951c888daf844a6a329f672ffb57450b39f72b0bdfb95",
		"node_modules/yaml/browser/dist/doc/Document.js": "6b9c9187a04d13331c07d7193baf29b0547fd20de042e1fd57289f13d61ad196",
		"node_modules/yaml/browser/dist/doc/anchors.js": "0d5c8fd9bf01e2f4eb0cf08771705e0c0efbd05d9835714fc94850d943003cc6",
		"node_modules/yaml/browser/dist/doc/applyReviver.js": "b653aa07fcd8619637c1dbf6151d9de5e22efcb3becfd4dff86cdcf4bb2f1a97",
		"node_modules/yaml/browser/dist/doc/createNode.js": "80a8212199fa1591e0836c0b19e05f9734dd5e6a7dcd54d6da1e4f2a20f2450c",
		"node_modules/yaml/browser/dist/doc/directives.js": "688805b988a34cf7c2f6e5b6c3f1e6a798b22b4eaa450286df095d6b741fedf0",
		"node_modules/yaml/browser/dist/errors.js": "410bb3397beb0d3a8c649d048b6e087bddf1f7114832eaf94be0fcbb4a8af29b",
		"node_modules/yaml/browser/dist/index.js": "c7d10350202ee8cb14febfce6b559c93760405cc4738a89c10abcb3c44fd6990",
		"node_modules/yaml/browser/dist/log.js": "2e7d7edee783c901f36a8f986d126f15f33ac504fe17d4655e6846869d07b9e4",
		"node_modules/yaml/browser/dist/nodes/Alias.js": "0aaa9956d9f965e29f391c268baca1e7f9c50649b900128a9e5e669450d76411",
		"node_modules/yaml/browser/dist/nodes/Collection.js": "f18de1edc4f5a3ae163a6ca894e2b4debd3a8c480338f580ac6cdffebbfc4bc9",
		"node_modules/yaml/browser/dist/nodes/Node.js": "aaf0e1042d4b11f4760f7de032ec99ac49dda1742e55911f5a4df182cbd5471f",
		"node_modules/yaml/browser/dist/nodes/Pair.js": "a9f0acf0f06eab7852a99418a07628fd0e26476895c90af3ae66bab8704e9b11",
		"node_modules/yaml/browser/dist/nodes/Scalar.js": "80a4961d380ec00c5eb9a47f29dfb378437d055910e163a9ebd9accf032b6e03",
		"node_modules/yaml/browser/dist/nodes/YAMLMap.js": "42b884f36dfb23248e9f2200bce5e7a6007f90e0adfd228de8079346e9627737",
		"node_modules/yaml/browser/dist/nodes/YAMLSeq.js": "75d12e1a5edbf1e3d04d6310ffdaf553a3a1ff7d12643cfa428330ca7189604d",
		"node_modules/yaml/browser/dist/nodes/addPairToJSMap.js": "67cc22455591363a78723876f73640c5712161bb840423e705820666cb0d3ada",
		"node_modules/yaml/browser/dist/nodes/identity.js": "da71af70da393500ab6e3cdbceba9c66965bc89c3401388c9ad422c91abf467f",
		"node_modules/yaml/browser/dist/nodes/toJS.js": "80f2431eaef0c531ab93b1a8883206394ae3fac75732cc683cdabfdcc00dd724",
		"node_modules/yaml/browser/dist/parse/cst-scalar.js": "e30a85b8b613badfb50039938fbb5bbbafbd5f9f95f3a630300ad3dec5fb3dc8",
		"node_modules/yaml/browser/dist/parse/cst-stringify.js": "275b500e3f1a0067d5d8671af5c536963a46d4921e49cf156547f796067b8810",
		"node_modules/yaml/browser/dist/parse/cst-visit.js": "0baadd57686b26163ba71e7323a9208fcba81978e9ecebbad80afaa8baa61788",
		"node_modules/yaml/browser/dist/parse/cst.js": "8bf6c87dc02b9375750d550a9099cb1cd1cd71ca9da68f1a0798844a0f76bf8f",
		"node_modules/yaml/browser/dist/parse/lexer.js": "14d3a6e0f1bf7945a92dfa0366f61bcd122aa3c62addb6fbfdaadd796c634036",
		"node_modules/yaml/browser/dist/parse/line-counter.js": "2428d1b9a18ad7d8dabc7e12276e0fd90446c9e3433f1501e6bb43e111ad63c0",
		"node_modules/yaml/browser/dist/parse/parser.js": "761580b1ad5b36b6fd5e2ffb411798cb5603f8fc46ff11ad8e68ca2ba32a405f",
		"node_modules/yaml/browser/dist/public-api.js": "1635da91bae6389b88d38bc99c57fa6ed71c017b026cb80be9cead10bbafa499",
		"node_modules/yaml/browser/dist/schema/Schema.js": "515d6576e94a5cc96c999cd9da230f7ef79d8fbea1f4c6c6939631ef122fb50e",
		"node_modules/yaml/browser/dist/schema/common/map.js": "6094c4919ff0051a663866cf75df489be51987d808f0862b9b9e36d4090182a7",
		"node_modules/yaml/browser/dist/schema/common/null.js": "6666e819b0dd4c9eac1498e8520e23943abf2c9d92cee72b9c5607557800eb14",
		"node_modules/yaml/browser/dist/schema/common/seq.js": "446dc09d297b2b9823d981f3c44e595f8d87c2ce97e2435e1ecc01bc6c31f4b9",
		"node_modules/yaml/browser/dist/schema/common/string.js": "830740273a4f0a39b94549377cb12183ab8ce558dfb12818f7b295fe261fc08e",
		"node_modules/yaml/browser/dist/schema/core/bool.js": "9d4b1fe540d36d8e09cf5799b8abed53e4ee620425d3d6712e8a50c927752615",
		"node_modules/yaml/browser/dist/schema/core/float.js": "b24b968b6b714be9650480e07f10d039f145e88e4299ce2268eed57de02673a8",
		"node_modules/yaml/browser/dist/schema/core/int.js": "dc7ae60f465273fd7e5dfd6b7f686ac47887fa02db3fe9ec603290003cc9baff",
		"node_modules/yaml/browser/dist/schema/core/schema.js": "92e75125989595b02d9b9f8d6788076d4c1ec173bfa4b0f04eabaaff86153dd9",
		"node_modules/yaml/browser/dist/schema/json/schema.js": "a33036dc6f8916682f9494431ad7ffb1116af7616aa83439b1a956b628e44068",
		"node_modules/yaml/browser/dist/schema/tags.js": "c8085f537d22c3f7f17ea2906ddc11fc69b0106d5447aac2953eec19c025f136",
		"node_modules/yaml/browser/dist/schema/yaml-1.1/binary.js": "ad5b0407d199dda7bc4fbacaee90d2a2a99540c8ced44c13bdf6974cb6dc3ef1",
		"node_modules/yaml/browser/dist/schema/yaml-1.1/bool.js": "1d605f63430047574323f352893ba3c52fc73fbd1b52e47fa6dec2eb375301a5",
		"node_modules/yaml/browser/dist/schema/yaml-1.1/float.js": "40e68189590e6924d063f2b88c7b2415dcb2f796fbd6e9af18e9b119eed3ce23",
		"node_modules/yaml/browser/dist/schema/yaml-1.1/int.js": "6c83bf34c4ecfa722eff2c252c8bdf95661777738c9971c4ccda3a5413218d80",
		"node_modules/yaml/browser/dist/schema/yaml-1.1/merge.js": "f3ac8d7fb4701053e97d5399bdacde15cdc662420cd7e85de349eb20330dab5e",
		"node_modules/yaml/browser/dist/schema/yaml-1.1/omap.js": "fb3d04682a48ec1e0ad26c1afc8a85d1e6c814942ca6eba8bfb94a6571d3e9a6",
		"node_modules/yaml/browser/dist/schema/yaml-1.1/pairs.js": "3c37806050903fd81b51e597bfe7acfff972e788e9a1b3c0148f17b32da3f568",
		"node_modules/yaml/browser/dist/schema/yaml-1.1/schema.js": "1e684cad435d9e9601aa56dd4d55243369a010e75edba21ff31d7be84c8600eb",
		"node_modules/yaml/browser/dist/schema/yaml-1.1/set.js": "0cdce6c41328c116fc17f5660a79f8995af8d0227e424e89177a30894138b687",
		"node_modules/yaml/browser/dist/schema/yaml-1.1/timestamp.js": "18fb9beee49f0f3452601ba01b46ae1d6e49bf4a63b499e9eff28366e3dfcb5d",
		"node_modules/yaml/browser/dist/stringify/foldFlowLines.js": "1a6360496e3cb52767d4c346655307c978cb2c94853229152f97017c4209745a",
		"node_modules/yaml/browser/dist/stringify/stringify.js": "af3ccd112cba318ff9b4686ed9afd0b33fc238da51954fd431dc4c7a9db0b455",
		"node_modules/yaml/browser/dist/stringify/stringifyCollection.js": "0d2babd8428322fe6a9f5cd10fde361a1d8dedae662fd4245c6d151e4a5ae013",
		"node_modules/yaml/browser/dist/stringify/stringifyComment.js": "20d3dc6bebda3efc2394ca162455ce9e4691b6c60995b5b4418b30659e09e03e",
		"node_modules/yaml/browser/dist/stringify/stringifyDocument.js": "3ca3818dc9e81ee7e45f0e26792065f47fccee99b6150e76a94fcbb3d0306421",
		"node_modules/yaml/browser/dist/stringify/stringifyNumber.js": "e0d02220e66fedc267b435e5d13d2383e24c8460562d815f670a169dadc2859f",
		"node_modules/yaml/browser/dist/stringify/stringifyPair.js": "4074dc125fdad4ef2ec8bab4fbf7ece4b399ecd2fbd1813c4a316e88243f1179",
		"node_modules/yaml/browser/dist/stringify/stringifyString.js": "0fd2e43243792cfa0a1d8cea13ba8e05ddaf6fb1296a4fde497b956454bfa44c",
		"node_modules/yaml/browser/dist/util.js": "e6b73d7297c4253e5299d4f97dc2c05e6e30d69ace66962412f6ab9690d4d412",
		"node_modules/yaml/browser/dist/visit.js": "d9daffd11ec68755a7238684ae3f9c64f59dc86338d0e7cbe521a8fc1d45bd19",
		"node_modules/yaml/browser/index.js": "5ae196b7abe55bed1d4d11f7eeba63aeda0c49fb73eb3c7359e3d6b9a080696b",
		"node_modules/yaml/browser/package.json": "3ca9d4afd21425087cf31893b8f9f63c81b0b8408db5e343ca76e5f8aa26ab9a",
		"node_modules/yaml/dist/cli.mjs": "0ad1d42d88c0648fb6fbd158b21dcc2b4daa2e34e4d4df7aa949d6978d343d4d",
		"node_modules/yaml/dist/compose/compose-collection.js": "a7db11a1a7987d6412df8adbbb85ccd4370171f82265703b2b6af2d13c45d646",
		"node_modules/yaml/dist/compose/compose-doc.js": "0f388537747b5c1a241639413f17fc2b5f831451b5017d6902e46db6842a5fe4",
		"node_modules/yaml/dist/compose/compose-node.js": "86562c85e4e5737d28b24aae2030b97bc9b672e1f2de5da9e4d25c4571e4345c",
		"node_modules/yaml/dist/compose/compose-scalar.js": "37920472755bdaa76399b6d33872f0015ae1fd9ba7faa031c03d501aa8c3e903",
		"node_modules/yaml/dist/compose/composer.js": "509c0bdb4cef641cc784c130b6cc2b350752f6841798daa1a13cbcaf4fc74c46",
		"node_modules/yaml/dist/compose/resolve-block-map.js": "dcfada448c8fc532ebba96d6788a4b41bb015fc5e697a9544ff429b9c4e4c70a",
		"node_modules/yaml/dist/compose/resolve-block-scalar.js": "af562e2e3cd7ee7b3cb9342984177f6b5c77de73121e87695db3ff635e12d152",
		"node_modules/yaml/dist/compose/resolve-block-seq.js": "18f54a39d73b600ebbd74a343e6671d0d08423f125bd86963b72dc24d6261911",
		"node_modules/yaml/dist/compose/resolve-end.js": "532bf56299183e75bb7c20db75321367c28393b66ecb8ffd540faedd9817f116",
		"node_modules/yaml/dist/compose/resolve-flow-collection.js": "242470b54c0deba1507babba2e879f3005ed2ee3bd53a36affb6ecf82fddd375",
		"node_modules/yaml/dist/compose/resolve-flow-scalar.js": "13bcd9d37afd4ffec4b1b3bc9ae1ecc2cff97e7f7c91b5f58b71c99ddd526b05",
		"node_modules/yaml/dist/compose/resolve-props.js": "0b49c6af0145c309883dbf24d1a00260c0c090412be10aaa301de126dad15983",
		"node_modules/yaml/dist/compose/util-contains-newline.js": "60182618fc9fa669e74ab74f4231c15b5d24bc52ab0a419684bb827a00d69be6",
		"node_modules/yaml/dist/compose/util-empty-scalar-position.js": "460516395ef7e961d5248e047ee6d52084f279b76e8af9f3c2bac92da1c7d656",
		"node_modules/yaml/dist/compose/util-flow-indent-check.js": "c7c0c9837a1f828de19eb3ee0947dff39c4f69222c762aed9fa2fe14fc46ee3e",
		"node_modules/yaml/dist/compose/util-map-includes.js": "0330dc34072cb499493176b293228631ca8ebaaaddcdc0e63b02bf24f6a25c2d",
		"node_modules/yaml/dist/doc/Document.js": "9bc1c9a56de3902d554e77193125b6aadcfaec743073b3417b22c95a8f7d7923",
		"node_modules/yaml/dist/doc/anchors.js": "ea9a479b1e98d88235ffa6736d0405e2119e9dde7b5249b72185488ab2527261",
		"node_modules/yaml/dist/doc/applyReviver.js": "7271668f41f264e4b9aeb184629cfd11c510b401c5a797fa7194d17a9652976e",
		"node_modules/yaml/dist/doc/createNode.js": "a39d14026d4cc6ff8d76d90db30c41facc26a146ebed30783bcf28e40b5caa65",
		"node_modules/yaml/dist/doc/directives.js": "8f02c3c03571e377e33680b68027d4336234d7a6da3d8c6a8b7f1183c1c428ff",
		"node_modules/yaml/dist/errors.js": "c389d9c448193ce1bcb9641f5eda62cbe56467b2104357d2fc8dd86df88cb07b",
		"node_modules/yaml/dist/index.js": "2d58984e0ae80de4acbd8f009fab332f5ce77d9e1a5f138a3058a0ada6567fb9",
		"node_modules/yaml/dist/log.js": "f6ccc3593357801851aa1023b202f842733043ac3b25773048d836f89de8108d",
		"node_modules/yaml/dist/nodes/Alias.js": "139f5fbb3e7727a9cea89e16b2518f9ffe2e3a37cfb46717e60d23da7d6e739e",
		"node_modules/yaml/dist/nodes/Collection.js": "e2d3ffdc9a997774602e72b296fba641558bc7355c9f12a3ee0502fb1e541306",
		"node_modules/yaml/dist/nodes/Node.js": "b57b42071f7ebab633626858656ec5187617f2290c272e87edc57467ef591215",
		"node_modules/yaml/dist/nodes/Pair.js": "d5dad67916ba0e864a892da63265a062c45c15a191349ef50a540f2ddbae93e5",
		"node_modules/yaml/dist/nodes/Scalar.js": "616ac0f6a0a5a6565307a4bb4443691b0dd019c03d6bb8777353750bd3459487",
		"node_modules/yaml/dist/nodes/YAMLMap.js": "d140cfc5aa8d28737bd3c993d977d5a10ab81efe221e36708ac45b3cf18f5dce",
		"node_modules/yaml/dist/nodes/YAMLSeq.js": "9f89417f3cba5f22a4436f67a9ff9dce627344b5874d2ed7957ff9acffb030e4",
		"node_modules/yaml/dist/nodes/addPairToJSMap.js": "e4977864d75c1fdbf7fc78c9f4329406e153deccfff090fd812dae2b27e6c2c2",
		"node_modules/yaml/dist/nodes/identity.js": "1a7cb042ae725ff68d05dc503efbbecbe65281f18b23dfc23f12d1749a440cfe",
		"node_modules/yaml/dist/nodes/toJS.js": "34de93bb4e16abbf317210a7bd1b062ed20acb028cd8395b69b591f433e277b6",
		"node_modules/yaml/dist/parse/cst-scalar.js": "2f72b634348b04b395408ac427fb4f8ee67432244c327561d4b755a28a783b34",
		"node_modules/yaml/dist/parse/cst-stringify.js": "4d14a7a286cff9c1a578ab15839388ea76f77ae79293db25b235394bcc377b51",
		"node_modules/yaml/dist/parse/cst-visit.js": "525535fc05841407420be6505804c74d873eb3aaa9319679896f7a24a474ca01",
		"node_modules/yaml/dist/parse/cst.js": "acc25760d010068844f36f4aefc7fe6f5f6048fd7f8fcc29d4290e154819d1a4",
		"node_modules/yaml/dist/parse/lexer.js": "cb30a2c4628e270ee810530217f3f7bb0f2730ab89f8fbaf1f8a73ccd1883cf5",
		"node_modules/yaml/dist/parse/line-counter.js": "ddfd11ca2cdd42d36bc6c3090a31c21e6bbcc90bf3498bf6aacfbb30c5d79436",
		"node_modules/yaml/dist/parse/parser.js": "0adc5ffa51ffa4c0ceed1f80efa8b188d10f58c7b9389a6d46bc861e6bff34e1",
		"node_modules/yaml/dist/public-api.js": "9b318ac7b3a3751127c74f59dd1dd209230a70ca116000348b82faae189f72f0",
		"node_modules/yaml/dist/schema/Schema.js": "d3b1bc956a766e2489c36114366f3b3f89762a257ae05ff6271ee3fc8c2a9bf5",
		"node_modules/yaml/dist/schema/common/map.js": "769207eaa56e34c113da10cdc22da845f92b4080ff2b921a72847a38d3ac03d8",
		"node_modules/yaml/dist/schema/common/null.js": "f5d5f694ea3a42ef136e0fbcc674dfd7aa0a3da2b8d62183fb750166a12e52bb",
		"node_modules/yaml/dist/schema/common/seq.js": "51fc0e8bfc63d1d9c7c66b0370a069bb33e0dad865080ff76802803597b9909a",
		"node_modules/yaml/dist/schema/common/string.js": "51d0b3aafab2ffa4ad9d86656a3b92c4b4824d0a8806423882ea5f92a1bf8d11",
		"node_modules/yaml/dist/schema/core/bool.js": "9fa696b1efc38cf8c73a398f30d9f9841658aa5afd0b7a6b0822947c3991ba7a",
		"node_modules/yaml/dist/schema/core/float.js": "139e3964f0e626ad3741500faf51d855ff98eafa2d9e7523cac06260e4515382",
		"node_modules/yaml/dist/schema/core/int.js": "f0e474254f6877d5dd23bb57017980931ab333a7eaa3d33872247a80d11f754d",
		"node_modules/yaml/dist/schema/core/schema.js": "481d7c64817b40090d519fb65bd83730dadd4c6baec1440b9bf85d29e52c046e",
		"node_modules/yaml/dist/schema/json/schema.js": "9efdd848455f6e0621feb13f3eb762453cb02b09d5e04b6501163cfb26af27ed",
		"node_modules/yaml/dist/schema/tags.js": "dba2f42d4dbe8cc8b13f662fd97d253da2da5567e71c47115305efede5a888f2",
		"node_modules/yaml/dist/schema/yaml-1.1/binary.js": "15d7b0b8516c8190b191ec9a0adaab16808d09751ef534d7829512944072011f",
		"node_modules/yaml/dist/schema/yaml-1.1/bool.js": "80a0046224dac3437f22e3b27b0180e1aad82277ab2fee4769094c6d12d67b6f",
		"node_modules/yaml/dist/schema/yaml-1.1/float.js": "a90c44db83152e4d902d46f667737dac90aa86b401abdefe89371ac3bd03abfe",
		"node_modules/yaml/dist/schema/yaml-1.1/int.js": "5ff72b08fecc3a924d4a76658a304859db5edb4fadf8893ee837aa06bba60a52",
		"node_modules/yaml/dist/schema/yaml-1.1/merge.js": "9c85b5e026e4369a96f3f7b5bc6c05da102dfa2968950b17986201cfe0be542c",
		"node_modules/yaml/dist/schema/yaml-1.1/omap.js": "3174270cd59c0f0e3ffd73b3b44c4de679efd5c681325b7aac8e0935d547bee8",
		"node_modules/yaml/dist/schema/yaml-1.1/pairs.js": "46ba76da72ad65a6202358c486c6a3084ab7c48a8eb5be60d241d9e198c5a9b5",
		"node_modules/yaml/dist/schema/yaml-1.1/schema.js": "a7320808484dc6d04817b33b2d09b65ead7ffc1c672ab54e068a80972b17702e",
		"node_modules/yaml/dist/schema/yaml-1.1/set.js": "e4553b0cbde79090884908f44bb3b4afd04935fc23656a1b87ec1af87f24427a",
		"node_modules/yaml/dist/schema/yaml-1.1/timestamp.js": "b157c946dc1b8854aadc4e7994b268ec8afe6d916721cb3580e0752c7d15a5f7",
		"node_modules/yaml/dist/stringify/foldFlowLines.js": "7819679e80222b80c564ea4a9cf3145fa4d5e28a6cfbac248283ac55b0249761",
		"node_modules/yaml/dist/stringify/stringify.js": "38efb5bc5553e98fee58c825a88131c59184368d8689e3e6f43c652a06e9c167",
		"node_modules/yaml/dist/stringify/stringifyCollection.js": "b55fd3b6e3f1346bbcd1fcdc48a59c089b7a4b0e6fac2b46846f7828f9488600",
		"node_modules/yaml/dist/stringify/stringifyComment.js": "490bff57104b7cfdb1893f14528610bb4d0a63c29b314e122233cf308cf96662",
		"node_modules/yaml/dist/stringify/stringifyDocument.js": "dd5ba1813a16b62955c466bce8d1c16254e90b36d688f863c508dc8fe38f2afe",
		"node_modules/yaml/dist/stringify/stringifyNumber.js": "26a1980d34a21a80704d356d475a0187a24ebcbeb37a2e3b149d4d791bb65598",
		"node_modules/yaml/dist/stringify/stringifyPair.js": "bc03ae533d85bf9122e87c0a256c841ae7fbf063499bc3034d49fd9f7b200659",
		"node_modules/yaml/dist/stringify/stringifyString.js": "4113b71a9c4c087a197f71452794a6acb9929111f569c973ff4efe7caee8f777",
		"node_modules/yaml/dist/test-events.js": "5ff5e7f170702d75d4bfd5ef24a35fc95dc2871680c0ae4d714137d4c2cde571",
		"node_modules/yaml/dist/util.js": "193b1d92fb7641d78f17a8f560cbe44dd7cdede2eb8935bacd4ca30df2f1a17a",
		"node_modules/yaml/dist/visit.js": "a757e3b924af184b25e2386d1678b1fe341805a516ebf9bccee219b47aebd5e7",
		"node_modules/yaml/package.json": "31244b3da44f3ddf3313e74b4e9f493621859997cc5dba2f96d92b7887b4b3f4",
		"node_modules/yaml/util.js": "2f1db26f6cc426ef698210b592f40cec49be1b6c4b34e7f2d61904786242bd85"
	}
};
//#endregion
//#region src/windows-terminal.ts
/** 可选的 Windows 官方 runner 宿主适配；不改变沙箱策略或 runner 实现。 */
const digest = (data) => createHash("sha256").update(data).digest("hex");
const failure = (reason) => /* @__PURE__ */ new Error(`CRATE_WINDOWS_TERMINAL: ${reason}`);
/** 拒绝重解析链接；不允许缓存写入通过已有路径逃出 Home。 */
async function directory(path) {
	const parent = dirname(path);
	if (parent !== path) await directory(parent);
	let info;
	try {
		info = await lstat(path);
	} catch (error) {
		if (error.code !== "ENOENT") throw error;
		await mkdir(path);
		info = await lstat(path);
	}
	if (!info.isDirectory() || info.isSymbolicLink()) throw failure(`目录不是普通目录: ${path}`);
}
/** 完整校验和完成标记之前不安装钩子；已有缓存每次逐字节复核。 */
async function prepareWindowsRunner(home, runtime) {
	if (!isAbsolute(home)) throw failure("DSH_HOME 必须是显式绝对路径");
	const pkg = JSON.parse(await readFile(join(runtime, "node_modules/@deepseek-ai/dsh/package.json"), "utf8"));
	if (pkg.version !== windowsRunnerIdentity.version) throw failure(`不支持 DSH ${String(pkg.version)}`);
	if (digest(await readFile(join(runtime, "node_modules/@deepseek-ai/dsh-sandbox-local/lib/index.js"))) !== windowsRunnerIdentity.providerSha256) throw failure("官方 sandbox provider 字节不匹配");
	const node = resolve(runtime, "..", "..", "runtime/primary-runtime/dependencies/node/bin/node.exe");
	const nodeInfo = await lstat(node);
	if (!nodeInfo.isFile() || nodeInfo.isSymbolicLink() || digest(await readFile(node)) !== windowsRunnerIdentity.nodeSha256) throw failure("应用随附控制台 Node 字节不匹配");
	const cache = join(home, ".dsh-pack", "runtime-sources", "windows-terminal-rc3-" + digest(JSON.stringify(windowsRunnerIdentity)).slice(0, 20));
	await directory(dirname(cache));
	let exists = false;
	try {
		const info = await lstat(cache);
		if (!info.isDirectory() || info.isSymbolicLink()) throw failure("runner 缓存不是普通目录");
		exists = true;
	} catch (error) {
		if (error.code !== "ENOENT") throw error;
	}
	const target = cache;
	const receipt = digest(JSON.stringify(windowsRunnerIdentity));
	if (!exists) await mkdir(target);
	if (exists) {
		const marker = join(target, "complete.sha256");
		const markerInfo = await lstat(marker);
		if (!markerInfo.isFile() || markerInfo.isSymbolicLink() || await readFile(marker, "utf8") !== receipt) throw failure("runner 缓存未完整准备，保留现场且不自动修复");
		const inspect = async (prefix = "") => {
			for (const entry of await readdir(join(target, prefix), { withFileTypes: true })) {
				const name = prefix ? `${prefix}/${entry.name}` : entry.name;
				if (entry.isSymbolicLink()) throw failure(`runner 缓存含链接: ${name}`);
				if (entry.isDirectory()) await inspect(name);
				else if (!entry.isFile() || name !== "complete.sha256" && !Object.hasOwn(windowsRunnerIdentity.files, name)) throw failure(`runner 缓存含额外文件: ${name}`);
			}
		};
		await inspect();
	}
	for (const [name, expected] of Object.entries(windowsRunnerIdentity.files)) {
		const source = await readFile(join(runtime, name));
		if (digest(source) !== expected) throw failure(`官方 runner 依赖字节不匹配: ${name}`);
		const destination = join(target, name);
		if (!exists) {
			await directory(dirname(destination));
			await writeFile(destination, source, { flag: "wx" });
		}
		const info = await lstat(destination);
		if (!info.isFile() || info.isSymbolicLink() || digest(await readFile(destination)) !== expected) throw failure(`runner 缓存字节不匹配: ${name}`);
	}
	if (!exists) await writeFile(join(target, "complete.sha256"), receipt, { flag: "wx" });
	return [node, join(cache, "node_modules/@deepseek-ai/dsh-sandbox-windows-acl/lib/runner.js")];
}
/** 只拥有自己写入的数组；其他插件后来修改时不得把它覆盖回去。 */
function installWindowsRunnerHook(sandbox, args) {
	if (sandbox?.constructor?.name !== "LocalSandboxProvider" || !sandbox.internals || typeof sandbox.windowsAclRunnerInvocation !== "function" || sandbox.runnerCommand?.length || sandbox.internals.windowsAclRunnerArgs !== void 0 || sandbox.internals.windowsAclRunnerEntry !== void 0) throw failure("sandbox 服务不受支持或已有 runner 覆盖");
	const internals = sandbox.internals;
	const hadOwn = Object.hasOwn(internals, "windowsAclRunnerArgs");
	const original = internals.windowsAclRunnerArgs;
	const owned = [...args];
	internals.windowsAclRunnerArgs = owned;
	let disposed = false;
	return () => {
		if (disposed) return;
		disposed = true;
		if (internals.windowsAclRunnerArgs !== owned) return;
		if (hadOwn) internals.windowsAclRunnerArgs = original;
		else delete internals.windowsAclRunnerArgs;
	};
}
function windowsTerminalRuntime(config) {
	if (config.windowsTerminalCompatibility === void 0 || config.windowsTerminalCompatibility === false) return void 0;
	if (config.windowsTerminalCompatibility !== true) throw failure("windowsTerminalCompatibility 必须为布尔值");
	if (process.platform !== windowsRunnerIdentity.platform || process.arch !== windowsRunnerIdentity.arch) throw failure("仅支持 Windows x64");
	const runtime = desktopRuntimeRoot();
	if (!runtime || !process.env.DSH_HOME || !isAbsolute(process.env.DSH_HOME)) throw failure("仅支持显式隔离 Home 的官方桌面宿主");
	return runtime;
}
//#endregion
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
//#region src/verify.ts
/** Default Web Verify arguments; execution and status decisions remain in Core. */
const KNOWN_SMOKES = {
	"@deepseek-ai/dsh-base": ["newSessionPersistsAcrossRestart"],
	"@deepseek-ai/dsh-web-app": ["workspaceRendered"],
	"@deepseek-ai/dsh-experimental-terminal-bundle": ["coreCapability"],
	"@deepseek-ai/dsh-experimental-session-search": ["coreCapability"],
	"@deepseek-ai/dsh-experimental-inspector-profile": ["cordisDomQuery"],
	"dsh-crate-web": ["preflightDownloadedPack"]
};
function object(value) {
	return value !== null && typeof value === "object" && !Array.isArray(value);
}
async function configuredRunner(path) {
	if (!isAbsolute(path)) throw new Error("DSH_PACK_VERIFY_RUNNER_CONFIG must be an absolute JSON file path");
	const info = await lstat(path);
	if (!info.isFile() || info.isSymbolicLink()) throw new Error("Verify runner config must be a regular JSON file");
	if (info.size > 1024 * 1024) throw new Error("Verify runner config exceeds the 1 MiB size limit");
	let value;
	try {
		value = JSON.parse(await readFile(path, "utf8"));
	} catch {
		throw new Error("Verify runner config must contain valid JSON");
	}
	if (!object(value)) throw new Error("Verify runner config must be a JSON object");
	return value;
}
async function installedNames(profilePath) {
	let manifest;
	try {
		manifest = JSON.parse(await readFile(join(profilePath, "package.json"), "utf8"));
	} catch {
		return /* @__PURE__ */ new Set();
	}
	if (!object(manifest)) return /* @__PURE__ */ new Set();
	const names = new Set(object(manifest.dependencies) ? Object.keys(manifest.dependencies) : []);
	const dsh = object(manifest.dsh) ? manifest.dsh : {};
	const profile = object(dsh.profile) ? dsh.profile : {};
	if (Array.isArray(profile.bundles)) {
		for (const name of profile.bundles) if (typeof name === "string") names.add(name);
	}
	return names;
}
async function prepareVerifyArgs(base, options) {
	let runner;
	let source = "unconfigured";
	if (options.requestConfig !== void 0) {
		if (!object(options.requestConfig)) throw new Error("runnerConfig must be a JSON object");
		runner = options.requestConfig;
		source = "request";
	} else if (options.configuredPath) {
		runner = await configuredRunner(options.configuredPath);
		source = "host-environment";
	} else if (options.defaultConfig) {
		runner = options.defaultConfig;
		source = "bundled-desktop";
	}
	if (runner?.mode !== void 0 && runner.mode !== options.mode) throw new Error("Verify runner mode must match the requested Verify mode");
	const names = await installedNames(options.profilePath);
	const configured = object(runner?.pluginTests) ? runner.pluginTests : {};
	const contracts = [];
	for (const plugin of names) {
		const probes = object(configured[plugin]) ? Object.keys(configured[plugin]).filter((name) => name.trim()) : [];
		const tests = probes.length ? probes : KNOWN_SMOKES[plugin];
		if (tests?.length) contracts.push({
			plugin,
			required: false,
			tests: [...tests]
		});
	}
	const args = [...base];
	if (runner || contracts.length) await mkdir(options.workDirectory, { recursive: true });
	const operation = randomUUID();
	if (runner) {
		const path = join(options.workDirectory, `verify-${operation}.json`);
		await writeFile(path, JSON.stringify(runner, null, 2) + "\n", {
			encoding: "utf8",
			flag: "wx",
			mode: 384
		});
		args.push("--runner-config", path);
	}
	if (contracts.length) {
		const path = join(options.workDirectory, `verify-${operation}-contracts.json`);
		await writeFile(path, JSON.stringify(contracts, null, 2) + "\n", {
			encoding: "utf8",
			flag: "wx",
			mode: 384
		});
		args.push("--plugin-contract", path);
	}
	return {
		args,
		source
	};
}
//#endregion
//#region src/index.ts
/** Host half: a small local HTTP bridge to the installed dsh-crate Core CLI. */
const API_PATH = "/dsh-crate/api";
const DOWNLOAD_PATH = "/dsh-crate/download";
const MAX_BODY_BYTES = 64 * 1024 * 1024;
const SAFE_NAME = /^[A-Za-z0-9._-]+$/;
const SAFE_PLUGIN_NAME = /^@?[A-Za-z0-9._-]+(?:\/[A-Za-z0-9._-]+)?$/;
const SAFE_OPERATION_ID = /^[0-9a-f-]{36}$/i;
const CRATE_PACKAGE_NAME = "dsh-crate-web";
/** Cordis FiberState enum values; mirrors dsh-host-plugin-inventory phases. */

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
	const core = join(dirname(dirname(fileURLToPath(import.meta.url))), "core");
	try {
		await access(join(core, "dsh_pack", "__main__.py"));
		return core;
	} catch {
		return;
	}
}
async function bundledRuntimeCommand() {
	const command = join(dirname(dirname(fileURLToPath(import.meta.url))), "runtime", "python", "python.exe");
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
	const runtimeModules = await materializeDesktopModules(home, args.flatMap((arg, index) => (arg === "--embed" || arg === "--reference-only") && typeof args[index + 1] === "string" ? [args[index + 1]] : []));
	const hostBundlesFile = await writeDesktopHostBundles(home);
	const desktopRoot = desktopRuntimeRoot();
	let pnpmCommand;
	let patchAdapterCommand;
	if (desktopRoot) {
		const entry = resolve(desktopRoot, "..", "..", "runtime", "primary-runtime", "dependencies", "pnpm", "bin", "pnpm.cjs");
		await access(entry);
		pnpmCommand = JSON.stringify([
			process.execPath,
			"--expose-internals",
			entry
		]);
		const helper = join(dirname(dirname(fileURLToPath(import.meta.url))), "desktop-patch-helper.mjs");
		await access(helper);
		patchAdapterCommand = JSON.stringify([
			process.execPath,
			"--expose-internals",
			helper,
			desktopRoot
		]);
	}
	return await new Promise((resolveRun, reject) => {
		const child = spawn(command.command, [...command.prefix, ...args], {
			cwd: home,
			env: {
				...process.env,
				...command.env,
				DSH_HOME: home,
				DSH_PACK_CORE_MODE: "1",
				PYTHONDONTWRITEBYTECODE: "1",
				...runtimeModules ? { DSH_PACK_RUNTIME_MODULES: runtimeModules } : {},
				...pnpmCommand ? { DSH_PACK_PNPM_COMMAND: pnpmCommand } : {},
				...hostBundlesFile ? { DSH_PACK_HOST_BUNDLES_FILE: hostBundlesFile } : {},
				...patchAdapterCommand ? { DSH_PACK_PATCH_ADAPTER_COMMAND: patchAdapterCommand } : {}
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
function coreDiagnostic(result, fallback) {
	if (isObject(result) && isObject(result.error)) return result.error;
	return { message: fallback };
}
function runtimeCoreArgs() {
	const args = [
		"--node-version",
		process.version.replace(/^v/, ""),
		"--os-name",
		platform() === "win32" ? "windows" : platform()
	];
	const version = desktopRuntimeVersion() ?? process.env.DSH_VERSION;
	if (version) args.push("--dsh-version", version);
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
		currentProfile: argumentValue(args, "--profile") ?? process.env.DSH_PACK_ACTIVE_PROFILE ?? process.env.DSH_PROFILE ?? (desktopRuntimeRoot() ? "desktop" : null),
		pid: process.pid,
		dshHome: home,
		port: port ?? null,
		restartConfigured: !desktopRuntimeRoot() && typeof process.argv[1] === "string" && port !== void 0,
		launcher: desktopRuntimeRoot() ? "official-desktop" : "cli"
	};
}
function operationDiagnostic(code, stage, item, message, impact, suggestedNextStep) {
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
		message
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
		const validPatch = typeof patch === "string" ? patch.trim() !== "" : Array.isArray(patch) && patch.length > 0 && patch.every((value) => typeof value === "string" && value.trim() !== "");
		if (typeof packageJson.name !== "string" || typeof packageJson.version !== "string" || !validPatch) return void 0;
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
	const desktop = desktopRuntimeRoot();
	if (desktop) await scanRoot(join(desktop, "node_modules"), "installation-anchor");
	await scanRoot(profileModules, "profile");
	await scanRoot(anchorModules, "installation-anchor");
	return [...bundles.values()].sort((left, right) => String(left.name).localeCompare(String(right.name)));
}
/**
* Packages published by the DSH project are treated as official built-ins.
* This is the single source of truth for the official/user split used by the
* plugin inventory UI: a runtime loader row is official only when the package
* itself is an official bundle. Loader row ids are deliberately NOT used,
* because a user plugin may register a row id that collides with an official
* built-in (for example a custom sidebar) and must stay in the user group.
*/
function isOfficialPackage(name) {
	return name.startsWith("@deepseek-ai/");
}
/** Collect loader row ids registered via top-level ``insert`` blocks. */
function insertedLoaderIds(patchText) {
	const ids = [];
	let inInsert = false;
	let insertIndent;
	for (const raw of patchText.split(/\r?\n/)) {
		const line = raw.replace(/\s+$/, "");
		const stripped = line.trim();
		if (!stripped || stripped.startsWith("#")) continue;
		const indent = line.length - line.trimStart().length;
		if (indent === 0 && stripped.startsWith("- ")) {
			inInsert = stripped.slice(2).trim() === "insert:";
			insertIndent = void 0;
			continue;
		}
		if (!inInsert) continue;
		if (!stripped.startsWith("- ")) continue;
		if (insertIndent === void 0) insertIndent = indent;
		if (indent !== insertIndent) continue;
		const row = stripped.slice(2).trim();
		if (row.startsWith("id:")) {
			const value = row.slice(3).trim().replace(/^["']|["']$/g, "");
			if (value) ids.push(value);
		}
	}
	return ids;
}
/** Loader row ids registered by one installed Bundle patch. */
async function installedBundlePatchIds(home, profileName, bundleName, patch) {
	const ids = /* @__PURE__ */ new Set();
	const segments = bundleName.split("/");
	const candidates = [
		...desktopRuntimeRoot() ? [join(desktopRuntimeRoot(), "node_modules", ...segments)] : [],
		join(home, "profiles", profileName, "node_modules", ...segments),
		join(home, "profiles", "node_modules", ...segments)
	];
	for (const candidate of candidates) try {
		for (const file of Array.isArray(patch) ? patch : [patch]) {
			const patchText = await readFile(join(candidate, file), "utf8");
			for (const id of insertedLoaderIds(patchText)) ids.add(id);
		}
		break;
	} catch {}
	return ids;
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
				const installedBundles = (await listInstalledBundles(join(root, entry.name, "node_modules"), join(root, "node_modules"))).map((bundle) => ({
					...bundle,
					active: activePlugins.has(String(bundle.name)),
					official: isOfficialPackage(String(bundle.name))
				})).filter((bundle) => bundle.active === true || dependencyNames.includes(String(bundle.name)));
				const activeRowIds = /* @__PURE__ */ new Set();
				const installedRowIds = /* @__PURE__ */ new Map();
				for (const bundle of installedBundles) {
					if (typeof bundle.patch !== "string" && !Array.isArray(bundle.patch)) continue;
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
		error: operationDiagnostic("PROFILE_NAME_RESERVED", "planning", profileName, `Profile name is reserved: ${profileName}`, "The requested Profile was not created.", "Choose another Profile name and retry.")
	};
	const profilesRoot = join(home, "profiles");
	const profileDir = join(profilesRoot, profileName);
	const profileRelative = relative(profilesRoot, resolve(profileDir));
	if (!profileRelative || profileRelative.startsWith("..") || profileRelative.includes("\\")) throw new Error("profileName escaped DSH_HOME");
	try {
		await lstat(profileDir);
		return {
			status: "failed",
			command: "create-profile",
			exitCode: 2,
			error: operationDiagnostic("PROFILE_EXISTS", "planning", profileName, `Profile already exists: ${profileName}`, "No Profile was created or modified.", "Choose a different Profile name, or delete the existing Profile first.")
		};
	} catch (error) {
		if (!isCommandNotFound(error)) throw error;
	}
	if (!desktopRuntimeRoot() && !process.env.DSH_PACK_PNPM_COMMAND) return {
		status: "failed",
		command: "create-profile",
		exitCode: 2,
		error: operationDiagnostic("PACKAGE_MANAGER_REQUIRED", "planning", profileName, "A trusted pnpm command is required to create a managed Profile.", "The requested Profile was not created.", "Use the official Desktop runtime or configure DSH_PACK_PNPM_COMMAND explicitly.")
	};
	const officialModules = desktopRuntimeRoot() ? join(desktopRuntimeRoot(), "node_modules") : join(profilesRoot, "node_modules");
	const officialBase = await readInstalledVersion(join(officialModules, "@deepseek-ai", "dsh-base"));
	const officialWeb = await readInstalledVersion(join(officialModules, "@deepseek-ai", "dsh-web-app"));
	if (officialBase === void 0 || officialWeb === void 0) return {
		status: "failed",
		command: "create-profile",
		exitCode: 2,
		error: operationDiagnostic("OFFICIAL_BUNDLE_MISSING", "planning", profileName, `cannot resolve official bundle version: ${officialBase === void 0 ? "@deepseek-ai/dsh-base" : "@deepseek-ai/dsh-web-app"}`, "The requested Profile was not created.", `Install the official DSH bundles into this DSH_HOME first (${profilesRoot}/node_modules), then retry.`)
	};
	const packageRoot = dirname(dirname(fileURLToPath(import.meta.url)));
	const sourceManifest = JSON.parse(await readFile(join(packageRoot, "package.json"), "utf8"));
	const crateVersion = typeof sourceManifest.version === "string" ? sourceManifest.version : void 0;
	if (crateVersion === void 0) return {
		status: "failed",
		command: "create-profile",
		exitCode: 2,
		error: operationDiagnostic("CRATE_VERSION_MISSING", "planning", profileName, "DSH Crate package version is missing", "The requested Profile was not created.", "Repair the DSH Crate installation and retry.")
	};
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
	const seedRoot = join(workspace.work, `create-${randomUUID()}`);
	await mkdir(seedRoot);
	try {
		const seedProfile = join(seedRoot, "profiles", profileName);
		await mkdir(seedProfile, { recursive: true });
		await writeFile(join(seedProfile, "package.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
		await writeFile(join(seedProfile, "cordis.yml"), "[]\n", "utf8");
		await writeFile(join(seedProfile, "cordis.patch.yml"), PROFILE_PATCH_TEMPLATE, "utf8");
		await writeFile(join(seedProfile, "pnpm-workspace.yaml"), PROFILE_PNPM_WORKSPACE, "utf8");
		await copyPackage(packageRoot, join(seedProfile, "node_modules", ...CRATE_PACKAGE_NAME.split("/")));
		const pack = join(seedRoot, "new-profile.dshcrate");
		const exported = await runCore(home, [
			"export",
			"--profile",
			seedProfile,
			"--output",
			pack,
			"--preset",
			"freeze",
			...DEFAULT_CREATE_BUNDLES.flatMap((name) => ["--embed", name]),
			"--json",
			...runtimeCoreArgs()
		]);
		const exportResult = parseCore(exported.stdout);
		if (exported.code !== 0) return {
			status: "failed",
			command: "create-profile",
			exitCode: exported.code,
			stage: "export",
			error: coreDiagnostic(exportResult, "Could not prepare the empty Profile seed.")
		};
		const imported = await runCore(home, [
			"import",
			pack,
			"--dsh-home",
			home,
			"--target-profile",
			profileName,
			"--offline",
			"--json",
			...runtimeCoreArgs()
		]);
		const importResult = parseCore(imported.stdout);
		if (imported.code !== 0 || !isObject(importResult) || importResult.status !== "prepared") return {
			status: "failed",
			command: "create-profile",
			exitCode: imported.code || 2,
			stage: "import",
			error: coreDiagnostic(importResult, "The new managed Profile could not be prepared.")
		};
	} finally {
		try {
			const actual = await realpath(seedRoot);
			const leaf = relative(await realpath(workspace.work), actual);
			const homeRelative = relative(await realpath(home), actual);
			if (!leaf || isAbsolute(leaf) || leaf.startsWith("..") || isAbsolute(homeRelative) || homeRelative.startsWith("..") || (await lstat(seedRoot)).isSymbolicLink()) throw new Error("Unsafe Profile seed cleanup path");
			await rm(seedRoot, {
				recursive: true,
				force: true
			});
		} catch {
			await record(workspace.history, {
				time: (/* @__PURE__ */ new Date()).toISOString(),
				action: "create-profile-cleanup",
				status: "FAIL",
				profile: profileName,
				message: "Temporary seed cleanup failed; committed targets were not removed.",
				seedRoot
			});
		}
	}
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
async function handleApi(home, body, runtimePlugins = [], runtimeInventoryComplete = false) {
	const action = body.action;
	const workspace = await ensureWorkspace(home);
	if (action === "profiles") {
		const runtime = currentRuntime(home);
		const isOfficialRow = (row) => typeof row.name === "string" && isOfficialPackage(row.name);
		const classifiedPlugins = runtimePlugins.map((row) => ({
			...row,
			official: isOfficialRow(row)
		}));
		return {
			status: "ok",
			profiles: await listProfiles(home),
			runtimePlugins: classifiedPlugins,
			runtimeInventoryComplete,
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
			let planFailure;
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
				} else {
					const diagnostic = coreDiagnostic(parseCore(planRun.stdout), planRun.stderr || "Import planning failed");
					if (!(diagnostic.code === "PROFILE_EXISTS" && body.targetProfile === void 0 && body.overwrite !== true)) planFailure = diagnostic;
				}
			} catch (error) {
				planFailure = coreDiagnostic(void 0, failMessage(error));
			}
			const enriched = isObject(result) ? {
				...result,
				...targetProfile ? { targetProfile } : {},
				...requestedProfileName ? { requestedProfileName } : {},
				...planFailure ? {
					canContinue: false,
					error: planFailure
				} : {}
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
				error: coreDiagnostic(void 0, run.stderr || run.stdout || "dsh-crate inspect failed")
			};
		}
	}
	if (action === "export" || action === "export-plan") {
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
		if (action === "export-plan") args.push("--plan-only");
		if (typeof body.preset === "string") args.push("--preset", body.preset);
		if (body.includeInstalledBundles === true) args.push("--include-installed-bundles");
		const embed = Array.isArray(body.embed) ? body.embed : [];
		const referenceOnly = Array.isArray(body.referenceOnly) ? body.referenceOnly : [];
		for (const name of embed) args.push("--embed", safePluginName(name, "embed plugin"));
		for (const name of referenceOnly) args.push("--reference-only", safePluginName(name, "reference-only plugin"));
		if (body.requiredSecrets !== void 0 && !Array.isArray(body.requiredSecrets)) throw new Error("requiredSecrets must be an array of environment variable names");
		const requiredSecrets = Array.isArray(body.requiredSecrets) ? body.requiredSecrets : [];
		for (const name of requiredSecrets) {
			if (typeof name !== "string" || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) throw new Error("requiredSecrets accepts environment variable names only; never supply Secret values");
			args.push("--required-secret", name);
		}
		let selectionPath;
		if (body.dataSelection !== void 0) {
			if (!Array.isArray(body.dataSelection)) throw new Error("dataSelection must be an array");
			selectionPath = join(workspace.work, "selection-" + randomUUID() + ".json");
			await writeFile(selectionPath, JSON.stringify(body.dataSelection), {
				encoding: "utf8",
				flag: "wx"
			});
			args.push("--data-selection-json", selectionPath);
		}
		const run = await runCore(home, args).finally(async () => {
			if (selectionPath) await rm(selectionPath, { force: true });
		});
		let result;
		try {
			result = parseCore(run.stdout);
		} catch {
			result = void 0;
		}
		if (action === "export-plan") return {
			status: run.code === 0 ? "ok" : "failed",
			command: action,
			exitCode: run.code,
			result,
			...run.code === 0 ? {} : { error: coreDiagnostic(result, run.stderr || "Export preview failed") }
		};
		if (run.code !== 0 || result === void 0) {
			const failure = {
				status: "failed",
				action,
				exitCode: run.code,
				error: coreDiagnostic(result, run.stderr || run.stdout || "dsh-crate export failed"),
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
				error: coreDiagnostic(result, message),
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
			error: operationDiagnostic("ACTIVE_PROFILE", "planning", profileName, `cannot delete the active Profile: ${profileName}`, "The running DSH process would lose its Profile files.", "Switch to another Profile first, then delete this Profile.")
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
				error: coreDiagnostic(result, message),
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
			error: operationDiagnostic("SWITCH_CONFIRMATION_REQUIRED", "planning", profileName, "switching Profile requires explicit confirmation", "The current DSH process was not changed.", "Confirm the switch and retry.")
		};
		if (!(await listProfiles(home)).some((profile) => profile.name === profileName)) return {
			status: "failed",
			command: action,
			exitCode: 2,
			error: operationDiagnostic("PROFILE_MISSING", "planning", profileName, `Profile does not exist: ${profileName}`, "The current DSH process was not changed.", "Choose an existing Profile and retry.")
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
			error: operationDiagnostic("RESTART_NOT_CONFIGURED", "planning", profileName, "the current DSH launch command cannot be safely reconstructed", "The current DSH process was not changed.", "Start DSH with an explicit --profile and --port, or configure the DSH Crate restart launcher.")
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
		const run = await runCore(home, (await prepareVerifyArgs([
			"verify",
			"--dsh-home",
			home,
			"--profile",
			profileName,
			"--mode",
			mode,
			"--json",
			...runtimeCoreArgs()
		], {
			mode,
			profilePath: join(home, "profiles", profileName),
			workDirectory: join(workspace.work, "verify"),
			requestConfig: body.runnerConfig,
			configuredPath: process.env.DSH_PACK_VERIFY_RUNNER_CONFIG,
			defaultConfig: process.platform === "win32" && mode === "web" && desktopRuntimeRoot() ? {
				kind: "desktop",
				mode: "web",
				desktopExecutable: process.execPath,
				runtimeRoot: desktopRuntimeRoot(),
				controllerScript: join(dirname(dirname(fileURLToPath(import.meta.url))), "verify-desktop.mjs"),
				maximumBoots: 1,
				modelRequests: 0,
				automaticRetries: 0
			} : void 0
		})).args);
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
			error: coreDiagnostic(void 0, run.stderr || run.stdout || "dsh-crate verify failed")
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
const inject = ["webServer", "connection"];
function apply(ctx, config = {}) {
	const home = resolve(process.env.DSH_HOME || process.cwd());
	const terminalRuntime = windowsTerminalRuntime(config);
	if (terminalRuntime) ctx.inject(["sandbox"], (scoped) => {
		scoped.effect(async () => {
			const args = await prepareWindowsRunner(home, terminalRuntime);
			return installWindowsRunnerHook(scoped.sandbox, args);
		}, "dsh-crate-web: optional Windows terminal host");
	});
	const connection = ctx.connection;
	ctx.effect(() => {
		const disposeApi = ctx.webServer.register({
			kind: "exact",
			path: API_PATH,
			handler: async (req, res) => {
				if (rejectRequest(connection, req, res)) return;
				if (req.method !== "POST") {
					res.writeHead(405);
					res.end();
					return;
				}
				try {
					const inventory = readRuntimeInventory(ctx);
					json(res, 200, await handleApi(home, await readRequest(req), inventory.rows, inventory.complete));
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
				if (rejectRequest(connection, req, res)) return;
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
