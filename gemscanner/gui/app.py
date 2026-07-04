import os
import sys
from PySide6.QtWidgets import QApplication
from gemscanner.gui.project import Project
from gemscanner.gui.session import ScanSession
from gemscanner.gui.main_window import MainWindow

_STYLE = os.path.join(os.path.dirname(__file__), "style.qss")


def main(argv=None):
    argv = list(sys.argv if argv is None else [sys.argv[0], *argv])
    project_path = "project.yaml"
    if "-p" in argv:
        project_path = argv[argv.index("-p") + 1]
    project = Project.load(project_path)
    config = project.to_scanner_config(project.gems[0]) if project.gems else \
        project.to_scanner_config_default()
    session = ScanSession(config)
    session.configure_stage(project.steps_per_rev)

    app = QApplication.instance() or QApplication(argv)
    if os.path.exists(_STYLE):
        with open(_STYLE, encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    win = MainWindow(project, session)
    win.resize(1100, 720)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
