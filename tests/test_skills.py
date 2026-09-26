from pathlib import Path
import tempfile
import unittest

from core.skills import catalog, import_skill, select_skill


class SkillsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_catalog_search(self):
        self.assertEqual([item['name'] for item in catalog(self.root, 'segurança')], ['security'])
        self.assertEqual(len(catalog(self.root)), 7)

    def test_auto_selection(self):
        for request, expected in [('Explique o roteamento', 'explore'), ('Entregue unified diff', 'patch'), ('Teste os limites', 'testing'), ('Revise este módulo', 'review'), ('Debug deste bug', 'debug'), ('Segurança de arquivos', 'security'), ('Crie uma função', 'minimal'), ('clamp lança ValueError', 'minimal')]:
            with self.subTest(request=request):
                self.assertEqual(select_skill(request)[0], expected)

    def test_import_requires_confirmation_and_is_not_auto_selected(self):
        source = self.root / 'external.md'; source.write_text('Instruções revisáveis')
        preview = import_skill(self.root, source, 'custom-work')
        self.assertFalse(preview['imported'])
        self.assertFalse((self.root / 'skills').exists())
        import_skill(self.root, source, 'custom-work', approved=True)
        self.assertEqual(select_skill('', 'custom-work', self.root)[1], 'Instruções revisáveis')
        self.assertEqual(select_skill('custom-work', root=self.root)[0], 'minimal')
        self.assertEqual(catalog(self.root)[-1]['source'], 'custom')

    def test_import_cannot_overwrite_builtin_or_escape(self):
        source = self.root / 'external.md'; source.write_text('content')
        for name in ('debug', '../escape', 'auto', 'none'):
            with self.assertRaises(ValueError):
                import_skill(self.root, source, name, approved=True)

    def test_import_rejects_large_or_symlink(self):
        source = self.root / 'external.md'; source.write_text('x' * 8001)
        with self.assertRaises(ValueError):
            import_skill(self.root, source, 'large')
        link = self.root / 'link.md'; link.symlink_to(source)
        with self.assertRaises(ValueError):
            import_skill(self.root, link, 'linked')

    def test_custom_directory_symlink_rejected(self):
        (self.root / 'skills').symlink_to(self.root)
        with self.assertRaises(ValueError):
            catalog(self.root)

    def test_none_is_empty(self):
        self.assertEqual(select_skill('debug', 'none'), ('none', ''))
