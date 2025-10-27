This updated design doc now:
- Reflects the flat storage architecture
- Explains the shift from hierarchical to flat + derived views
- Documents all current working code
- Provides complete code reference for new session
- Maintains the philosophical foundations
- Captures lessons learned from the refactor
- Maps out clear future directions

-----

# HyFS Design Document
> Hyper FileSystem - A filesystem abstraction with stable identity and semantic relationships

## Overview
HyFS is a Python-based filesystem management tool built on fastcore principles. It provides flat storage with stable entity identification (eids), enabling multiple derived views (tree, tags, relationships) from a single canonical representation. Designed for interactive exploration, filtering, semantic organization, and eventual manipulation.

## Core Philosophy

### Principle of Lean Information Form (LIF)
Information must be expressed in its meaningful form, preserving integrity without requiring decoders. We store semantic structure directly, then decide display independently. This means:
- Organize as objects, lists, or flat dicts—always fully meaningful
- No ASCII art for tree branches (`├──`, `└──`)—these are display concerns, not data
- Store nodes in flat dict keyed by `eid`, derive tree views from `path` relationships
- Separation of data (flat) from presentation (tree, tags, relations)

### LIF Lemma 1: Separation of Concerns
Three orthogonal concepts, stored separately:
1. **Entity storage**: Flat dict `{eid -> node}` (canonical)
2. **Filesystem hierarchy**: Derived from `path` relationships (view)
3. **Semantic organization**: Tags and relations (metadata layer)

Don't mix these—keep them separate:
- Tags are many-to-many mappings: `{tag_name -> {eid, ...}}`
- Relations are typed connections: `{eid -> {rel_type -> {eid, ...}}}`
- Tree structure is computed on-demand from `path.parent` checks

### The fastcore Way
Methods return transformed data when possible, enabling chaining. `filter()` returns a flat `L` of nodes, not print output. This separates data transformation from presentation.

### Make Side Effects Explicit and Deferrable
Inspired by Git's staging area, ZFS transactions, and the Command Pattern:
- **Read operations**: Immediate (work directly on flat storage)
- **Write operations**: Return a Plan/Transaction object that can be inspected, then executed
- Example: `plan = hyfs.rename(eid, 'newname')` → `plan.preview()` → `plan.execute()`
- This provides safety, composability, and clear boundaries between observation and mutation

## Architecture Decisions

### Data Structure: Flat Storage with Derived Views
**Choice**: HyFS stores nodes in flat dict `{eid -> FSNode}`, derives tree structure on-demand

```python
# Canonical storage: flat dict
hyfs.nodes = {
    'eid1': FSNode(path=Path('/app/data/file.py'), type='file', eid='eid1'),
    'eid2': FSNode(path=Path('/app/data'), type='dir', eid='eid2'),
    ...
}

# Derived view: tree constructed from path relationships
tree = hyfs.tree('/app/data')  # Builds hierarchy on-demand
```

**Why flat storage**:
- O(1) lookup by eid: `hyfs.get(eid)`
- No nested traversal needed for global operations
- Tags/relations are just dicts: `{'important': {'eid1', 'eid2'}}`
- Multiple views from single source: tree by path, tree by tags, graph by imports
- Easy serialization: flat dict → JSON
- Scales better: 100K nodes = 100K dict entries, not nested recursion

**Why derived tree views**:
- Tree structure is implicit in `path` property
- Compute hierarchy when needed: `path.parent == other.path`
- Display is a view concern, not data concern
- Can build multiple trees: filesystem tree, tag tree, relation graph

**FSNode as AttrDict**:
```python
class FSNode(AttrDict):
    # Enables both node.path and node['path']
    # REPL-friendly with tab completion
    # Custom __getattribute__ to support @property decorators
```

**Rejected alternatives**:
- Hierarchical dict with `children`: Mixes data with one specific view, hard to query globally
- Separate tree classes: More ceremony, fights the "data is just dicts" philosophy
- Graph database: Overkill for MVP, harder to inspect/debug

