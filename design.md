# HyFS Design Document
> formerly called fsxp

## Overview
HyFS (FileSystem eXPlorer) is a Python-based filesystem management tool built on fastcore principles. It provides a tree-based representation of filesystem structures with stable entity identification, designed for interactive exploration, filtering, and eventual manipulation.

## Core Philosophy

### Principle of Lean Information Form (LIF)
Information must be expressed in its meaningful form, preserving integrity without requiring decoders. We store semantic structure directly, then decide display independently. This means:
- Organize as objects, lists, or indented structures—always fully meaningful
- No ASCII art for tree branches (`├──`, `└──`)—these are display concerns, not data
- When we `pathlib.Path()` the filesystem, we store what we find properly, then display separately

### LIF Lemma 1: Separation of Tagging and Nesting
Item tagging (atomic, category-based) and tree nesting (path-based hierarchy) are separate concerns:
- Don't store tags inside tree structure—keep them separate (dict mapping paths to tag sets, or metadata layer)
- Tags are many-to-many; trees are one-to-many
- Decide early: filesystem metadata (xattrs) or application-level (separate file/db)
- xattrs are portable but platform-dependent; app-level is consistent but not universal

### The fastcore Way
Methods return transformed data when possible, enabling chaining. `filter()` returns a new structure (or `L` of nodes), not print output. This separates data transformation from presentation.

### Make Side Effects Explicit and Deferrable
Inspired by Git's staging area, ZFS transactions, and the Command Pattern:
- **Read operations**: Immediate (work directly on tree snapshot)
- **Write operations**: Return a Plan/Transaction object that can be inspected, then executed
- Example: `plan = node.rename('newname')` → `plan.preview()` → `plan.execute()`
- This provides safety, composability, and clear boundaries between observation and mutation

## Architecture Decisions

### Data Structure: AttrDict + Path Composition
**Choice**: FSNode as AttrDict subclass, with Path objects as values
```python
{'path': Path('/app/data'), 'type': 'dir', 'children': [...]}
```

**Why**:
- Clean separation: AttrDict handles tree structure, Path handles filesystem operations
- Dual access: `node.path` (attribute) and `node['path']` (dict) both work
- Composable: Leverage both APIs fully without fighting immutability
- REPL-friendly: Tab completion works on attributes

**Rejected alternatives**:
- Subclassing Path: Fights Path's immutability, adds complexity
- Plain dicts: Loses ergonomic attribute access
- Custom tree node classes: More ceremony, less flexibility

### Tree Building: Lazy and Recursive
```python
def build_tree(path):
    p = Path(path)
    if p.is_file():
        return {'path': p, 'type': 'file'}
    children = [build_tree(child) for child in p.iterdir()]
    return {'path': p, 'type': 'dir', 'children': children}
```

**Why**:
- Simple recursion mirrors filesystem structure naturally
- Returns plain dicts, converted to FSNode via `dict2obj(build_tree(path), dict_func=FSNode)`
- Fast: No metadata collection upfront, only structure
- Extensible: Easy to add fields later

### Metadata: Lazy Properties
**Choice**: Properties like `eid`, `size`, `mtime` accessed on-demand via `@property`

**Why**:
- Pay-as-you-go: Don't stat() 100K files if you only need 50
- Scales better: Building tree with metadata upfront would add 20+ seconds for 1M files
- Most use cases filter first, then access metadata on subset
- Can add `@cached_property` later if repeated access becomes bottleneck

**Threshold analysis**:
- 10K files: Upfront metadata = 200ms (negligible), but lazy still better for partial queries
- 100K files: Upfront = 2s (noticeable), lazy = instant build + selective stats
- 1M files: Upfront = 20s+ (painful), lazy = <1s build

### Entity Identification: UUID with xattr Storage

**Concept**: Every node (file or directory) gets a stable `eid` (Entity ID)

**Why `eid` not `fid`/`nid`**:
- Directories are entities too—structure has semantic meaning before files exist
- `fid` (file ID) excludes directories
- `nid` (node ID) too bound to filesystem concept (inode)
- `eid` sits at perfect abstraction: generic enough for any representation, specific enough to be meaningful
- Conceptual hierarchy: `cid` (content) → `eid` (entity/metadata) → `nid` (filesystem-specific)

**Storage strategy**:
1. Try to read UUID from xattr `user.hyfs.uuid`
2. If missing, generate UUID v4 (v7 not yet in Python stdlib)
3. Try to store in xattr
4. If xattr fails (unsupported fs, permissions), fall back to deterministic hash of `(st_dev, st_ino, st_mtime)`

**xattr tradeoffs**:
- **Pros**: Atomic with file, survives renames within filesystem, standard POSIX
- **Cons**: Lost on cloud sync, zip, basic copy; not supported on FAT32/exFAT
- **Acceptable**: For SolveIT use case (Linux containers, modern fs), works 95% of time

**Why not inode-only**:
- Inodes change across filesystems (USB, network, backups)
- Need identity to persist across hosts for multi-instance SolveIT usage
- UUID provides stable identity even when filesystem metadata changes

