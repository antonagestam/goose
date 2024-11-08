# Installation

It's recommended to install Goose via [uvx] or [pipx], and to use the reusable workflow
in Github Actions.

[uvx]: https://github.com/astral-sh/uv#tool-management
[pipx]: https://github.com/pypa/pipx

## Recommended methods

### Via uvx

```shell
uvx install git-goose
```

### Via pipx

```shell
pipx install git-goose
```

### Github Actions

```yaml
name: CI
on:
  push:
    branches: ["main"]
  pull_request:
jobs:
  lint:
    name: Run goose checks
    uses: antonagestam/goose/.github/workflows/run.yaml@main
```

## Alternate methods

### From PyPI

You can install Goose directly from PyPI, but mind it will only ever support a single
Python release, you will need to manually manage upgrading Python this way.

```shell
pip install --require-venv git-goose
```

### From source

This can be useful to try out a development version of Goose.

```shell
pip install --require-venv https://github.com/org/antonagestam/goose/main.tar.gz
```

### As Docker container

Goose also ships a Docker container that you can use. Mind that this currently somewhat
limits the feature set.

```sh
alias goose='docker run --rm -it -v ${PWD}:/wd -v ~/.cache/goose-docker:/home/nonroot/.cache -e "GOOSE_AUGMENTED_CWD=${PWD}" ghcr.io/antonagestam/goose:latest'
```
