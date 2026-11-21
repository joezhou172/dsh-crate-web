"""停机后的桌面维护；执行器和日志位于目标 Profile 之外。"""
import contextlib
import io
import json
import os
import sys
from pathlib import Path
from .snapshot import Snapshot, inventory, save_json
from .incremental import recover_interrupted


def run(job_path, rollback=False):
    job_path = Path(job_path).resolve()
    job = json.loads(job_path.read_text(encoding='utf-8'))
    home = Path(job['home']).resolve()
    target = home / 'profiles' / job['target']
    from .importer import _validate_profile_name
    _validate_profile_name(job['target'])
    if job_path.parent.parent != home / '.dsh-pack' / 'maintenance':
        raise ValueError('维护任务路径越界')
    if (target / 'lock').exists():
        raise ValueError('目标仍有运行锁，未执行快照或导入')
    report_file = job_path.parent / 'result.json'
    report = json.loads(report_file.read_text(encoding='utf-8')) if report_file.exists() else {}
    os.environ.pop('DSH_PACK_ACTIVE_PROFILE', None)
    os.environ['DSH_PACK_MAINTENANCE_JOB'] = job_path.parent.name
    if rollback:
        try:
            recover_interrupted(home, job['target'])
            snapshots = report.get('result', {}).get('snapshot', {})
            for key in ('metadata', 'profile'):
                if snapshots.get(key):
                    Snapshot.reopen(home, snapshots[key]).rollback()
            # 覆盖“Core 已提交，但维护结果尚未落盘”这一崩溃窗口。
            for journal in (home / '.dsh-pack/snapshots').glob('*/transaction.json'):
                transaction = json.loads(journal.read_text(encoding='utf-8'))
                if transaction.get('maintenanceJob') == job_path.parent.name and transaction.get('status') != 'restored':
                    for saved in reversed(transaction['snapshots']):
                        Snapshot.reopen(home, saved).rollback()
                    transaction['status'] = 'restored'
                    save_json(journal, transaction)
            if report.get('before') is not None and inventory(target) != report['before']:
                raise ValueError('恢复后的 Profile 与导入前不一致，已保留现场')
            report.update(status='restored', restored=True)
            save_json(report_file, report)
            return report
        except Exception as error:
            report.update(status='recovery-failed', restored=False, recoveryError=str(error))
            save_json(report_file, report)
            raise
    from .cli import main
    def execute(args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(args)
        value = json.loads(out.getvalue())
        if code:
            raise RuntimeError(json.dumps(value, ensure_ascii=False))
        return value
    try:
        recover_interrupted(home, job['target'])
        report = {'status': 'snapshot', 'before': inventory(target), 'target': job['target']}
        save_json(report_file, report)
        # 前置快照在预览/安装之前完成。实际提交继续使用 Core 原有原子事务。
        before = Snapshot(home, target)
        report['preSnapshot'] = str(before.root)
        save_json(report_file, report)
        args = job['args']
        if '--incremental' in args:
            preview = execute([*args, '--plan-only'])
            report['plan'] = preview['plan']
            save_json(report_file, report)
            args = [*args, '--plan-token', preview['plan']['planToken']]
        result = execute(args)
        report.update(status='awaiting-boot', result=result)
        save_json(report_file, report)
        return report
    except Exception as error:
        report.update(status='failed', error=str(error))
        save_json(report_file, report)
        try:
            run(job_path, rollback=True)
        except Exception as recovery:
            report.update(status='recovery-failed', recoveryError=str(recovery), restored=False)
            save_json(report_file, report)
        return json.loads(report_file.read_text(encoding='utf-8'))

if __name__ == '__main__':
    try:
        result = run(sys.argv[1], '--rollback' in sys.argv[2:])
        print(json.dumps({'status': result['status'], 'restored': result.get('restored')}, ensure_ascii=False))
        sys.exit(0 if result['status'] in ('awaiting-boot', 'restored') else 1)
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}, ensure_ascii=False))
        sys.exit(1)