### The AttrDict Property Problem

**Challenge**: AttrDict's `__getattr__` intercepts attribute access, checking dict keys before class properties. This breaks `@property` decorators.

**Solution**: Override `__getattribute__` to check class properties first:
```python
class FSNode(AttrDict):
    def __getattribute__(self, key):
        cls = object.__getattribute__(self, '__class__')
        if key in cls.__dict__ and isinstance(cls.__dict__[key], property):
            return cls.__dict__[key].fget(self)
        return super().__getattribute__(key)
```

**Critical detail**: Use `@property` + manual attachment (`FSNode.eid = eid`), not `@patch(as_prop=True)`. The latter doesn't work with our `__getattribute__` override.

**Naming conflicts avoided**:
- `id` → conflicts with Python builtin
- `uuid` → conflicts with imported module
- `uid` → conflicts with User ID concept
- Final choice: `eid` (mnemonic: D→E←F, between directories and files)

## Method Design

### `show(indent=0)`: Tree Display
Recursive print with indentation. Simple, effective MVP. Future: add depth limiting, icons, colors.

### `filter(pred)`: Flat List of Matches
```python
@patch
def filter(self:FSNode, pred):
    matches = L()
    if pred(self): matches.append(self)
    if self.type == 'dir':
        for child in self.children:
            matches += child.filter(pred)
    return matches
```

**Returns**: Flat `L` (fastcore list) of nodes matching predicate

**Why flat, not tree**:
- Unix philosophy: `find` outputs paths, not trees
- Composable: Easy to operate on results
- Separate concern from `prune()` (future: tree with only matching branches)

### `find(pattern)`: Glob Pattern Matching
```python
@patch
def find(self:FSNode, pattern):
    return self.filter(lambda n: fnmatch(n.path.name, pattern))
```

One-liner convenience wrapper. Uses `fnmatch` for shell-style globs (`*.py`, `test_*`).

## Development Principles

### Vertical Space Efficiency
- Favor one-liners where clarity isn't sacrificed
- Imports at top (no lazy imports unless heavy deps)
- `@patch` for adding methods to classes

### Fastcore Alignment
- Use `L` for lists (chainable, better defaults)
- Use `AttrDict` for dict-with-attributes
- Use `@patch` to extend classes
- Leverage `dict2obj` for recursive AttrDict conversion

### Jeremy Howard's Design Process
- Start simple, iterate toward elegance
- REPL-driven development: optimize for tab completion, exploration
- Composability over monolithic features
- "Do one thing well" (Unix philosophy)

### What We Avoid
- Premature optimization (measure first)
- Mixing concerns (filter ≠ display)
- ASCII art in data structures
- Schema-heavy approaches (dataclasses for dynamic data)
- Ceremony (favor terse, clear code)

## Code Style

### Naming
- Short where unambiguous: `eid`, `L`, `pred`
- Explicit where needed: `build_tree`, `dict2obj`
- Unix-inspired: `find`, `filter`, `show`

### Structure
1. Imports
2. Class definitions
3. Methods (via `@patch`)
4. Functions
5. Usage/tests

### Comments
- Docstrings for public methods
- Inline comments for non-obvious logic
- No redundant comments explaining obvious code

## Future Directions

### Immediate Next Steps
1. Add `prune()` for structural filtering (tree with only matching branches + ancestors)
2. Add metadata properties: `size`, `mtime`, `permissions`
3. Add navigation: `parent`, `find_by_path`, depth limiting

### Medium Term
1. Write operations: `rename()`, `move()`, `copy()` returning Plan objects
2. Content operations: `read()`, `write()` with sed-like transforms
3. Tagging system (separate from tree structure)

### Long Term
1. Distributed filesystem index (multi-host UUID tracking)
2. Semantic relationships (parent/child beyond filesystem hierarchy)
3. Integration with nbdev, SolveIT dialog management
4. CLI tool with FastHTML web interface

## Lessons Learned

### AttrDict + Properties
AttrDict wasn't designed for class properties. Our `__getattribute__` override works but is a workaround. For future: consider if fastcore could add property support, or if we should use a different base class.

### UUID Version Drama
Python 3.12 doesn't have uuid7 yet (still in discussion). uuid4 is fine for our needs, easy to migrate later.

### xattr Portability
xattrs work great on modern Linux/macOS but fail on many consumer scenarios (cloud sync, FAT32). Deterministic fallback is essential. Future: consider sidecar metadata files for persistent tracking.

### Debugging Strategy
When stuck: strip to vanilla Python, verify concept works, then incrementally add complexity. Our AttrDict property issue was solved by testing with `SimpleNode` first.

## Meta: How We Work

- **Incremental understanding**: Build simple examples to grasp concepts before implementing
- **Question assumptions**: "Why doesn't this exist?" often reveals antipatterns or limitations
- **Book-quality prose**: Dense paragraphs over blog-style bullet points for deep insights
- **Design before code**: Understand tradeoffs, then implement decisively
- **Prototype as we design**: PoC validates decisions immediately

This is a living document. Update as HyFS evolves.
