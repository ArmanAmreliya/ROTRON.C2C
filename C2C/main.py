"""Entry point for the C2C project.

This launches the GUI `MainWindow` when run as a module:
    python -m C2C.main

It falls back to non-package imports when necessary so running as a script
may still work depending on your PYTHONPATH / current working directory.
"""

import sys

def import_mainwindow():
    try:
        from C2C.ui.main_window import MainWindow
        return MainWindow
    except Exception:
        # Print the original traceback for debugging, then try package/absolute
        # fallbacks. This helps when the module is executed as a script rather
        # than a package (so relative imports fail).
        import traceback
        traceback.print_exc()
        # Ensure the project root (parent of this package) is on sys.path so
        # absolute import `C2C.ui.main_window` can succeed when this file is
        # executed as a script from the `C2C/` directory.
        try:
            from pathlib import Path
            project_root = Path(__file__).resolve().parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
        except Exception:
            pass

        # Try relative import
        try:
            from .ui.main_window import MainWindow
            return MainWindow
        except Exception:
            # Try top-level (non-package) import as a last resort
            try:
                from ui.main_window import MainWindow
                return MainWindow
            except Exception as e:
                raise ImportError("Failed to import MainWindow from UI module") from e


def main():
    try:
        MainWindow = import_mainwindow()
    except Exception as e:
        print("Could not import MainWindow:", e, file=sys.stderr)
        raise

    app = MainWindow()
    try:
        app.update_view()
    except Exception:
        pass
    app.run()


if __name__ == "__main__":
    main()
