"""正式包身份、版本兼容和零桌面控制器契约。"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
from dsh_pack import diagnostics
from dsh_pack._version import __version__


class PublicIdentityTests(unittest.TestCase):
    def test_actual_compatibility_metadata_supports_this_core(self):
        pkg = json.loads((ROOT / "package.json").read_text())
        compat = json.loads((ROOT / "skills/dsh-crate-troubleshooting/compatibility.json").read_text())
        self.assertEqual(pkg["name"], "dsh-crate-web")
        self.assertEqual(pkg["version"], __version__)
        self.assertEqual(pkg["version"], compat["skillVersion"])
        result = diagnostics.compat_status(skill_version=compat["skillVersion"],
            dsh_crate_range=compat["compatibility"]["dshCrate"],
            supported_schemas=compat["compatibility"]["diagnosticSchema"],
            crate_version=__version__, diagnostic_schema_version=1)
        self.assertEqual(result["status"], "FULL")
        self.assertTrue(result["canProceed"])

    def test_compiled_client_registration_and_self_references_agree(self):
        script = """
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
let registration;
vm.runInNewContext(readFileSync('lib/client.js','utf8'),{
  window:{__ModuleLoader__:{load:value=>{registration=value}}}
});
assert.equal(registration.id,'dsh-crate-web');
assert.equal(typeof registration.factory,'function');
for(const name of ['cordis.patch.yml','tsdown.config.ts','src/index.ts','src/verify.ts','lib/index.js','core/dsh_pack/desktop_verify.py']) {
  const text=readFileSync(name,'utf8');
  assert(text.includes('dsh-crate-web'),name);
  assert(!text.includes('@open-dsh-stack/dsh-crate-web'),name);
}
"""
        subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT, check=True, capture_output=True)

    def test_bundled_helpers_parse_and_zero_desktop_bridge_contracts_pass(self):
        for name in ["lib/index.js", "lib/client.js", "verify-desktop.mjs", "desktop-patch-helper.mjs", "restart-helper.mjs", "scripts/npm-release.mjs"]:
            subprocess.run(["node", "--check", name], cwd=ROOT, check=True, capture_output=True)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["node", "tests/bundled_verify_bridge.mjs", str(root)], cwd=ROOT, check=True, capture_output=True)

    @unittest.skipUnless(os.environ.get("CRATE_CONTRACT_RUNTIME"), "需显式指定已有 DSH runtime；不下载或安装依赖")
    def test_controller_contract_uses_existing_runtime_without_booting_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            node = os.environ.get("CRATE_CONTRACT_NODE", "node")
            env = dict(os.environ)
            if "CRATE_CONTRACT_NODE" in os.environ:
                env["ELECTRON_RUN_AS_NODE"] = "1"
            subprocess.run([node, "tests/bundled_verify_controller.mjs", str(root / "controller"),
                            os.environ["CRATE_CONTRACT_RUNTIME"]], cwd=ROOT, env=env, check=True, capture_output=True)


if __name__ == "__main__": unittest.main()
