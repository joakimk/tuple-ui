.PHONY: default restart help install uninstall

default: restart

restart:
	@bash restart.sh

install:
	pip3 install -e .
	mkdir -p ~/.local/share/applications
	cp tuple-ui.desktop ~/.local/share/applications/
	update-desktop-database ~/.local/share/applications 2>/dev/null || true
	@echo "Installation complete! You can now run 'tuple-ui' from anywhere."
	@echo "The app will appear in your applications menu using the Tuple icon"
	@echo "(reuses the 'tuple' hicolor icon installed by the Tuple CLI)."

uninstall:
	pip3 uninstall -y tuple-ui
	rm -f ~/.local/share/applications/tuple-ui.desktop
	update-desktop-database ~/.local/share/applications 2>/dev/null || true
	@echo "Uninstall complete."

help:
	@echo "Available targets:"
	@echo "  make             - Restart tuple_ui (default)"
	@echo "  make restart     - Restart tuple_ui"
	@echo "  make install     - Install tuple-ui as a system application"
	@echo "  make uninstall   - Uninstall tuple-ui"
	@echo "  make help        - Show this help message"
