.PHONY: test lint run build binary

test:
	PYTHONPATH=src pytest

lint:
	ruff check .

run:
	PYTHONPATH=src python -m libbyctl --help

build:
	python -m pip wheel . --no-deps --no-build-isolation -w dist

binary:
	pyinstaller packaging/pyinstaller/libbyctl.spec --noconfirm
