<h1 align=center>goose 🦆</h1>

<p align=center>A <i>picky</i> and <i>eager</i> <a href=https://git-scm.com/book/en/v2/Customizing-Git-Git-Hooks>Git hook</a> runner.</p>

### Features

- Smart parallelism schedules hooks across CPUs while avoiding concurrent writes.
- Deterministic environments by using ecosystem-specific lock files.
- Share environments across hooks.
- Self-contained hook definitions makes sure there's no need to push tool-specific
  configuration upstream, or to create elaborate repository mirroring schemes.

### Parallelism

Goose takes care to keep your CPUs as busy as possible, optimizing to have the full
suite of hooks finish as soon as possible. It does this by distributing units of work to
all available processing cores.

Parameterized hooks, or hooks that take files as command line arguments, are divided to
one unit of work per available core. Whenever a core becomes available for more work, a
new unit is chosen for execution.

The scheduler takes care to never run more than one mutating hook on the same file. It
does this by taking into account hooks marked as `read_only` and by comparing sets of
files a unit of work is assigned to. Two incompatible hooks can be simultaneously
working on two separate parts of the code-base.

### Deterministic environments

Goose uses lock files to facilitate deterministic results across developer environments
and CI. You specify dependencies in `goose.yaml`, and invoking `goose run` will produce
the appropriate lock files under a `.goose/` directory. The `.goose/` directory is meant
to be checked into git, so that future invocations of `goose run` can use the lock files
it contains to produce identical environments for hooks to run in.

## Usage

Create a `goose.yaml` file in your repository root.

```yaml
version: 0

exclude:
  - ^\.goose/.*

environments:
  - id: python
    ecosystem:
      language: python
      version: "3.12"
    dependencies:
      - ruff

hooks:
  - id: ruff
    environment: python
    command: ruff
    args: [check, --force-exclude, --fix]
    types: [python]

  - id: ruff-format
    environment: python
    command: ruff
    args: [format]
    types: [python]
```

Make an initial run over all files in the repository.

```sh
$ python -m goose run --select=all
```

Then add the configuration and lock files to git.

```sh
$ git add goose.yaml .goose
$ git commit -m 'Add goose configuration'
```

### Upgrading hook versions

As pinning of hook versions is handled with lock files, there's no need to change
configuration to upgrade hook dependency versions, instead you just run the upgrade
command.

```sh
$ python -m goose upgrade
$ git add .goose
$ git commit -m 'Bump goose dependencies'
```

### Todo

- [x] Pass filenames
- [x] Configurably do not pass filenames
- [x] File types
- [x] Global exclude patterns
- [x] Hook level exclude patterns
- [x] Hook parallelism
  - Within hook
  - Across hooks
- [x] Only changed files
- [x] Run on all files
- [ ] Git hook installation
- [x] Run single hook
- [x] Exit 0 on fail
- [ ] Write output to buffers, dump to stdout/err on error only
- [x] Rich-based visualization of running units as table
