.PHONY: test

PYTHON ?= python3

test:
	$(PYTHON) -m unittest discover -s tests -v
