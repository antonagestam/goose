<h1 align=center>goose 🦆</h1>

<p align=center>A <i>picky</i> and <i>eager</i> <a href=https://git-scm.com/book/en/v2/Customizing-Git-Git-Hooks>Git hook</a> runner.</p>

### Features

- Smart parallelism schedules hooks across CPUs while avoiding concurrent writes.
- Deterministic environments by using ecosystem-specific lock files.
- Share environments across hooks.

### Parallelism

Goose takes care to keep your CPUs as busy as possible. It does this by distributing units of work to all processing cores. 

Parameterized hooks, or hooks that take files as command line arguments, are divided to one unit of work per available core. Whenever a core becomes available for more work, a new unit is chosen for execution.

The scheduler takes care to never run more than one mutating hook on the same file. It does this by taking into account hooks marked as `read_only` and by comparing sets of files a unit of work is assigned to. Two incompatible hooks can be simultaneously working on two separate parts of the code-base.

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
