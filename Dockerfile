FROM python:3.13.0-bookworm AS build

ARG RELEASE_VERSION="dev"
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_GIT_GOOSE=$RELEASE_VERSION

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PIP_REQUIRE_VIRTUALENV true
ENV PIP_VERSION 24.2
ENV SETUPTOOLS_VERSION 75.2.0
ENV WHEEL_VERSION 0.44.0
# Permanently activate virtualenv.
ENV PATH="/venv/bin:$PATH"

# Build requirements.
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,readwrite,source=.,target=/app-src \
    set -eux \
 && python -m venv /venv \
 && pip install \
      pip==$PIP_VERSION \
      setuptools==$SETUPTOOLS_VERSION \
      wheel==$WHEEL_VERSION \
 && pip install \
      --only-binary=:all: \
      --no-dependencies \
      --require-hashes \
      -r /app-src/requirements.txt \
 && pip install --no-dependencies /app-src \
 && pip check

FROM python:3.13.0-slim-bookworm AS final

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
