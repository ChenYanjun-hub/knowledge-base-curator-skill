"""Shared, offline validation and rendering for curated knowledge packages."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

TYPES = {'operation', 'faq', 'process', 'product', 'rule'}
STATUSES = {'confirmed', 'partial', 'pending'}


def load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('The input must be a JSON object.')
    return data


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_asset(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise ValueError('Missing local_path.')
    path = Path(relative)
    if path.is_absolute():
        raise ValueError('local_path must be relative to the input JSON directory.')
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError('Image path escapes the input directory.')
    if not resolved.is_file():
        raise ValueError(f'Image file does not exist: {relative}')
    return resolved


def validate(data: dict, root: Path) -> dict:
    errors, warnings = [], []

    def require_text(value, label):
        if not isinstance(value, str) or not value.strip():
            errors.append(f'{label}: expected nonempty text.')

    def string_list(value, label):
        if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
            errors.append(f'{label}: expected an array of nonempty strings.')
            return []
        return value

    def known_id(value, mapping):
        return isinstance(value, str) and value in mapping

    def indexed(name):
        value = data.get(name, [])
        if not isinstance(value, list):
            errors.append(f'{name}: expected an array.')
            return [], {}
        mapping = {}
        valid = []
        for item in value:
            if not isinstance(item, dict):
                errors.append(f'{name}: every entry must be an object.')
                continue
            key = item.get('id')
            if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', key):
                errors.append(f'{name}: invalid id {key!r}.')
                continue
            if key in mapping:
                errors.append(f'{name}: duplicate id {key}.')
            mapping[key] = item
            valid.append(item)
        return valid, mapping

    if data.get('schema_version') != 1:
        errors.append('schema_version must be 1.')
    require_text(data.get('title'), 'title')
    require_text(data.get('version'), 'version')
    sources, source_map = indexed('sources')
    images, image_map = indexed('images')
    cards, card_map = indexed('cards')
    issues, _ = indexed('issues')
    cases, _ = indexed('evaluation_cases')
    if not sources:
        errors.append('At least one source is required.')
    if not cards:
        errors.append('At least one card is required.')
    for source in sources:
        require_text(source.get('title'), f"source {source['id']} title")
        require_text(source.get('version'), f"source {source['id']} version")
    for image in images:
        label = f"image {image['id']}"
        if not known_id(image.get('source_id'), source_map):
            errors.append(f'{label}: unknown source_id.')
        require_text(image.get('locator'), label + ' locator')
        require_text(image.get('alt'), label + ' alt')
        require_text(image.get('description'), label + ' description')
        try:
            path = local_asset(root, image.get('local_path'))
            if image.get('sha256') and digest(path) != image['sha256']:
                errors.append(f'{label}: image checksum mismatch.')
        except (ValueError, OSError) as exc:
            errors.append(f'{label}: {exc}')
        if image.get('url'):
            try:
                if not isinstance(image['url'], str):
                    raise ValueError('URL must be text.')
                url = urlsplit(image['url'])
                if url.scheme != 'https' or not url.hostname or url.username or url.password:
                    raise ValueError('Expected an HTTPS image URL without credentials.')
            except (ValueError, TypeError) as exc:
                errors.append(f'{label}: invalid URL: {exc}')

    used = set()
    published_image_ids = set()
    published = []
    for card in cards:
        label = f"card {card['id']}"
        require_text(card.get('title'), label + ' title')
        if not known_id(card.get('type'), TYPES):
            errors.append(f'{label}: invalid type.')
        status = card.get('evidence_status', 'confirmed')
        if not known_id(status, STATUSES):
            errors.append(f'{label}: invalid evidence_status.')
        if 'summary' in card and not isinstance(card['summary'], str):
            errors.append(f'{label}: summary must be text.')
        scope = card.get('scope')
        if not isinstance(scope, dict):
            errors.append(f'{label}: scope must be an object.')
            scope = {}
        require_text(scope.get('system'), label + ' scope.system')
        roles = string_list(scope.get('roles', []), label + ' scope.roles')
        if not roles:
            errors.append(f'{label}: at least one explicit role/scope label is required.')
        if 'manual_scope' in scope:
            require_text(scope['manual_scope'], label + ' scope.manual_scope')
        refs = card.get('source_refs')
        if not isinstance(refs, list) or not refs:
            errors.append(f'{label}: source_refs required.')
            refs = []
        for ref in refs:
            if not isinstance(ref, dict):
                errors.append(f'{label}: invalid source reference.')
                continue
            if not known_id(ref.get('source_id'), source_map):
                errors.append(f'{label}: unknown source_id {ref.get("source_id")!r}.')
            require_text(ref.get('locator'), label + ' source locator')
        for field in ['questions', 'keywords', 'preconditions', 'facts', 'limitations']:
            string_list(card.get(field, []), label + ' ' + field)
        if status == 'partial' and not card.get('limitations'):
            errors.append(f'{label}: partial evidence needs an explicit limitation.')
        for related in string_list(card.get('related_card_ids', []), label + ' related_card_ids'):
            if related not in card_map or related == card['id']:
                errors.append(f'{label}: invalid related card {related}.')
        steps = card.get('steps', [])
        if not isinstance(steps, list):
            errors.append(f'{label}: steps must be an array.')
            steps = []
        image_ids = string_list(card.get('image_ids', []), label + ' image_ids')[:]
        for step in steps:
            if not isinstance(step, dict):
                errors.append(f'{label}: step must be an object.')
                continue
            require_text(step.get('text'), label + ' step text')
            image_ids.extend(string_list(step.get('image_ids', []), label + ' step image_ids'))
        for image_id in image_ids:
            if image_id not in image_map:
                errors.append(f'{label}: unknown image {image_id}.')
            else:
                used.add(image_id)
                if status != 'pending':
                    published_image_ids.add(image_id)
        if status != 'pending':
            published.append(card)
            if not card.get('summary') and not card.get('facts') and not steps:
                errors.append(f'{label}: no answer content.')

    excluded = set()
    exclusions = data.get('image_exclusions', [])
    if not isinstance(exclusions, list):
        errors.append('image_exclusions must be an array.')
        exclusions = []
    for item in exclusions:
        if not isinstance(item, dict):
            errors.append('image_exclusions entries must be objects.')
            continue
        image_id = item.get('image_id')
        require_text(item.get('reason'), 'image exclusion reason')
        if not isinstance(image_id, str):
            errors.append('Image exclusion image_id must be text.')
            continue
        if image_id not in image_map:
            errors.append(f'Unknown excluded image {image_id}.')
        if image_id in excluded:
            errors.append(f'Duplicate exclusion {image_id}.')
        if image_id in used:
            errors.append(f'Image {image_id} is both used and excluded.')
        excluded.add(image_id)
    missing = set(image_map) - used - excluded
    if missing:
        errors.append('Images without use or exclusion reason: ' + ', '.join(sorted(missing)))
    issue_card_ids = set()
    for issue in issues:
        require_text(issue.get('question'), f"issue {issue['id']} question")
        require_text(issue.get('evidence'), f"issue {issue['id']} evidence")
        for card_id in string_list(issue.get('card_ids', []), 'issue card_ids'):
            issue_card_ids.add(card_id)
            if card_id not in card_map:
                errors.append(f'Issue refers to unknown card {card_id}.')
    for case in cases:
        require_text(case.get('query'), f"case {case['id']} query")
        for card_id in string_list(case.get('expected_card_ids', []), 'case expected_card_ids'):
            if card_id not in card_map:
                errors.append(f'Test case refers to unknown card {card_id}.')
        string_list(case.get('expected_facts', []), 'case expected_facts')
        string_list(case.get('negative_constraints', []), 'case negative_constraints')
    for card in cards:
        if card.get('evidence_status') == 'pending' and card['id'] not in issue_card_ids:
            errors.append(f"Pending card {card['id']} needs a linked issue.")
    local_only = sorted(key for key in published_image_ids if not image_map[key].get('url'))
    if local_only:
        warnings.append('Some published images have local references only; cloud access is not ready.')
    if not cases:
        warnings.append('No retrieval evaluation plan was supplied.')
    if not published:
        warnings.append('No confirmed or partial card is available for publication.')
    return {
        'valid': not errors, 'errors': errors, 'warnings': warnings,
        'card_count': len(cards), 'published_card_count': len(published),
        'pending_card_count': len(cards) - len(published), 'image_count': len(images),
        'used_image_count': len(used), 'excluded_image_count': len(excluded),
        'local_only_image_ids': local_only,
        'cloud_image_urls_present': not local_only,
        'image_urls_network_verified': False, 'business_rules_verified_by_script': False,
        'retrieval_test_execution': 'not_run',
    }


def inline(text) -> str:
    return re.sub(r'([\\`*_\[\]<>])', r'\\\1', str(text).replace('\n', ' '))


def render(data: dict, image_paths: dict, offline=False) -> tuple[str, list]:
    source_map = {source['id']: source for source in data['sources']}
    image_map = {image['id']: image for image in data.get('images', [])}
    blocks, index = [], []

    def picture(image_id):
        image = image_map[image_id]
        address = image_paths[image_id] if offline else image.get('url') or image_paths[image_id]
        address = address.replace(' ', '%20').replace('(', '%28').replace(')', '%29')
        return f"![{inline(image_id)}：{inline(image['alt'])}]({address})\n\n图示说明：{image['description']}"

    for card in data['cards']:
        status = card.get('evidence_status', 'confirmed')
        entry = {'id': card['id'], 'title': card['title'], 'type': card['type'], 'scope': card['scope'], 'source_refs': card['source_refs'], 'evidence_status': status, 'published': status != 'pending'}
        index.append(entry)
        if status == 'pending':
            continue
        scope = card['scope']
        lines = [f"## 知识卡片：{inline(card['title'])}",
                 f"适用系统：{inline(scope['system'])}；适用角色/范围：{'、'.join(inline(r) for r in scope['roles'])}。",
                 f"知识编号：{inline(card['id'])}。"]
        if scope.get('manual_scope'):
            lines.append(f"范围标识：{inline(scope['manual_scope'])}。")
        for ref in card['source_refs']:
            source = source_map[ref['source_id']]
            lines.append(f"来源：《{inline(source['title'])}》；版本：{inline(source['version'])}；位置：{inline(ref['locator'])}。")
        for key, label in [('questions', '常见问法'), ('keywords', '关键词')]:
            if card.get(key):
                lines.append(f"{label}：{'；'.join(card[key])}")
        if card.get('summary'):
            lines.append('**结论/概要**：' + card['summary'])
        for key, label in [('preconditions', '前提'), ('facts', '事实与规则')]:
            if card.get(key):
                lines.append(f'**{label}**\n\n' + '\n'.join('- ' + x for x in card[key]))
        for number, step in enumerate(card.get('steps', []), 1):
            lines.append(f"{number}. {step['text']}")
            lines.extend(picture(image_id) for image_id in step.get('image_ids', []))
        lines.extend(picture(image_id) for image_id in card.get('image_ids', []))
        if card.get('limitations'):
            lines.append('**限制与资料边界**\n\n' + '\n'.join('- ' + x for x in card['limitations']))
        if card.get('related_card_ids'):
            lines.append('关联卡片：' + '、'.join(inline(x) for x in card['related_card_ids']))
        block = '\n\n'.join(lines)
        entry['characters'] = len(block)
        blocks.append(block)
    body = '\n\n---\n\n'.join(blocks)
    return f"# {inline(data['title'])}\n\n整理版本：{inline(data['version'])}。\n\n{body}\n", index
