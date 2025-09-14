FROM ghcr.io/astral-sh/uv:python3.13-bookworm AS build

ARG RELEASE_VERSION="dev"
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_GIT_GOOSE=$RELEASE_VERSION

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
# Permanently activate virtualenv.
ENV PATH="/venv/bin:$PATH"

# Build requirements.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,readwrite,source=.,target=/app-src \
    set -eux \
 && uv venv \
      --no-project \
      --python-preference=only-system \
      /venv \
 && uv pip install \
      --python=/venv/bin/python \
      --only-binary=:all: \
      --no-deps \
      --require-hashes \
      -r /app-src/requirements.txt \
 && uv pip install \
      --python=/venv/bin/python \
      --no-deps \
      /app-src \
 && uv pip check --python=/venv/bin/python

FROM python:3.13.7-slim-bookworm AS final

ARG UID="1000"
ARG GID="1000"
ENV PYTHONUNBUFFERED 1
ENV HOME "/home/nonroot/"

# Install git
WORKDIR /wd
RUN apt update --yes \
 && apt install --yes git

# Permanently activate virtualenv.
ENV PATH="/venv/bin:$PATH"
COPY --from=build /venv /venv

RUN addgroup --gid $GID nonroot \
 && adduser --uid $UID --gid $GID --disabled-password --gecos "" nonroot \
 && echo 'nonroot ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers \
 && mkdir -p /home/nonroot/.cache \
 && chown nonroot:nonroot /home/nonroot/.cache \
 && git config --system safe.directory '*'
VOLUME "$HOME/.cache"
USER "$UID:$GID"

ENTRYPOINT ["python", "-m", "goose"]
CMD ["run"]