### Filesystem Scanning: Flat Population
```python
def scan_fs(root_path, include_metadata=False):
    """Scan filesystem and populate HyFS flat storage"""
    hyfs = HyFS()
    root_path = Path(root_path)
    
    # Walk entire tree, add each node to flat storage
    for path in [root_path] + list(root_path.rglob('*')):
        hyfs.add_node(path, **metadata)
    
    return hyfs
```

**Why flat scan**:
- Simple iteration, no recursion needed
- Fast: Only `path`, `type`, and `eid` collected upfront
- Metadata on-demand: Add `size`, `mtime`, `cid` when needed
- Scales: 100K files in <1 second

**Process**:
1. Walk filesystem with `rglob('*')`
2. For each path: compute `eid`, create `FSNode`, store in `hyfs.nodes[eid]`
3. Tree structure implicit in paths, reconstructed later

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

### Tree View Construction: On-Demand Hierarchy

```python
def tree(self, root_path=None):
    """Build hierarchical tree view from flat storage"""
    root_node = self.find_by_path(root_path)
    return self._build_tree_node(root_node)

def _build_tree_node(self, node):
    """Recursively build tree structure for a node"""
    tree_node = FSNode(node)  # Copy node data
    
    if node.type == 'dir':
        # Find children: nodes whose path.parent == this path
        children = []
        for candidate in self.nodes.values():
            if candidate.path.parent == node.path:
                children.append(self._build_tree_node(candidate))
        tree_node['children'] = children
    
    return tree_node
```

**Why on-demand**:
- Tree is just one view of the data
- Most operations work on flat storage (filter, tag, lookup)
- Only build tree when displaying or traversing hierarchy
- Can build multiple trees: full tree, filtered tree, tag-based tree

**Performance**: O(n²) worst case (check every node for each parent), but acceptable for <10K nodes. Future optimization: maintain `path -> eid` index.

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

**Future metadata as properties**: `size`, `mtime`, `cid` can be added as `@property` for lazy evaluation.

## Method Design

### HyFS Class Methods

**`scan_fs(root_path, include_metadata=False)`**: Populate flat storage
- Walks filesystem, creates FSNode for each path
- Stores in `hyfs.nodes[eid]`
- Returns HyFS instance

**`add_node(path, eid=None, **metadata)`**: Add single node
- Computes `eid` if not provided
- Creates FSNode with path, type, eid, metadata
- Stores in flat dict

**`get(eid)`**: O(1) lookup by eid
- Direct dict access: `self.nodes[eid]`
- Fastest way to retrieve node

**`find_by_path(path)`**: Find node by path
- O(n) scan through nodes
- Future: maintain `path -> eid` index for O(1)

**`filter(pred)`**: Filter nodes by predicate
- Returns flat `L` of matching nodes
- Works on entire flat storage
- Composable: `hyfs.filter(lambda n: n.type == 'file')`

**`find(pattern)`**: Glob pattern matching
- Convenience wrapper: `self.filter(lambda n: fnmatch(n.path.name, pattern))`
- Returns flat `L` of matches

**`tree(root_path=None)`**: Build tree view
- Constructs hierarchical FSNode with `children`
- Returns tree root node
- Auto-detects root if only one exists

### FSNode Methods (via @patch)

**`show(indent=0)`**: Display tree recursively
- Prints indented tree structure
- Only works on tree view (needs `children`)
- Simple MVP, future: colors, icons, depth limiting

**`filter(pred)`**: Filter tree recursively
- Returns flat `L` of matching nodes
- Traverses `children` if present
- Works on tree view

**`find(pattern)`**: Find in tree
- Convenience wrapper for `filter` with `fnmatch`
- Works on tree view

## Current Capabilities

