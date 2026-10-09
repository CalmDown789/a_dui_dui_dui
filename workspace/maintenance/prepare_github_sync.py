"""Export the verified current handoff and compact workspace documents to a Git clone."""
from pathlib import Path
import hashlib
import json
import shutil
from workspace_maintenance import ROOT, digest, write_json

REPO = ROOT / 'github_sync'
SOURCE = ROOT / 'output/C_TO_B_LATENCY_HANDOFF_V2_20261009'
TARGET = REPO / 'deliverables/c_latency_v2_20261009'
assert (REPO / '.git').is_dir()
assert not TARGET.exists(), 'Existing export must be verified instead of replaced'
source_manifest = json.loads((SOURCE / 'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
for row in source_manifest['files']:
    p = SOURCE / row['file']
    assert p.stat().st_size == row['bytes'] and digest(p) == row['sha256'], row['file']
shutil.copytree(SOURCE, TARGET)
workspace = REPO / 'workspace'
workspace.mkdir()
for name in ('CURRENT_STATUS.md', 'WORKFLOW.md', 'HISTORY.md', 'CLEANUP_PLAN.json'):
    shutil.copy2(ROOT / 'docs' / name, workspace / name)
shutil.copytree(ROOT / 'scripts', workspace / 'maintenance', ignore=shutil.ignore_patterns('__pycache__'))
receipt = ROOT / 'output/C_TO_B_LATENCY_HANDOFF_V2_20261009.receipt.json'
shutil.copy2(receipt, workspace / receipt.name)
plan = json.loads((ROOT / 'docs/CLEANUP_PLAN.json').read_text(encoding='utf-8'))
report = f'''# 工作区整理结果 · 2026-10-10

当前交付实验日期为 2026-10-09。本次整理没有重新上板。

- 清除 {plan['delete_file_count']:,} 个文件，释放 {plan['delete_bytes']:,} 字节（{plan['delete_bytes']/1024**3:.2f} GiB）。
- 根目录探测流水账、旧交接单、旧日记及过期任务书先压缩备份并逐文件校验，再移出工作区。
- 旧仿真缓存中的 {len(plan['diagnostic_backup']['entries']):,} 个日志/报告/脚本原件另行压缩校验；生成的快照、调试数据库及依赖下载可重建。
- 当前 V2 交付的 {len(source_manifest['files']):,} 个文件清理后 SHA256 全部通过。
- 原 A/C 仓库未提交源码保持；本次导出使用独立分支。A 本地旧 README 修改由新状态入口补充，不擅自合入主分支。

备份：`{plan['backup']}`，校验 SHA256 `{plan['backup_sha256']}`。
完整清单见 `CLEANUP_PLAN.json`。冻结 V2 的原身份清单及旧状态原文保持不变，实际最终状态由 BOARD_TEST_RECEIPT、FINAL_RECEIPT 与当前状态摘要补充。
'''
(ROOT / 'docs/CLEANUP_REPORT.md').write_text(report, encoding='utf-8')
(workspace / 'CLEANUP_REPORT.md').write_text(report, encoding='utf-8')
(workspace / 'README.md').write_text('''# 当前工作入口

先读 [当前状态](CURRENT_STATUS.md)，再读 [工作约定](WORKFLOW.md) 和 [必要历史](HISTORY.md)。

当前可运行交付是 [C→B 延迟优化 V2](../deliverables/c_latency_v2_20261009/README.md)，包含源代码、RTL、约束、模型 MEM、输入/Golden、BIT/DCP、构建/回归证据和离线核验工具。冻结文件保持原始字节；其中原状态可能早于最终板测，应按当前状态摘要和最终收据引用。

完整 512 帧原始证据包及历史候选保留本地，SHA256、大小、索引见 V2 的 EVIDENCE_ARCHIVE_INDEX.json 与本目录交付收据。GitHub 文件清单见 SYNC_MANIFEST.json，整理数量与备份位置见 CLEANUP_REPORT.md。

新任务采用 candidates/<日期>_<任务>/，结果写 results/，缓存写 build/；任务结束只维护一份简短结果和当前状态，避免重复流水账。
''', encoding='utf-8')
readme = REPO / 'README.md'
content = readme.read_text(encoding='utf-8-sig')
readme.write_text('> 当前工作区进度与关键交付：[2026-10-09 延迟优化 V2 / 整理后的工作入口](workspace/README.md)。本分支用于工作区同步，未合并到 main 或 C/B 项目分支。\n\n' + content, encoding='utf-8')
attributes = REPO / '.gitattributes'
attributes.write_text(attributes.read_text(encoding='utf-8') + '\n# Preserve frozen delivery bytes and identity hashes.\ndeliverables/** -text\nworkspace/** -text\n', encoding='utf-8')
gitignore = REPO / '.gitignore'
gitignore.write_text(gitignore.read_text(encoding='utf-8') + '\n# Local task output and caches\ncandidates/**/build/\ncandidates/**/results/\n__pycache__/\n', encoding='utf-8')
rows = []
for base in (workspace, TARGET):
    for p in sorted(base.rglob('*')):
        if p.is_file():
            rows.append({'file': p.relative_to(REPO).as_posix(), 'bytes': p.stat().st_size,
                         'sha256': digest(p)})
for name in ('README.md', '.gitattributes', '.gitignore'):
    p = REPO / name
    rows.append({'file': name, 'bytes': p.stat().st_size, 'sha256': digest(p)})
write_json(workspace / 'SYNC_MANIFEST.json', {
    'branch': 'workspace-maintenance-20261009',
    'scope': 'complete_frozen_current_V2_and_compact_workspace_framework',
    'files': rows, 'file_count': len(rows), 'bytes': sum(r['bytes'] for r in rows),
    'original_delivery_manifest_sha256': digest(SOURCE / 'DELIVERY_MANIFEST.json'),
    'not_uploaded': ['512-frame raw evidence archive (1,540,326,714 bytes)',
                     'old worktrees and candidates', 'Python environments', 'temporary caches',
                     'legacy scratch backup (verified local archive)'],
    'verification': 'every exported file compared with its source; frozen delivery SHA check passed'})
for row in source_manifest['files']:
    assert digest(TARGET / row['file']) == row['sha256'], row['file']
print(json.dumps({'status': 'PASS_EXPORT_IDENTICAL', 'files': len(rows), 'bytes': sum(r['bytes'] for r in rows)}))
