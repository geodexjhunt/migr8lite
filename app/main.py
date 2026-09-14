"""Application entry point."""

import sys
import logging
from PyQt6.QtWidgets import QApplication
from config import Config
from ui.main_window import MainWindow

def setup_logging(config: Config) -> None:
    logging_config = config.logging_config
    log_level = logging_config.get("level", "INFO")
    log_file = logging_config.get("file", "migr8lite.log")
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()]
    )

def main() -> None:
    try:
        config = Config()
        setup_logging(config)
        app = QApplication(sys.argv)
        window = MainWindow(config)
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        logging.error(f"Application error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
