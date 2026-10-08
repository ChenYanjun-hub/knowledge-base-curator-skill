#!/usr/bin/env python3
"""Build a traceable Markdown package from manually curated cards.json."""
import argparse
import copy
import json
import shutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from kb_common import digest, load, local_asset, render, validate


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def build(input_path: Path, output: Path):
    data = load(input_path)
    root = input_path.resolve().parent
    report = validate(data, root)
    if not report['valid']:
        raise ValueError('\n'.join(report['errors']))
    output = output.resolve()
    if output.exists():
        raise ValueError('Output already exists; choose a new version directory.')
    output.mkdir(parents=True)
    (output / 'images').mkdir()
    image_paths, image_manifest = {}, []
    for number, image in enumerate(data.get('images', []), 1):
        source = local_asset(root, image['local_path'])
        extension = source.suffix.lower()
        if not extension or len(extension) > 12:
            extension = '.bin'
        relative = f'images/{number:04d}{extension}'
        shutil.copyfile(source, output / relative)
        image_paths[image['id']] = relative
        image_manifest.append({**{k: image[k] for k in ('id', 'source_id', 'locator', 'alt', 'description', 'url') if k in image}, 'local_path': relative, 'sha256': digest(output / relative)})
    main_text, index = render(data, image_paths)
    offline_text, _ = render(data, image_paths, offline=True)
    (output / 'knowledge.md').write_text(main_text, encoding='utf-8')
    (output / 'knowledge-offline.md').write_text(offline_text, encoding='utf-8')
    write_json(output / 'card-index.json', index)
    editable = copy.deepcopy(data)
    for item in editable.get('images', []):
        item['local_path'] = image_paths[item['id']]
        item['sha256'] = digest(output / item['local_path'])
    write_json(output / 'cards.json', editable)
    write_json(output / 'source-map.json', {'sources': data['sources'], 'images': image_manifest, 'image_exclusions': data.get('image_exclusions', [])})
    write_json(output / 'validation.json', report)
    write_json(output / 'evaluation-plan.json', {'execution_status': 'not_run', 'cases': data.get('evaluation_cases', [])})
    issue_lines = ['业务待确认事项', '本文件供维护确认，不建议直接加入常规问答索引。']
    for issue in data.get('issues', []):
        issue_lines.extend([f"\n{issue['id']}：{issue['question']}", '证据/缺口：' + issue['evidence'], '关联卡片：' + '、'.join(issue.get('card_ids', []))])
    if not data.get('issues'):
        issue_lines.append('本次整理未登记待确认事项；这不表示已经通过现行业务验收。')
    (output / 'issues.txt').write_text('\n'.join(issue_lines) + '\n', encoding='utf-8')
    instructions = f'''知识库交付说明

主文件：knowledge.md。每张知识卡以二级标题和水平分隔线区分。
离线审阅：knowledge-offline.md 与 images 文件夹一起使用。
后续更新：编辑 cards.json，再用打包工具输出到新的版本目录；它包含完整卡片及待确认草稿。
元数据、卡片索引、待确认事项和测试计划供维护使用，不需要全部加入业务检索。

卡片总数：{report['card_count']}；主文件卡片数：{report['published_card_count']}；待确认未入主文件：{report['pending_card_count']}。
源图片：{report['image_count']}；已使用：{report['used_image_count']}；有理由排除：{report['excluded_image_count']}。
需要云端地址的本地图片：{', '.join(report['local_only_image_ids']) or '未发现仅本地引用的已发布图片'}。

本地图片路径不能由云端知识库直接读取。HTTPS 地址存在也不代表已做联网、平台解析或多模态验证。
先核对实际分段边界，完整保留角色、前提、限制与图片。字符数不等于 token 数。
文档内的范围标识不自动创建平台元数据，需配置实际字段和过滤条件。
业务待确认项见 issues.txt；执行评测前 evaluation-plan.json 状态为 not_run。
本包完成结构与引用校验，不代表业务事实或线上召回已验收。
'''
    (output / 'import-notes.txt').write_text(instructions, encoding='utf-8')
    archive_path = output / 'knowledge-package.zip'
    with ZipFile(archive_path, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob('*')):
            if path.is_file() and path != archive_path:
                archive.write(path, path.relative_to(output).as_posix())
    with ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP integrity check failed.')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build(args.input, args.out)
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