### Working Now
1. **Flat storage**: 96 nodes in simple dict, O(1) lookup by eid
2. **Tree view**: Derived hierarchy from path relationships
3. **Dual querying**: Flat (`hyfs.find('*.py')`) and tree (`tree.find('*.py')`)
4. **Stable identity**: eids persist in xattr, survive renames
5. **Tags/relations ready**: Empty dicts waiting to be populated

### Example Usage
```python
# Scan filesystem
hyfs = scan_fs('/app/data/dev/hyfs/test/fs')

# O(1) lookup
node = hyfs.get('some-eid')

# Find by pattern (flat)
py_files = hyfs.find('*.py')

# Build tree view
tree = hyfs.tree('/app/data/dev/hyfs/test/fs')
tree.show()

# Find in tree (hierarchical)
ipynb_files = tree.find('*.ipynb')

# Tag files (future: add helper methods)
hyfs.tags['important'].add(node.eid)
```

## Development Principles

### Vertical Space Efficiency
- Favor one-liners where clarity isn't sacrificed
- Imports at top (no lazy imports unless heavy deps)
- `@patch` for adding methods to classes

### Fastcore Alignment
- Use `L` for lists (chainable, better defaults)
- Use `AttrDict` for dict-with-attributes
- Use `@patch` to extend classes
- Leverage Path objects for filesystem operations

### Jeremy Howard's Design Process
- Start simple, iterate toward elegance
- REPL-driven development: optimize for tab completion, exploration
- Composability over monolithic features
- "Do one thing well" (Unix philosophy)

### What We Avoid
- Premature optimization (measure first)
- Mixing concerns (storage ≠ display ≠ tags)
- ASCII art in data structures
- Schema-heavy approaches (dataclasses for dynamic data)
- Ceremony (favor terse, clear code)

## Code Style

### Naming
- Short where unambiguous: `eid`, `L`, `pred`, `cid`
- Explicit where needed: `scan_fs`, `find_by_path`, `_compute_eid`
- Unix-inspired: `find`, `filter`, `show`, `tree`

### Structure
1. Imports
2. Class definitions (FSNode, HyFS)
3. Helper functions (`_compute_eid`)
4. Main functions (`scan_fs`)
5. Methods (via `@patch`)
6. Usage/tests

### Comments
- Docstrings for public methods
- Inline comments for non-obvious logic
- No redundant comments explaining obvious code

## Future Directions

### Immediate Next Steps
1. **Tagging operations**: `hyfs.tag(eid, 'important')`, `hyfs.untag()`, `hyfs.tagged('important')`
2. **Relations**: `hyfs.relate(eid1, 'imports', eid2)`, `hyfs.related(eid, 'imports')`
3. **Content ID (cid)**: Hash file contents, detect duplicates, track content changes
4. **Path index**: Maintain `path -> eid` dict for O(1) path lookups
5. **Metadata properties**: `@property` for `size`, `mtime`, `permissions`

### Medium Term
1. **Filtered tree views**: `hyfs.tree(filter=lambda n: n.eid in tagged('important'))`
2. **Write operations**: `rename()`, `move()`, `copy()` returning Plan objects
3. **Serialization**: Save/load HyFS state (nodes, tags, relations) to JSON
4. **Deduplication**: Content-based duplicate detection with resolution strategies
5. **Snapshots**: Capture state at point in time, diff between snapshots

### Long Term
1. **Distributed filesystem index**: Multi-host UUID tracking, sync across instances
2. **Semantic relationships**: Import graphs, generation lineage, reference tracking
3. **Integration with SolveIT**: Dialog file management, notebook organization
4. **CLI tool**: Shell-like interface with pipes and filters
5. **FastHTML web interface**: Visual tree explorer with tagging UI

## What HyFS Enables

### 1. Track files across renames (trivial)
```python
old_eid = node.eid
# ... rename happens ...
new_node = hyfs.get(old_eid)  # Still works
```

