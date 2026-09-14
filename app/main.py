"""Application entry point."""

import sys
import logging
from PyQt6.QtWidgets import QApplication
from app.config import Config
from app.ui.main_window import MainWindow


def setup_logging(config: Config) -> None:
    """Set up application logging."""
    logging_config = config.logging_config
    log_level = logging_config.get("level", "INFO")
    log_file = logging_config.get("file", "migr8lite.log")
    
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )


def main() -> None:
    """Main application entry point."""
    try:
        # Load configuration
        config = Config()
        setup_logging(config)
        
        # Create Qt application
        app = QApplication(sys.argv)
        
        # Create and show main window
        window = MainWindow(config)
        window.show()
        
        # Run application
        sys.exit(app.exec())
    
    except Exception as e:
        logging.error(f"Application error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
