.PHONY: requirements
requirements: export CUSTOM_COMPILE_COMMAND='make requirements'
requirements:
	@pip-compile --allow-unsafe