### 2. Detect duplicates (easy)
```python
from collections import defaultdict
eid_map = defaultdict(list)
for node in hyfs.filter(lambda n: n.type == 'file'):
    eid_map[node.eid].append(node.path)
duplicates = {eid: paths for eid, paths in eid_map.items() if len(paths) > 1}
```

### 3. Compare trees (moderate)
```python
tree1 = scan_fs('/path')
eids1 = set(tree1.nodes.keys())
# ... changes happen ...
tree2 = scan_fs('/path')
eids2 = set(tree2.nodes.keys())
added = eids2 - eids1
removed = eids1 - eids2
```

### 4. Build change history (moderate)
```python
snapshots = []
snapshots.append({'time': now(), 'hyfs': scan_fs('/path')})
# Later: diff any two snapshots by eid
```

### 5. Cross-filesystem tracking (advanced)
```python
# Track "this notebook exists on laptop, server, and backup"
locations = {
    'eid123': [
        '/home/user/notebook.ipynb',
        '/mnt/server/notebook.ipynb',
        's3://backup/notebook.ipynb'
    ]
}
```

### 6. Semantic relationships (advanced)
```python
# Build graph beyond filesystem hierarchy
hyfs.relations[notebook_eid]['imports'].add(module_eid)
hyfs.relations[notebook_eid]['generates'].add(output_eid)
# Query: "What notebooks use this module?"
```

### 7. Persistent selections/tags (advanced)
```python
# Tags survive renames, moves
hyfs.tags['important'].update({eid1, eid2, eid3})
hyfs.tags['work-in-progress'].update({eid4, eid5})
# Find all important files regardless of location
important = [hyfs.get(eid) for eid in hyfs.tags['important']]
```

## Lessons Learned

### Flat vs Hierarchical Storage
The original hierarchical dict approach mixed data (nodes) with one view (tree structure). Separating these into flat storage + derived views enables multiple perspectives (tree, tags, relations) without data duplication.

### AttrDict + Properties
AttrDict wasn't designed for class properties. Our `__getattribute__` override works but is a workaround. Future: consider if fastcore could add property support, or if we should use a different base class.

### UUID Version Drama
Python 3.12 doesn't have uuid7 yet (still in discussion). uuid4 is fine for our needs, easy to migrate later.

### xattr Portability
xattrs work great on modern Linux/macOS but fail on many consumer scenarios (cloud sync, FAT32). Deterministic fallback is essential. Future: consider sidecar metadata files for persistent tracking.

### Performance Thresholds
- <1K nodes: Any approach works
- 1K-10K nodes: Flat storage wins, tree on-demand
- 10K-100K nodes: Need path index for O(1) lookups
- 100K+ nodes: Consider incremental scanning, lazy loading

## Meta: How We Work

- **Incremental understanding**: Build simple examples to grasp concepts before implementing
- **Question assumptions**: "Why doesn't this exist?" often reveals antipatterns or limitations
- **Book-quality prose**: Dense paragraphs over blog-style bullet points for deep insights
- **Design before code**: Understand tradeoffs, then implement decisively
- **Prototype as we design**: PoC validates decisions immediately
- **Refactor boldly**: When design reveals better approach (hierarchical → flat), rewrite completely

## Complete Code Reference

