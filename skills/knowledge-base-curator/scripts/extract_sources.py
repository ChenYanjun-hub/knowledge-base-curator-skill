#!/usr/bin/env python3
"""Extract local DOCX/Markdown/TXT evidence without OCR, network access, or uploads."""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import posixpath
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'v': 'urn:schemas-microsoft-com:vml',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def docx(path, source_id, output):
    units, images, warnings = [], [], []
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
        rels = {}
        if 'word/_rels/document.xml.rels' in archive.namelist():
            rels = {r.attrib['Id']: r.attrib for r in ET.fromstring(archive.read('word/_rels/document.xml.rels'))}
        seen_media = {}
        body = root.find('w:body', NS)
        if body is None:
            raise ValueError('DOCX has no document body.')
        for n, paragraph in enumerate(body.findall('.//w:p', NS), 1):
            unit_id = f'{source_id}-P{n:04d}'
            text = ''.join(node.text or '' for node in paragraph.findall('.//w:t', NS))
            style_node = paragraph.find('w:pPr/w:pStyle', NS)
            image_ids, remote_images = [], []
            relationships = []
            for blip in paragraph.findall('.//a:blip', NS):
                relationships.extend(x for x in [blip.get('{' + NS['r'] + '}embed'), blip.get('{' + NS['r'] + '}link')] if x)
            for image in paragraph.findall('.//v:imagedata', NS):
                if image.get('{' + NS['r'] + '}id'):
                    relationships.append(image.get('{' + NS['r'] + '}id'))
            for rid in dict.fromkeys(relationships):
                relationship = rels.get(rid)
                if not relationship:
                    warnings.append(f'{unit_id}: missing image relationship {rid}.')
                    continue
                target = relationship.get('Target', '')
                if relationship.get('TargetMode') == 'External':
                    remote_images.append(target)
                    continue
                member = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join('word', target))
                if member not in archive.namelist():
                    warnings.append(f'{unit_id}: missing media {member}.')
                    continue
                if member not in seen_media:
                    info = archive.getinfo(member)
                    if info.file_size > 50 * 1024 * 1024:
                        raise ValueError(f'Media too large for automatic extraction: {member}')
                    raw = archive.read(member)
                    image_id = f'{source_id}-image-{len(seen_media)+1:03d}'
                    suffix = Path(member).suffix.lower() or '.bin'
                    filename = f'images/{image_id}{suffix}'
                    (output / filename).write_bytes(raw)
                    record = {'id': image_id, 'source_id': source_id, 'locator': unit_id,
                              'local_path': filename, 'original_media': member, 'sha256': sha(raw),
                              'alt': '', 'description': '', 'unit_ids': [],
                              'mime_type': mimetypes.guess_type(filename)[0] or 'application/octet-stream'}
                    seen_media[member] = record
                    images.append(record)
                record = seen_media[member]
                record['unit_ids'].append(unit_id)
                image_ids.append(record['id'])
            if text or image_ids or remote_images:
                units.append({'id': unit_id, 'text': text, 'paragraph_style': style_node.get('{' + NS['w'] + '}val') if style_node is not None else None, 'image_ids': image_ids, 'external_image_urls': remote_images})
        for tag, message in [('tbl', 'Tables were flattened into paragraph order; inspect row/column meaning.'),
                             ('ins', 'Tracked insertions exist; review revision state.'),
                             ('del', 'Tracked deletions exist; deleted text was not treated as current text.'),
                             ('txbxContent', 'Text boxes exist; reading order and duplicate text need review.')]:
            if body.find('.//w:' + tag, NS) is not None:
                warnings.append(message)
        if any(name.startswith(('word/header', 'word/footer')) for name in archive.namelist()):
            warnings.append('Header/footer parts are not included in this main-body extraction.')
        if any(name in archive.namelist() for name in ['word/footnotes.xml', 'word/endnotes.xml', 'word/comments.xml']):
            warnings.append('Footnotes, endnotes, or comments exist and need separate inspection.')
        if any(unit['external_image_urls'] for unit in units):
            warnings.append('External image references were recorded but not downloaded.')
        unlocated = sorted(name for name in archive.namelist() if name.startswith('word/media/') and not name.endswith('/') and name not in seen_media)
        if unlocated:
            warnings.append('Media not located in main-body image references; inspect and preserve or exclude explicitly: ' + ', '.join(unlocated))
    return units, images, warnings


def extract(inputs, output):
    for path in inputs:
        if not path.is_file() or path.suffix.lower() not in {'.docx', '.md', '.txt'}:
            raise ValueError(f'Unsupported or missing input: {path}. Use a suitable parser for PDF/OCR.')
    if output.exists():
        raise ValueError('Output exists; use a new evidence directory.')
    output.mkdir(parents=True)
    (output / 'images').mkdir()
    result = {'schema_version': 1, 'sources': [], 'images': [], 'warnings': [], 'ocr_performed': False}
    for number, path in enumerate(inputs, 1):
        source_id = f'source-{number:03d}'
        raw = path.read_bytes()
        warnings = []
        if path.suffix.lower() == '.docx':
            units, images, warnings = docx(path, source_id, output)
        else:
            text = raw.decode('utf-8-sig')
            units = [{'id': f'{source_id}-L{n:04d}', 'text': line} for n, line in enumerate(text.splitlines(), 1)]
            images = []
            refs = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', text)
            if refs:
                warnings.append('Markdown image links recorded only; resolve and inspect them before adding to the curated image manifest.')
            for unit in units:
                unit['image_references'] = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', unit['text'])
        source = {'id': source_id, 'title': path.stem, 'version': '未注明', 'filename': path.name, 'sha256': sha(raw), 'units': units, 'warnings': warnings}
        result['sources'].append(source)
        result['images'].extend(images)
        result['warnings'].extend(f'{source_id}: {warning}' for warning in warnings)
        (output / f'{source_id}.txt').write_text('\n'.join(f"{unit['id']}: {unit['text']}" + (f" [images: {', '.join(unit['image_ids'])}]" if unit.get('image_ids') else '') for unit in units) + '\n', encoding='utf-8')
    (output / 'evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', type=Path, nargs='+')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = extract(args.inputs, args.out)
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc) + '\n')
    print(json.dumps({'sources': len(result['sources']), 'embedded_images': len(result['images']), 'warnings': result['warnings'], 'ocr_performed': False}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
