"""Application entry point: create the Qt app and show the main window."""
import sys

from qtpy.QtWidgets import QApplication

from toumira import updater
from toumira.ui import MainWindow


def main():
    updater.schedule_old_exe_cleanup(sys.argv)
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    exit_code = app.exec() if hasattr(app, "exec") else app.exec_()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
