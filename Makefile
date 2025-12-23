SERVICE_NAME := vk_stream
SERVICE_TEMPLATE := config/vk_stream.service
SYSTEMD_PATH := /etc/systemd/system/$(SERVICE_NAME).service
WORKDIR := $(CURDIR)

.PHONY: deps venv install start stop restart status logs enable disable uninstall

deps:
	@if ! command -v ffmpeg >/dev/null || ! command -v obs >/dev/null || ! command -v vlc >/dev/null; then \
		apt-get update; \
		apt-get install -y ffmpeg vlc obs-studio xvfb pulseaudio pulseaudio-utils xauth curl ca-certificates; \
	fi

venv:
	@export PATH="$$HOME/.local/bin:$$PATH"; \
	if ! command -v uv >/dev/null; then \
		echo "uv not found, installing..."; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	fi; \
	if ! command -v uv >/dev/null; then \
		echo "uv still not found in PATH"; exit 1; \
	fi; \
	if [ ! -d ".venv" ]; then \
		uv venv; \
	else \
		echo ".venv already exists, skipping uv venv"; \
	fi; \
	uv pip install -e .

install: deps venv
	@chmod +x $(WORKDIR)/bin/run_obs.sh
	@sed "s|__WORKDIR__|$(WORKDIR)|g" $(SERVICE_TEMPLATE) > $(SYSTEMD_PATH)
	systemctl daemon-reload

enable: install
	systemctl enable --now $(SERVICE_NAME)

start: install
	@if systemctl is-active --quiet $(SERVICE_NAME); then \
		systemctl restart $(SERVICE_NAME); \
	else \
		systemctl start $(SERVICE_NAME); \
	fi

stop:
	systemctl stop $(SERVICE_NAME)

restart: start

status:
	systemctl status $(SERVICE_NAME) --no-pager || true

logs:
	journalctl -u $(SERVICE_NAME) -n 200 --no-pager

disable:
	systemctl disable --now $(SERVICE_NAME)

uninstall: disable
	rm -f $(SYSTEMD_PATH)
	systemctl daemon-reload
