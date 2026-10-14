"""Catch source corruption before importing the application and its dependencies."""
import ast
import unittest
from pathlib import Path


class SourceIntegrityTests(unittest.TestCase):
    def test_all_runtime_modules_compile_and_have_unique_top_level_definitions(self):
        root = Path(__file__).resolve().parents[1] / 'job_radar_ai'
        for path in sorted(root.glob('*.py')):
            with self.subTest(module=path.name):
                tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
                names = [node.name for node in tree.body
                         if isinstance(node, (ast.FunctionDef, ast.ClassDef))]
                self.assertEqual(len(names), len(set(names)), 'Duplicate runtime definition')
