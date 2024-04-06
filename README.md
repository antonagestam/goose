<h1 align=center>goose<br>🦆🧪💻</h1>

<p align=center>A <i>picky</i> and <i>eager</i> <a href=https://git-scm.com/book/en/v2/Customizing-Git-Git-Hooks>Git hook</a> runner.</p>

- Reproducible builds.
- Dynamic parallelism.
- Small file-system footprint.

### Features

- Smart parallelism schedules hooks across CPUs while avoiding concurrent writes.
- Deterministic environments by using ecosystem-specific lock files.
- Environments are shared across hooks.
- Self-contained definitions means there's no need to push tool-specific configuration
  upstream, or to maintain brittle mirroring schemes.

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

Create a `goose.yaml` file in the repository root.

```yaml
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
    args: [format, --force-exclude]
    types: [python]
```

Bootstrap environments, generate lock files, and install dependencies.

```sh
$ python -m goose upgrade
```

Run all hooks over all files.

```sh
$ python -m goose run --select=all
```

Commit configuration and lock files.

```sh
$ git add goose.yaml .goose
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

### Example node hook

Goose currently supports Python and Node environments, here's an example using
[Prettier] to format Markdown files.

[Prettier]: https://prettier.io/

```yaml
environments:
  - id: node
    ecosystem:
      language: node
      version: "21.7.1"
    dependencies:
      - prettier

hooks:
  - id: prettier
    environment: node
    command: prettier
    types: [markdown]
    args:
      - --write
      - --ignore-unknown
      - --parser=markdown
      - --print-width=88
      - --prose-wrap=always
```

### Read-only hooks

You will likely want to use a mix of pure linters, as well as formatters and
auto-fixers. Tools that don't mutate files can be more heavily parallelized by Goose,
because they can inspect overlapping sets of files simultaneously as other tools. To
enable this you set `read_only: true` in hook configuration.

```yaml
environments:
  - id: python
    ecosystem:
      language: python
      version: "3.12"
    dependencies:
      - pre-commit-hooks

hooks:
  - id: check-case-conflict
    environment: python
    command: check-case-conflict
    read_only: true

  - id: check-merge-conflict
    environment: python
    command: check-merge-conflict
    read_only: true
    types: [text]

  - id: python-debug-statements
    environment: python
    command: debug-statement-hook
    read_only: true
    types: [python]

  - id: detect-private-key
    environment: python
    command: detect-private-key
    read_only: true
    types: [text]

  - id: end-of-file-fixer
    environment: python
    command: end-of-file-fixer
    types: [text]

  - id: trailing-whitespace-fixer
    environment: python
    command: trailing-whitespace-fixer
    types: [text]
```

Hooks that do not specify `read_only: true` will never run simultaneously as other tools
over the same file.

### Non-parameterized hooks

Some tools don't support passing files, or just work better if given the responsibility
to parallelize work itself. One such tool is mypy. You can instruct goose to not pass
filenames to a hook (and as a consequence, also not spawn multiple parallel jobs for
this hook).

```yaml
environments:
  - id: mypy
    ecosystem:
      language: python
      version: "3.12"
    dependencies:
      - mypy

hooks:
  - id: mypy
    environment: mypy
    command: mypy
    read_only: true
    parameterize: false
```

### Todo

- [ ] Git hook installation
- [ ] Proper hook integration. There's some complexity in figuring out which delta to
      run on.
  - In pre-push. How do we figure out what to run on without assuming what the default
    branch/target branch is ...
  - In pre-commit.
  - When invoked in a dev env (although I think pre-commit just runs on whatever is
    staged ...).
- [ ] Write output to buffers, dump to stdout/err on error only In CI, we don't want to
      be silently overwriting lock files.
- [ ] `until_complete()` could be improved to generate _type_ of event, such as
      "spawned", "finished". In non-tty, this could be used to print unfancy text
      output.
- [x] ⚠️ Error on changed files.
  - Need to capture this locally per unit. Gather state of all targets before-hand and
    after each executed unit. Will be interesting for performance.
- [ ] Option to print git diff on failure.
- [ ] Weigh file chunk distribution based on previous runs.
  - Store score in root envs directory.
  - Use something like 50% from last value.
    ```
    stored = last run _ .5 + existing _.5
    ```
- [ ] Generate default id from command and args (simplify most configs).
