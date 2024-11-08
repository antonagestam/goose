.PHONY: requirements
requirements: export CUSTOM_COMPILE_COMMAND='make requirements'
requirements:
	@uv pip compile --generate-hashes --strip-extras --upgrade --output-file=requirements.txt pyproject.toml
	@uv pip compile --generate-hashes --strip-extras --extra=test --upgrade --constraint=requirements.txt --output-file=requirements-test.txt pyproject.toml
	@uv pip compile --generate-hashes --strip-extras --extra=docs --upgrade --constraint=requirements.txt --output-file=requirements-docs.txt pyproject.toml
