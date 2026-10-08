"""Behavior checks use synthetic documents only; no private business fixtures."""
import copy
import hashlib
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills' / 'knowledge-base-curator' / 'scripts'))
from kb_common import validate
from package_kb import build
from extract_sources import extract


def png_bytes():
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 1, 1, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b'\0\xff\xff\xff')) + chunk(b'IEND', b'')


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kb-curator-test-')
        self.root = Path(self.temp.name)
        self.data = json.loads((ROOT / 'examples' / 'cards.json').read_text(encoding='utf-8'))

    def tearDown(self):
        self.temp.cleanup()

    def add_image(self):
        raw = png_bytes()
        (self.root / 'screen.png').write_bytes(raw)
        self.data['images'] = [{'id': 'image-1', 'source_id': 'manual', 'locator': '第2章截图', 'local_path': 'screen.png', 'alt': '虚构测试图', 'description': '只有一个白色像素，用于测试字节和引用，不是业务截图。', 'sha256': hashlib.sha256(raw).hexdigest()}]
        self.data['cards'][0]['steps'][0]['image_ids'] = ['image-1']
        return raw

    def input_path(self):
        path = self.root / 'cards.json'
        path.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')
        return path

    def test_example_is_valid_but_not_business_certified(self):
        report = validate(self.data, self.root)
        self.assertTrue(report['valid'], report)
        self.assertEqual(report['published_card_count'], 2)
        self.assertFalse(report['business_rules_verified_by_script'])
        self.assertEqual(report['retrieval_test_execution'], 'not_run')

    def test_pending_card_not_published_and_issue_kept(self):
        build(self.input_path(), self.root / 'out')
        text = (self.root / 'out/knowledge.md').read_text(encoding='utf-8')
        self.assertNotIn('DEMO_ARCHIVED_EDIT', text)
        self.assertIn('项目处于草稿状态', text)
        self.assertIn('24 V', text)
        self.assertIn('归档后的项目', (self.root / 'out/issues.txt').read_text(encoding='utf-8'))

    def test_image_bytes_zip_and_local_only_state(self):
        raw = self.add_image()
        before = self.input_path().read_bytes()
        report = build(self.root / 'cards.json', self.root / 'out')
        self.assertFalse(report['cloud_image_urls_present'])
        self.assertEqual(report['local_only_image_ids'], ['image-1'])
        self.assertEqual((self.root / 'out/images/0001.png').read_bytes(), raw)
        self.assertEqual((self.root / 'cards.json').read_bytes(), before)
        with ZipFile(self.root / 'out/knowledge-package.zip') as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.read('images/0001.png'), raw)
            self.assertNotIn('knowledge-package.zip', archive.namelist())

    def test_remote_url_presence_does_not_claim_network_verification(self):
        self.add_image()
        self.data['images'][0]['url'] = 'https://example.invalid/screen.png'
        report = build(self.input_path(), self.root / 'out')
        self.assertTrue(report['cloud_image_urls_present'])
        self.assertFalse(report['image_urls_network_verified'])
        self.assertIn('https://example.invalid/screen.png', (self.root / 'out/knowledge.md').read_text(encoding='utf-8'))
        self.assertNotIn('https://example.invalid', (self.root / 'out/knowledge-offline.md').read_text(encoding='utf-8'))

    def test_unaccounted_image_fails_then_explicit_exclusion_passes(self):
        self.add_image()
        self.data['cards'][0]['steps'][0]['image_ids'] = []
        self.assertFalse(validate(self.data, self.root)['valid'])
        self.data['image_exclusions'] = [{'image_id': 'image-1', 'reason': 'Decorative synthetic pixel.'}]
        self.assertTrue(validate(self.data, self.root)['valid'])

    def test_used_image_cannot_also_be_excluded(self):
        self.add_image()
        self.data['image_exclusions'] = [{'image_id': 'image-1', 'reason': 'duplicate'}]
        self.assertFalse(validate(self.data, self.root)['valid'])

    def test_unknown_source_duplicate_id_and_wrong_image_fail(self):
        for mutate in [lambda d: d['cards'][0]['source_refs'][0].update(source_id='missing'),
                       lambda d: d['cards'].append(copy.deepcopy(d['cards'][0])),
                       lambda d: d['cards'][0].update(image_ids=['missing'])]:
            data = copy.deepcopy(self.data)
            mutate(data)
            self.assertFalse(validate(data, self.root)['valid'])

    def test_partial_evidence_requires_visible_boundary(self):
        self.data['cards'][0]['evidence_status'] = 'partial'
        self.data['cards'][0]['limitations'] = []
        self.assertFalse(validate(self.data, self.root)['valid'])

    def test_bad_field_types_are_reported_without_crashing(self):
        for mutate in [lambda d: d['cards'][0].update(type=[]),
                       lambda d: d['cards'][0].update(evidence_status={}),
                       lambda d: d['cards'][0].update(summary=123),
                       lambda d: d['cards'][0]['source_refs'][0].update(source_id=[]),
                       lambda d: d['issues'][0].update(card_ids=None),
                       lambda d: d.update(image_exclusions=[{'image_id': [], 'reason': 'invalid'}])]:
            data = copy.deepcopy(self.data)
            mutate(data)
            self.assertFalse(validate(data, self.root)['valid'])

    def test_delivered_manifest_can_build_next_version(self):
        raw = self.add_image()
        build(self.input_path(), self.root / 'v1')
        delivered = self.root / 'v1/cards.json'
        build(delivered, self.root / 'v2')
        self.assertEqual((self.root / 'v2/images/0001.png').read_bytes(), raw)
        self.assertEqual((self.root / 'v1/knowledge.md').read_bytes(), (self.root / 'v2/knowledge.md').read_bytes())
        self.assertEqual(len(json.loads(delivered.read_text(encoding='utf-8'))['cards']), 3)

    def test_traversal_and_wrong_checksum_fail(self):
        self.add_image()
        self.data['images'][0]['local_path'] = '../outside.png'
        self.assertFalse(validate(self.data, self.root)['valid'])
        self.data['images'][0]['local_path'] = 'screen.png'
        self.data['images'][0]['sha256'] = '0' * 64
        self.assertFalse(validate(self.data, self.root)['valid'])

    def test_existing_output_not_overwritten(self):
        output = self.root / 'out'
        output.mkdir()
        sentinel = output / 'keep.txt'
        sentinel.write_text('keep', encoding='utf-8')
        with self.assertRaises(ValueError):
            build(self.input_path(), output)
        self.assertEqual(sentinel.read_text(), 'keep')

    def test_docx_extraction_preserves_image_and_source_with_table_notice(self):
        image = png_bytes()
        path = self.root / 'synthetic.docx'
        xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body><w:p><w:r><w:t>草稿可以编辑。</w:t></w:r><w:r><a:blip r:embed="rId1"/></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>仅草稿</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'''
        rels = '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="media/image1.png" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"/></Relationships>'''
        with ZipFile(path, 'w') as archive:
            archive.writestr('word/document.xml', xml)
            archive.writestr('word/_rels/document.xml.rels', rels)
            archive.writestr('word/media/image1.png', image)
        source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        result = extract([path], self.root / 'evidence')
        self.assertEqual(result['sources'][0]['sha256'], source_hash)
        self.assertEqual(result['sources'][0]['units'][0]['text'], '草稿可以编辑。')
        self.assertEqual((self.root / 'evidence' / result['images'][0]['local_path']).read_bytes(), image)
        self.assertTrue(any('Tables' in warning for warning in result['warnings']))
        self.assertFalse(result['ocr_performed'])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), source_hash)

    def test_unsupported_pdf_does_not_generate_fake_text(self):
        path = self.root / 'scan.pdf'
        path.write_bytes(b'%PDF-synthetic')
        with self.assertRaises(ValueError):
            extract([path], self.root / 'evidence')
        self.assertFalse((self.root / 'evidence').exists())


if __name__ == '__main__':
    unittest.main()
