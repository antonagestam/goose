# goose 🦆

### Features

- Smart parallelism schedules hooks across CPUs while avoiding concurrent writes.
- Deterministic environments by using ecosystem-specific lock files.
- Share environments across hooks.

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
