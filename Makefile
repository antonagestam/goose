.PHONY: requirements
requirements: export CUSTOM_COMPILE_COMMAND='make requirements'
requirements:
	@uv pip compile --generate-hashes --strip-extras --upgrade requirements.txt