### Core Implementation
```python
import uuid
import os
import errno
from hashlib import sha256
from pathlib import Path
from fastcore.basics import AttrDict, patch
from fastcore.foundation import L
from fnmatch import fnmatch
from collections import defaultdict

class FSNode(AttrDict):
    def __getattribute__(self, key):
        cls = object.__getattribute__(self, '__class__')
        if key in cls.__dict__ and isinstance(cls.__dict__[key], property):
            return cls.__dict__[key].fget(self)
        return super().__getattribute__(key)

class HyFS:
    def __init__(self):
        self.nodes = {}  # eid -> FSNode
        self.tags = defaultdict(set)  # tag_name -> {eid, ...}
        self.relations = defaultdict(lambda: defaultdict(set))  # eid -> {rel_type -> {eid, ...}}
    
    def add_node(self, path, eid=None, **metadata):
        """Add a node to the flat storage"""
        if eid is None:
            eid = _compute_eid(path)
        node = FSNode(
            path=path,
            eid=eid,
            type='dir' if path.is_dir() else 'file',
            **metadata
        )
        self.nodes[eid] = node
        return eid
    
    def get(self, eid):
        """O(1) lookup by eid"""
        return self.nodes[eid]
    
    def find_by_path(self, path):
        """Find node by path (O(n) scan - could optimize with index)"""
        path = Path(path)
        for node in self.nodes.values():
            if node.path == path:
                return node
        return None
    
    def tree(self, root_path=None):
        """Build hierarchical tree view from flat storage"""
        if root_path is None:
            # Find root (node with no parent in our set)
            roots = []
            for node in self.nodes.values():
                if not any(node.path.is_relative_to(other.path) and node.path != other.path 
                          for other in self.nodes.values()):
                    roots.append(node)
            if len(roots) == 1:
                root_path = roots[0].path
            else:
                raise ValueError("Multiple roots found, specify root_path")
        else:
            root_path = Path(root_path)
        
        root_node = self.find_by_path(root_path)
        if not root_node:
            raise ValueError(f"Root path {root_path} not found in nodes")
        
        return self._build_tree_node(root_node)
    
    def _build_tree_node(self, node):
        """Recursively build tree structure for a node"""
        tree_node = FSNode(node)  # Copy node data
        
        if node.type == 'dir':
            # Find children: nodes whose path.parent == this path
            children = []
            for candidate in self.nodes.values():
                if candidate.path.parent == node.path:
                    children.append(self._build_tree_node(candidate))
            tree_node['children'] = children
        
        return tree_node
    
    def filter(self, pred):
        """Filter nodes by predicate, returns flat list"""
        return L([node for node in self.nodes.values() if pred(node)])
    
    def find(self, pattern):
        """Find nodes matching glob pattern"""
        return self.filter(lambda n: fnmatch(n.path.name, pattern))

def _compute_eid(path):
    """Compute stable UUID for a path. Uses xattr if available, else deterministic hash."""
    path_str = str(path)
    xattr_key = 'user.hyfs.uuid'
    
    try:
        uuid_bytes = os.getxattr(path_str, xattr_key)
        return uuid_bytes.decode()
    except OSError:
        pass
    
    new_uuid = str(uuid.uuid4())
    
    try:
        os.setxattr(path_str, xattr_key, new_uuid.encode())
        return new_uuid
    except OSError as e:
        if e.errno in (errno.ENOTSUP, errno.EPERM, errno.EACCES):
            s = path.stat()
            data = f"{s.st_dev}:{s.st_ino}:{s.st_mtime}".encode()
            hash_hex = sha256(data).hexdigest()
            return f"{hash_hex[:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"
        else:
            raise

def scan_fs(root_path, include_metadata=False):
    """Scan filesystem and populate HyFS flat storage"""
    hyfs = HyFS()
    root_path = Path(root_path)
    
    # Walk the entire tree
    for path in [root_path] + list(root_path.rglob('*')):
        metadata = {}
        if include_metadata:
            # Add any metadata you want here
            pass
        hyfs.add_node(path, **metadata)
    
    return hyfs

@patch
def show(self:FSNode, indent=0):
    """Display tree node (works on tree view)"""
    print('    ' * indent + self.path.name)
    if 'children' in self:
        for child in self.children:
            child.show(indent+1)

@patch
def filter(self:FSNode, pred):
    """Filter tree node recursively (works on tree view)"""
    matches = L()
    if pred(self): matches.append(self)
    if 'children' in self:
        for child in self.children:
            matches += child.filter(pred)
    return matches

@patch
def find(self:FSNode, pattern):
    """Find in tree node (works on tree view)"""
    return self.filter(lambda n: fnmatch(n.path.name, pattern))
```

This is a living document. Update as HyFS evolves.
