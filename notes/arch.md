# HyFS Architecture Document
> Implementation details, data structures, and algorithms

## Data Structures

### FSNode: AttrDict with Properties

`FSNode` extends `AttrDict` to enable both dict-style (`node['path']`) and attribute-style (`node.path`) access, optimized for REPL exploration.

**Property override challenge**: AttrDict's `__getattr__` intercepts attribute access before class properties. Solution: override `__getattribute__` to check class properties first.

Properties enable lazy computation:
- `cid`: Computed on first access, cached in node dict
- Future: `size`, `mtime`, `permissions`

### HyFS: Flat Storage Container

```python
self.nodes = {}              # eid -> FSNode (canonical storage)
self.path_index = {}         # path -> eid (O(1) lookups)
self.tags = defaultdict(set) # tag_name -> {eid, ...}
self.relations = defaultdict(lambda: defaultdict(set))  # eid -> {rel_type -> {eid, ...}}
```

All lookups are dict-based. Tree structure derived on-demand.

## Core Algorithms

### Entity ID Computation

1. Try read UUID from xattr `user.hyfs.uuid`
2. If missing, generate UUID v4
3. Try write to xattr
4. On xattr failure (unsupported fs, permissions), fall back to deterministic hash: `SHA256(st_dev:st_ino:st_mtime)` formatted as UUID

**Tradeoff**: xattr provides true stability, hash provides portability. Hash changes on mtime update, but that's acceptable for fallback scenario.

### Content ID Computation

Lazy `@property` on `FSNode`:
- Check if `'cid'` key exists in node dict (cache)
- If not, compute SHA256 using 64KB streaming chunks (ZFS-style)
- Store result in dict, return
- Subsequent access: O(1) dict lookup (~7x speedup)

Returns `None` for directories (no standard dir hashing yet).

### Tree View Construction

**Input**: Root path
**Output**: Hierarchical `FSNode` with `children` lists

**Algorithm**:
1. Look up root node in `path_index` (O(1))
2. Recursively build tree:
   - Copy node data into new `FSNode`
   - If directory: scan all nodes, find children where `path.parent == node.path`
   - Recursively build each child
   - Attach children list

**Complexity**: O(n²) worst case (check every node for each parent). Acceptable for <10K nodes. Future optimization: maintain parent-child index.

### Filesystem Scanning

**Algorithm**:
1. Use `Path.rglob('*')` to walk entire tree
2. For each path:
   - Compute eid (with xattr/hash fallback)
   - Determine type (file/dir)
   - Create `FSNode`
   - Store in `nodes[eid]` and `path_index[path]`
3. Return populated `HyFS` instance

**Performance**: ~1ms per 100 nodes on modern hardware. Metadata (size, mtime) skipped unless requested.

## Method Patterns

### Querying: Returns vs Side Effects

**Returns data**: `filter()`, `find()`, `get()`, `tagged()`, `tags_of()`, `tree()`
- Enable chaining: `hyfs.filter(pred1).filter(pred2)`
- Use `L` for lists (fastcore convention)
- Return actual references (sets) when mutation might be useful

**Side effects**: `tag()`, `untag()`, `add_node()`
- Modify internal state
- Idempotent where sensible
- Return minimal info (eid, None)

### Patching: Extending Classes

Use `@patch` to add methods to `HyFS` and `FSNode` after class definition. Keeps related functionality together without bloating class body.

Pattern:
```python
@patch
def method_name(self:ClassName, ...):
    """Docstring"""
    # implementation
```

## Key Implementation Details

### Path Index Maintenance

Updated in `add_node()` only. Not updated on rename/move (not implemented yet). When write operations added, will need atomic updates of both `nodes` and `path_index`.

### Tag Cleanup

`untag()` removes empty tag sets to prevent `defaultdict` accumulation. Tradeoff: extra check on every untag, but keeps `hyfs.tags.keys()` clean.

### defaultdict Usage

- `tags`: `defaultdict(set)` - tags auto-create on first use
- `relations`: `defaultdict(lambda: defaultdict(set))` - two-level auto-creation

Enables `hyfs.tags[new_tag].add(eid)` without checking if tag exists.

## Performance Characteristics

**Fast (O(1))**:
- Lookup by eid: `get(eid)`
- Lookup by path: `find_by_path(path)` (with index)
- Get all tagged: `tagged(tag)`

**Linear (O(n))**:
- Filter/find operations (scan all nodes)
- Get tags of eid: `tags_of(eid)` (scan all tags)
- Filesystem scan

**Quadratic (O(n²))**:
- Tree construction (check all nodes for each parent)

**Cached after first access**:
- Content hash: `node.cid`

## Edge Cases Handled

- **Missing xattr support**: Falls back to deterministic hash
- **Empty tag sets**: Auto-cleanup in `untag()`
- **Multiple roots**: `tree()` requires explicit root_path
- **Non-existent paths**: `find_by_path()` returns `None`
- **Duplicate tags/untags**: Idempotent operations
- **Directories**: `cid` returns `None` (no content)

## Persistence Strategy (Future)

**Current state**: All data in-memory only. Tags/relations lost on session end.

**Planned approach**:
- xattr for eid only (bound to file)
- Separate index file for semantic layer (tags, relations, snapshots)
- Format: JSON initially (human-readable), SQLite later (performance)
- Index references eids, not paths (stable across moves)
- Enables tracking entities that don't currently exist on filesystem

**Rationale**: Tags are index metadata, not file metadata. Separation of concerns matches architecture.

## Dependencies

- **Python 3.12+**: For `match` statements, walrus operator
- **fastcore**: `AttrDict`, `L`, `@patch`
- **pathlib**: All path operations
- **hashlib.sha256**: Content hashing (stdlib)
- **uuid**: Entity identification (stdlib)
- **os.{get,set}xattr**: Extended attributes (stdlib, Unix only)
- **collections.defaultdict**: Auto-creating dicts (stdlib)

No external dependencies beyond fastcore.

---

*This document describes current implementation. Update as architecture evolves.*