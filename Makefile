SERVICE_NAME := vk_stream
SERVICE_TEMPLATE := config/vk_stream.service
SYSTEMD_PATH := /etc/systemd/system/$(SERVICE_NAME).service
WORKDIR := $(CURDIR)

.PHONY: gen deps venv start stop restart status logs install uninstall enable disable convert-one convert-all

gen:
	./.venv/bin/python -m vk_stream --gen-playlist

convert-one:
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make convert-one FILE=/path/to/file.mkv"; \
		exit 2; \
	fi
	./.venv/bin/python -m vk_stream.convert --one "$(FILE)"

convert-all:
	./.venv/bin/python -m vk_stream.convert --all --delete-original

deps:
	@if ! command -v ffmpeg >/dev/null || ! command -v curl >/dev/null; then \
		apt-get update; \
		apt-get install -y ffmpeg curl ca-certificates; \
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
	@sed "s|__WORKDIR__|$(WORKDIR)|g" $(SERVICE_TEMPLATE) > $(SYSTEMD_PATH)
	systemctl daemon-reload

enable: install
	systemctl enable --now $(SERVICE_NAME)

start: install
	systemctl start $(SERVICE_NAME)

stop:
	systemctl stop $(SERVICE_NAME)

restart: install
	systemctl restart $(SERVICE_NAME)

status:
	systemctl status $(SERVICE_NAME) --no-pager || true

logs:
	journalctl -u $(SERVICE_NAME) -n 200 --no-pager

disable:
	systemctl disable --now $(SERVICE_NAME)

uninstall: disable
	rm -f $(SYSTEMD_PATH)
	systemctl daemon-reload
