// DSH Crate Web - 本地安装辅助脚本（完全离线，不访问网络）。
// 由 NSIS 安装器调用；也可以直接运行用于调试：
//   node helper.mjs [--dsh-home <目录>] [--profile <名称>] [--tgz <路径>] [--cli <bin.js>] [--log <文件>]
import { spawnSync } from "node:child_process";
import { existsSync, readdirSync, statSync, appendFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import { homedir, platform } from "node:os";

const IS_WIN = platform() === "win32";
const DELIM = IS_WIN ? ";" : ":";
const HELP_DIR = dirname(fileURLToPath(import.meta.url));
const CLI_RELS = [
  "vendor\\deepseek-harness\\apps\\cli\\lib\\bin.js",
  "resources\\app\\vendor\\deepseek-harness\\apps\\cli\\lib\\bin.js",
  "resources\\app.asar.unpacked\\vendor\\deepseek-harness\\apps\\cli\\lib\\bin.js",
];

function fail(message, code = 1) {
  process.stderr.write(`[失败] ${message}\n`);
  process.exit(code);
}

// 把 stdout/stderr 同步追加到日志文件（静默安装时用于留证据）。
function redirectOutput(logPath) {
  if (!logPath) return;
  try { writeFileSync(logPath, ""); } catch { /* ignore */ }
  const writeBoth = (chunk) => {
    try { appendFileSync(logPath, String(chunk)); } catch { /* ignore */ }
  };
  const origOut = process.stdout.write.bind(process.stdout);
  const origErr = process.stderr.write.bind(process.stderr);
  process.stdout.write = (chunk, ...rest) => { origOut(chunk, ...rest); writeBoth(chunk); return true; };
  process.stderr.write = (chunk, ...rest) => { origErr(chunk, ...rest); writeBoth(chunk); return true; };
}

function expandHome(p) {
  if (p === "~") return homedir();
  if (p.startsWith("~/") || p.startsWith("~\\")) return join(homedir(), p.slice(2));
  return p;
}

function where(cmd) {
  if (!IS_WIN) return [];
  const r = spawnSync("where", [cmd], { encoding: "utf8" });
  if (r.status !== 0) return [];
  return r.stdout.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
}

function findNode() {
  if (process.env.DSH_CRATE_NODE && existsSync(process.env.DSH_CRATE_NODE)) return process.env.DSH_CRATE_NODE;
  for (const key of ["ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"]) {
    const base = process.env[key];
    if (base) {
      const p = join(base, "nodejs", "node.exe");
      if (existsSync(p)) return p;
    }
  }
  for (const p of where("node")) {
    if (/node\.exe$/i.test(p) && existsSync(p)) return p;
  }
  return null;
}

function findPnpmDir() {
  if (process.env.DSH_CRATE_PNPM) {
    const p = process.env.DSH_CRATE_PNPM;
    if (!existsSync(p)) return null;
    return statSync(p).isDirectory() ? p : dirname(p);
  }
  for (const p of where("pnpm")) {
    if (existsSync(p)) return dirname(p);
  }
  const npm = process.env.APPDATA && join(process.env.APPDATA, "npm");
  if (npm && existsSync(join(npm, "pnpm.cmd"))) return npm;
  return null;
}

function safeReaddirs(dir) {
  try {
    return readdirSync(dir, { withFileTypes: true })
      .filter((d) => d.isDirectory())
      .map((d) => join(dir, d.name));
  } catch {
    return [];
  }
}

function detectDshHome(override) {
  if (override && override.trim()) return { home: resolve(expandHome(override.trim())), why: "手动指定 --dsh-home" };
  const envHome = process.env.DSH_HOME;
  if (envHome && envHome.trim()) return { home: resolve(expandHome(envHome.trim())), why: "$DSH_HOME 环境变量" };
  const candidates = [];
  const appdata = process.env.APPDATA;
  if (appdata) {
    for (const dir of safeReaddirs(appdata)) {
      for (const sub of ["dsh", "dsh-home"]) {
        const home = join(dir, sub);
        const manifest = join(home, "profiles", "web", "package.json");
        if (existsSync(manifest)) candidates.push({ home, mtime: statSync(manifest).mtimeMs, why: `${dir} (${sub}\\profiles\\web)` });
      }
      const direct = join(dir, "profiles", "web", "package.json");
      if (existsSync(direct)) candidates.push({ home: dir, mtime: statSync(direct).mtimeMs, why: `${dir} (profiles\\web)` });
    }
  }
  if (candidates.length > 0) {
    candidates.sort((a, b) => b.mtime - a.mtime);
    return candidates[0];
  }
  return { home: join(homedir(), ".dsh"), why: "未找到桌面版数据目录，回退到默认 ~/.dsh" };
}

function probeCli(entry) {
  for (const rel of CLI_RELS) {
    const p = join(entry, rel);
    if (existsSync(p)) return p;
  }
  return null;
}

function findCli(home) {
  if (process.env.DSH_CRATE_CLI && existsSync(process.env.DSH_CRATE_CLI)) return process.env.DSH_CRATE_CLI;
  // 1) 由 DSH 数据目录反推应用目录
  for (const appDir of new Set([home, dirname(home)])) {
    const found = probeCli(appDir);
    if (found) return found;
  }
  // 2) 广搜常见位置（跳过系统重目录）
  const roots = [];
  for (const p of [
    process.env.LOCALAPPDATA && join(process.env.LOCALAPPDATA, "Programs"),
    process.env.APPDATA,
    homedir() && join(homedir(), "Desktop"),
    homedir() && join(homedir(), "Documents", "Codex"),
    "H:\\Desktop",
    "H:\\File\\.code",
  ]) {
    if (p && existsSync(p)) roots.push(p);
  }
  const SKIP = new Set(["node_modules", ".git", ".cache", "Windows", "LocalLow", "Temp"]);
  const seen = new Set();
  const stack = roots.map((r) => ({ dir: r, depth: 0 }));
  let visited = 0;
  while (stack.length > 0 && visited < 20000) {
    const { dir, depth } = stack.pop();
    visited += 1;
    if (depth > 8 || seen.has(dir)) continue;
    seen.add(dir);
    for (const entry of safeReaddirs(dir)) {
      const name = entry.split(/[\\/]/).pop();
      if (SKIP.has(name)) continue;
      const found = probeCli(entry);
      if (found) return found;
      stack.push({ dir: entry, depth: depth + 1 });
    }
  }
  return null;
}

function parseArgs(argv) {
  const args = { "dsh-home": undefined, profile: "web", tgz: undefined, cli: undefined, log: undefined };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--dsh-home" || a === "--profile" || a === "--tgz" || a === "--cli" || a === "--log") {
      args[a.slice(2)] = argv[i + 1];
      i += 1;
    }
  }
  return args;
}

