from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import export_main_graph  # noqa: E402


class ExportMainGraphTests(unittest.TestCase):
    def test_collect_main_graph_only_includes_knowledge_pages(self) -> None:
        vault = ROOT / ".tmp-tests" / "main-graph-vault"
        if vault.exists():
            shutil.rmtree(vault)
        for rel in [
            "wiki/concepts",
            "wiki/entities",
            "wiki/domains",
            "wiki/syntheses",
            "wiki/sources",
        ]:
            (vault / rel).mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "concepts" / "A.md").write_text(
            '---\ntitle: "A"\ntype: "concept"\ngraph_role: "knowledge"\ngraph_include: "true"\n---\n\n[[entities/B]]\n[[sources/raw-a]]\n',
            encoding="utf-8",
        )
        (vault / "wiki" / "entities" / "B.md").write_text(
            '---\ntitle: "B"\ntype: "entity"\ngraph_role: "knowledge"\ngraph_include: "true"\n---\n\n[[domains/C]]\n',
            encoding="utf-8",
        )
        (vault / "wiki" / "domains" / "C.md").write_text(
            '---\ntitle: "C"\ntype: "domain"\ngraph_role: "knowledge"\ngraph_include: "true"\n---\n\n[[syntheses/D]]\n',
            encoding="utf-8",
        )
        (vault / "wiki" / "syntheses" / "D.md").write_text(
            '---\ntitle: "D"\ntype: "synthesis"\ngraph_role: "knowledge"\ngraph_include: "true"\n---\n\n',
            encoding="utf-8",
        )
        (vault / "wiki" / "sources" / "raw-a.md").write_text(
            '---\ntitle: "raw-a"\ntype: "source"\ngraph_role: "document"\ngraph_include: "false"\n---\n\n[[concepts/A]]\n',
            encoding="utf-8",
        )
        self.addCleanup(lambda: shutil.rmtree(vault, ignore_errors=True))

        graph = export_main_graph.collect_main_graph(vault)

        self.assertEqual(sorted(graph["nodes"].keys()), ["concepts/A", "domains/C", "entities/B", "syntheses/D"])
        self.assertIn(("concepts/A", "entities/B"), graph["edges"])
        self.assertNotIn(("concepts/A", "sources/raw-a"), graph["edges"])

    def test_build_graph_view_page_contains_mermaid_and_filters(self) -> None:
        page = export_main_graph.build_graph_view_page(
            {
                "nodes": {
                    "concepts/A": {"label": "A", "folder": "concepts"},
                    "entities/B": {"label": "B", "folder": "entities"},
                },
                "edges": [("concepts/A", "entities/B")],
            }
        )

        self.assertIn("```mermaid", page)
        self.assertIn("path:\"wiki/concepts\"", page)
        self.assertIn("[[concepts/A]]", page)

    def test_script_writes_graph_view_markdown(self) -> None:
        vault = ROOT / ".tmp-tests" / "main-graph-run-vault"
        if vault.exists():
            shutil.rmtree(vault)
        (vault / "wiki" / "concepts").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "concepts" / "A.md").write_text(
            '---\ntitle: "A"\ntype: "concept"\ngraph_role: "knowledge"\ngraph_include: "true"\n---\n',
            encoding="utf-8",
        )
        self.addCleanup(lambda: shutil.rmtree(vault, ignore_errors=True))

        subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "export_main_graph.py"), "--vault", str(vault)],
            check=True,
            cwd=ROOT,
        )

        output = vault / "wiki" / "graph-view.md"
        self.assertTrue(output.exists())
        self.assertIn("主图谱视角", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
