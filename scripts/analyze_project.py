# Author: mertaygn, cglrgrkn
import ast
import json
import os
from pathlib import Path


class ProjectAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.has_qt_import = False
        self.has_qt_class = False
        self.has_pure_logic = False
        self.qt_keywords = ['PyQt6', 'PyQt5', 'PySide6']
        self.ui_base_classes = ['QWidget', 'QMainWindow', 'QDialog', 'QFrame', 'QObject', 'QThread']

    def visit_Import(self, node):
        for alias in node.names:
            if any(qt_kw in alias.name for qt_kw in self.qt_keywords):
                self.has_qt_import = True
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module and any(qt_kw in node.module for qt_kw in self.qt_keywords):
            self.has_qt_import = True
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        is_qt_class = False
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id in self.ui_base_classes:
                is_qt_class = True
                self.has_qt_class = True
            elif isinstance(base, ast.Attribute) and base.attr in self.ui_base_classes:
                is_qt_class = True
                self.has_qt_class = True

        if not is_qt_class:
            self.has_pure_logic = True

        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        if not hasattr(self, '_in_class') or not self._in_class:
            self.has_pure_logic = True
        self.generic_visit(node)


def analyze_directory(directory_path):
    results = {"CORE_LOGIC": [], "GUI_ONLY": [], "SPAGHETTI": [], "ERROR": []}

    for root, dirs, files in os.walk(directory_path):
        # build directories ve venv gibi klasörleri es geç:
        dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'myenv', 'build', 'dist']]

        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        tree = ast.parse(f.read(), filename=file_path)

                    analyzer = ProjectAnalyzer()
                    analyzer.visit(tree)

                    # Göreceli path kullanmak raporu daha okunaklı yapar
                    rel_path = os.path.relpath(file_path, directory_path)

                    if analyzer.has_qt_import:
                        if analyzer.has_pure_logic and analyzer.has_qt_class:
                            results["SPAGHETTI"].append(rel_path)
                        elif analyzer.has_qt_class:
                            results["GUI_ONLY"].append(rel_path)
                        else:
                            # Sadece import var ama GUI class yoksa da Spaghetti olabilir veya Thread/Signal kullanıyordur.
                            results["SPAGHETTI"].append(rel_path)
                    else:
                        results["CORE_LOGIC"].append(rel_path)

                except Exception as e:
                    results["ERROR"].append(f"{os.path.relpath(file_path, directory_path)} - {str(e)}")

    return results


if __name__ == "__main__":
    # Proje dizinini dosyaya göre bul (guii klasörü)
    script_dir = Path(__file__).resolve().parent
    guij_dir = script_dir.parent

    print(f"[{guij_dir}] dizini analiz ediliyor, lütfen bekleyin...")
    analysis_results = analyze_directory(str(guij_dir))

    report_path = guij_dir / "architecture_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(analysis_results, f, indent=4, ensure_ascii=False)

    print("Bitti!")
    print(f"Rapor Yolu: {report_path}")
    print(f"CORE_LOGIC: {len(analysis_results['CORE_LOGIC'])}")
    print(f"GUI_ONLY: {len(analysis_results['GUI_ONLY'])}")
    print(f"SPAGHETTI: {len(analysis_results['SPAGHETTI'])}")
    print(f"ERROR: {len(analysis_results['ERROR'])}")
