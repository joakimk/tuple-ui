.PHONY: default restart help install uninstall

default: restart

restart:
	@bash restart.sh

install:
	pip3 install -e .
	mkdir -p ~/.local/share/icons/hicolor/256x256/apps
	mkdir -p ~/.local/share/applications
	python3 -c "import urllib.request; urllib.request.urlretrieve('https://tuple.app/favicon.ico', '$(HOME)/.local/share/icons/hicolor/256x256/apps/tuple-ui.ico')" || echo "Warning: Could not download icon, continuing without it"
	cp tuple-ui.desktop ~/.local/share/applications/
	@echo "Installation complete! You can now run 'tuple-ui' from anywhere."
	@echo "The app will appear in your applications menu."

uninstall:
	pip3 uninstall -y tuple-ui
	rm -f ~/.local/share/icons/hicolor/256x256/apps/tuple-ui.ico
	rm -f ~/.local/share/applications/tuple-ui.desktop
	@echo "Uninstall complete."

help:
	@echo "Available targets:"
	@echo "  make             - Restart tuple_ui (default)"
	@echo "  make restart     - Restart tuple_ui"
	@echo "  make install     - Install tuple-ui as a system application"
	@echo "  make uninstall   - Uninstall tuple-ui"
	@echo "  make help        - Show this help message"
