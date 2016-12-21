CWD="`pwd`"
PROJECT_NAME = vault
PROJECT_HOME = $(CWD)

clean: ## Clear *.pyc files, etc
	@echo "Cleaning up *.pyc files"
	@find . -name "*.pyc" -delete
	@find . -name "*.~" -delete

pep8: ## Check source-code for PEP8 compliance
	@echo "Checking source-code PEP8 compliance"
	@-pep8 $(PROJECT_HOME) --ignore=E501,E126,E127,E128

tests: clean pep8 ## Run pep8 and all tests with coverage
	@echo "Running pep8 and all tests with coverage"
	@py.test --cov-config .coveragerc --cov $(PROJECT_HOME) --cov-report term-missing