function findTgz(explicit) {
  if (explicit && existsSync(explicit)) return resolve(explicit);
  try {
    const hits = readdirSync(HELP_DIR).filter((f) => /^dsh-crate-web-.*\.tgz$/i.test(f));
    if (hits.length > 0) return join(HELP_DIR, hits.sort().pop());
  } catch { /* ignore */ }
  return null;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  redirectOutput(args.log);
  const tgz = findTgz(args.tgz);
  if (!tgz) fail("未找到插件安装包（*.tgz）。请确认安装器文件完整。");

  const nodePath = findNode();
  if (!nodePath) fail("未找到 Node.js。请先安装 Node.js（https://nodejs.org）后重试。");
  const pnpmDir = findPnpmDir();
  if (!pnpmDir) fail("未找到 pnpm。请先安装 pnpm（npm install -g pnpm）后重试。");
  const detected = detectDshHome(args["dsh-home"]);
  const home = detected.home;
  const cli = findCli(home);
  if (!cli) {
    fail(
      `未找到 DSH 命令行程序（apps/cli/lib/bin.js）。\n` +
      `检测到的 DSH 数据目录: ${home}\n` +
      `请确认 DeepSeek Harness 已安装，或用环境变量 DSH_CRATE_CLI 指定 bin.js 路径后重试。`
    );
  }

  const env = {
    ...process.env,
    DSH_HOME: home,
    PATH: [pnpmDir, process.env.PATH].filter(Boolean).join(DELIM),
  };

  process.stdout.write(`DSH Crate Web 本地安装器\n`);
  process.stdout.write(`- 数据目录(DSH_HOME): ${home}\n`);
  process.stdout.write(`- 检测依据: ${detected.why}\n`);
  process.stdout.write(`- DSH 命令行: ${cli}\n`);
  process.stdout.write(`- Node.js: ${nodePath}\n`);
  process.stdout.write(`- pnpm: ${pnpmDir}\n`);
  process.stdout.write(`- 安装包: ${tgz}\n`);
  process.stdout.write(`- 目标 profile: ${args.profile}\n\n`);
  process.stdout.write("开始安装（完全本地，不联网）...\n\n");

  const r = spawnSync(nodePath, [cli, "plugin", "--profile", args.profile, "add", tgz], {
    encoding: "utf8",
    env,
    maxBuffer: 64 * 1024 * 1024,
  });
  if (r.stdout) process.stdout.write(r.stdout);
  if (r.stderr) process.stdout.write(r.stderr);
  const status = r.status ?? 1;
  process.stdout.write(`\n${status === 0 ? "[成功]" : "[失败]"} 退出码 ${status}\n`);
  if (status === 0) {
    process.stdout.write(`请重启 DeepSeek Harness 使 DSH Crate Web 插件生效。\n`);
  }
  process.exit(status >= 0 && status <= 255 ? status : 1);
}

main();