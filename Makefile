.PHONY: default restart help

default: restart

restart:
	@bash restart.sh

help:
	@echo "Available targets:"
	@echo "  make           - Restart tuple_ui (default)"
	@echo "  make restart   - Restart tuple_ui"
	@echo "  make help      - Show this help message"
