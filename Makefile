.PHONY: install test lint format build-feed

install:
	poetry install

test:
	poetry run python -m unittest discover -s tests -p "test_*.py" -v

build-feed:
	poetry run python build_feed.py --output feeds/hacker-news.xml

lint:
	python -m compileall src build_feed.py

format:
	@echo "No formatter configured. Add black/isort if desired."
