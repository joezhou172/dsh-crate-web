"""Windows 短暂占用快照日志时重试原子替换，永久失败必须保留错误。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from dsh_pack.snapshot import save_json


class AtomicJournalTests(unittest.TestCase):
    def test_transient_windows_access_denied(self):
        import os
        original = os.replace
        calls = []
        def replace(source, target):
            calls.append((source, target))
            if len(calls) == 1:
                error = PermissionError('sharing violation')
                error.winerror = 5
                raise error
            original(source, target)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'journal.json'
            path.write_text('{"status":"ready"}', encoding='utf-8')
            with patch('dsh_pack.snapshot.os.replace', side_effect=replace), patch('dsh_pack.snapshot.time.sleep'):
                save_json(path, {'status': 'committed'})
            self.assertEqual(json.loads(path.read_text()), {'status': 'committed'})
            self.assertEqual(len(calls), 2)

    def test_persistent_denial_is_bounded_and_preserves_old_journal(self):
        error = PermissionError('permanent denial')
        error.winerror = 32
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'journal.json'
            path.write_text('{"status":"ready"}', encoding='utf-8')
            with patch('dsh_pack.snapshot.os.replace', side_effect=error) as replace, patch('dsh_pack.snapshot.time.sleep'):
                with self.assertRaises(PermissionError):
                    save_json(path, {'status': 'committed'})
            self.assertEqual(replace.call_count, 8)
            self.assertEqual(json.loads(path.read_text()), {'status': 'ready'})

    def test_other_errors_are_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('dsh_pack.snapshot.os.replace', side_effect=OSError('disk failure')) as replace:
                with self.assertRaises(OSError):
                    save_json(Path(directory) / 'journal.json', {'status': 'ready'})
            self.assertEqual(replace.call_count, 1)
