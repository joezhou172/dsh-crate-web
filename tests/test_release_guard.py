"""发布检查的攻击样本全部在测试中合成，日志不得包含值。"""
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from release_guard import scan_blob, inspect_tarball
from release_policy import validate_metadata


class ReleaseGuardTests(unittest.TestCase):
    def test_tokens_and_local_credentials_are_reported_without_values(self):
        token = b"npm" + b"_" + b"aB9z" * 10
        report = scan_blob("source.ts", b"first\n" + token)
        self.assertEqual(report[0]["line"], 2)
        self.assertNotIn(token.decode(), json.dumps(report))
        self.assertEqual(scan_blob("data", b"plain-local-value", ["plain-local-value"])[0]["rule"], "known-local-credential")

    def test_realistic_literal_and_private_key_block_are_rejected(self):
        self.assertTrue(scan_blob("config.json", b'"apiKey": "' + b"zX9cQ4bN" * 4 + b'"'))
        key = b"-----BEGIN " + b"PRIVATE KEY-----\n" + b"ABCD" * 24 + b"\n-----END PRIVATE KEY-----"
        self.assertTrue(scan_blob("key.pem", key))

    def test_named_test_fixtures_and_secret_references_are_not_credentials(self):
        for payload in [b'apiKey: "SENSITIVE_FIXTURE_VALUE"', b'apiKey: "${API_KEY}"', b'apiKey: "CRATE_VERIFY_NO_MODEL_REQUESTS"', b'-----BEGIN PRIVATE KEY-----']:
            self.assertEqual(scan_blob("test.py", payload), [])

    def test_zip_payload_is_scanned(self):
        content = io.BytesIO()
        with zipfile.ZipFile(content, "w") as archive:
            archive.writestr("config.txt", b"npm" + b"_" + b"Ab9x" * 10)
        self.assertTrue(any("!config.txt" in item["path"] for item in scan_blob("runtime.zip", content.getvalue())))

    def test_tarball_refuses_escape_link_duplicate_and_extra_files(self):
        for name, kind in [("package/../escape", None), ("package/link", tarfile.SYMTYPE), ("package/.env", None), ("package/tests/test.py", None), ("package/skills/dsh-crate-troubleshooting/tests/run_tests.py", None)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                file = Path(directory) / "sample.tgz"
                with tarfile.open(file, "w:gz") as archive:
                    item = tarfile.TarInfo(name)
                    if kind:
                        item.type = kind
                        item.linkname = "outside"
                    archive.addfile(item, io.BytesIO(b""))
                self.assertEqual(inspect_tarball(file)["status"], "FAIL")

    def test_preview_version_tag_and_metadata_are_enforced(self):
        pkg = {"name": "dsh-crate-web", "version": "0.1.1-preview.1", "publishConfig": {"access": "public", "tag": "preview"}, "repository": {"url": "git+https://github.com/joezhou172/dsh-crate-web.git"}}
        self.assertEqual(validate_metadata(pkg, "tag", "v0.1.1-preview.1"), pkg["version"])
        with self.assertRaises(ValueError): validate_metadata(pkg, "tag", "v0.1.0")
        with self.assertRaises(ValueError): validate_metadata(dict(pkg, version="0.1.1"))
        with self.assertRaises(ValueError): validate_metadata(dict(pkg, publishConfig={"access": "public"}))
        with self.assertRaises(ValueError): validate_metadata(dict(pkg, repository={"url": "https://github.com/joezhou172/open-dsh-stack.git"}))

    def test_publish_decision_and_hash_validation_without_network(self):
        node = """
import {publicationDecision,validateAudit} from './scripts/npm-release.mjs';
import assert from 'node:assert/strict';
assert.equal(publicationDecision(404,null,'a'),'publish');
assert.equal(publicationDecision(200,'a','a'),'skip');
for(const status of [401,403,429,500]) assert.throws(()=>publicationDecision(status,null,'a'));
assert.throws(()=>publicationDecision(200,'old','new'));
const hash='a'.repeat(64);
const audit={status:'PASS',package:'dsh-crate-web',version:'0.1.1-preview.1',filename:'release.tgz',sha256:hash};
validateAudit(audit,hash,hash);
assert.throws(()=>validateAudit(audit,hash,'b'.repeat(64)));
assert.throws(()=>validateAudit({...audit,filename:'../outside'},hash,hash));
"""
        subprocess.run(["node", "--input-type=module", "-e", node], cwd=ROOT, check=True, capture_output=True)

    def test_workflow_does_not_publish_pr_or_repack_in_publish_job(self):
        data = (ROOT / ".github/workflows/publish-dsh-crate-web.yml").read_text(encoding="utf-8")
        self.assertIn("branches: [main]", data)
        self.assertIn("pull_request:", data)
        publish = data.split("\n  publish:\n", 1)[1]
        self.assertNotIn("npm pack", publish)
        self.assertIn("actions/download-artifact@v4", publish)
        self.assertIn("EXPECTED_SHA256", publish)
        self.assertIn("github.event.repository.private == false", publish)
        self.assertNotIn("NODE_AUTH_TOKEN:", data)


if __name__ == "__main__": unittest.main()
