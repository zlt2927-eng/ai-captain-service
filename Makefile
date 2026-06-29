.PHONY: help test test-unit test-coverage clean install dev-install lint format

help:
	@echo "AI Captain Service - Development Commands"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  install          Install production dependencies"
	@echo "  dev-install      Install development dependencies"
	@echo "  test             Run all tests"
	@echo "  test-unit        Run unit tests only"
	@echo "  test-coverage    Run tests with coverage report"
	@echo "  test-verbose     Run tests with verbose output"
	@echo "  lint             Run linter (flake8)"
	@echo "  format           Format code (black, isort)"
	@echo "  clean            Clean temporary files"

install:
	pip install -r requirements.txt

dev-install:
	pip install -r requirements-dev.txt

test:
	pytest tests/ -m "not slow"

test-unit:
	pytest tests/unit/ -v

test-coverage:
	pytest tests/ --cov=app --cov-report=html --cov-report=term
	@echo "Coverage report generated in htmlcov/index.html"

test-verbose:
	pytest tests/ -v --tb=long

test-watch:
	pytest-watch tests/ -- -v

lint:
	flake8 app/ tests/ --max-line-length=120 --extend-ignore=E203,W503

format:
	black app/ tests/ --line-length=120
	isort app/ tests/ --profile=black

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name htmlcov -exec rm -rf {} +
	find . -type f -name .coverage -delete
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete