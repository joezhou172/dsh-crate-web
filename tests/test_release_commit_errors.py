"""目录提交失败须给出可操作提示，且不改写原错误与回滚结果。"""
import unittest
from dsh_pack.errors import PackImportError

class CommitMessageTests(unittest.TestCase):
    def error(self, winerror=5, filename2='new-profile', **details):
        return PackImportError('Import failed unexpectedly',stage='commit',code='IMPORT_FAILED',details={
            'observed':{'error':'ORIGINAL_WINDOWS_ERROR','errorType':'PermissionError',
                        'winerror':winerror,'filename':'staged-profile','filename2':filename2},**details})

    def test_rename_access_error_has_actionable_message_and_original_error(self):
        for code in [5,32]:
            with self.subTest(code=code):
                value=self.error(winerror=code).as_dict()
                self.assertIn('占用',value['message'])
                self.assertIn('权限',value['message'])
                self.assertIn('关闭',value['suggestedNextStep'])
                self.assertEqual(value['observed']['error'],'ORIGINAL_WINDOWS_ERROR')
                self.assertEqual(value['code'],'IMPORT_FAILED')
                self.assertEqual(value['stage'],'commit')
                self.assertEqual(value['status'],'FAIL')

    def test_retained_stage_keeps_cleanup_failure_guidance(self):
        value=self.error(canRetry=False,temporaryProfileStatus='retained',
            suggestedNextStep='先检查原始错误与回滚错误，解除占用并核实残留。',
            rollback={'status':'FAIL','errors':[{'error':'ORIGINAL_ROLLBACK_ERROR'}]}).as_dict()
        self.assertIn('占用',value['message'])
        self.assertFalse(value['canRetry'])
        self.assertEqual(value['temporaryProfileStatus'],'retained')
        self.assertIn('回滚错误',value['suggestedNextStep'])
        self.assertEqual(value['details']['rollback']['errors'][0]['error'],'ORIGINAL_ROLLBACK_ERROR')

    def test_non_rename_and_other_os_errors_keep_existing_message(self):
        for kwargs in [dict(filename2=None),dict(winerror=2),dict(winerror=None)]:
            self.assertEqual(self.error(**kwargs).as_dict()['message'],'Import failed unexpectedly')

if __name__=='__main__':unittest.main()
