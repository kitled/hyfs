# HyFS Architecture Document
> Implementation details, data structures, and algorithms

## Data Structures

### FSNode: AttrDict with Properties

`FSNode` extends `AttrDict` to enable both dict-style (`node['path']`) and attribute-style (`node.path`) access, optimized for REPL exploration.

**Property override challenge**: AttrDict's `__getattr__` intercepts attribute access before class properties. Solution: override `__getattribute__` to check class properties first.

Properties enable lazy computation:
- `cid`: Computed on first access, cached in node dict
- Future: `size`, `mtime`, `permissions`

**Custom repr**: Shows file/dir icon (📄/📁), name, and truncated eid (8 chars) for clean REPL display.

### HyFS: Flat Storage Container

```python
self.nodes = {}              # eid -> FSNode (canonical storage)
self.path_index = {}         # path -> eid (O(1) lookups)
self.children_index = {}     # parent_eid -> {child_eids} (O(n) tree construction)
self.tags = defaultdict(set) # tag_name -> {eid, ...}
self.eid_tags = defaultdict(set)  # eid -> {tag_name, ...} (bidirectional)
self.relations = defaultdict(lambda: defaultdict(set))  # eid -> {rel_type -> {eid, ...}}
```

All lookups are dict-based. Tree structure derived on-demand. Multiple indexes maintained over canonical `nodes` storage.

**Custom repr**: Shows counts with emoji: `HyFS(📄 60 files, 📁 36 dirs, 🏷️ 3 tags)`

## Core Algorithms

### Entity ID Computation

**Three-tier approach** with `ctime` as first-class metadata:

1. **Always** try to store creation time (`user.hyfs.ctime`) using `st_mtime` as initial value
2. Try read UUID from xattr `user.hyfs.uuid`
3. If missing, generate UUID v4
4. Try write to xattr
5. On xattr failure, fall back to deterministic hash: `SHA256(st_dev:st_ino:ctime)` formatted as UUID

**Key insight**: `ctime` is valuable metadata in its own right, not just for eid fallback. Always stored when possible.

**Stability guarantee**: 
- Best case (xattr): True UUID, survives all filesystem changes
- Fallback case (no xattr): Deterministic hash stable as long as `ctime` xattr persists
- Ultimate fallback (no xattr at all): Hash based on `st_mtime`, changes on file modification

### Content ID Computation

**Two-tier caching** for performance:

1. Check xattr `user.hyfs.cid` (persistent across sessions)
2. If not found, compute SHA256 using 64KB streaming chunks (ZFS-style)
3. Cache in xattr for next session
4. Also cache in node dict for current session (~7x speedup on repeated access)

Returns `None` for directories (no standard dir hashing yet).

**Update mechanism**: `update_cids()` method clears both caches (node dict + xattr) to force recompute from disk. Chainable on `L` for workflows like `hyfs.find('*.py').update_cids()`.

### Tree View Construction

**Input**: Root path  
**Output**: Hierarchical `FSNode` with `children` lists

**Algorithm**:
1. Look up root node in `path_index` (O(1))
2. Recursively build tree:
   - Copy node data into new `FSNode`
   - If directory: look up children in `children_index` (O(1))
   - Recursively build each child
   - Attach children list

**Complexity**: O(n) with children index (previously O(n²)). Index maintained during `add_node()`.

### Filesystem Scanning

**Algorithm**:
1. Use `Path.rglob('*')` to walk entire tree
2. For each path:
   - Compute eid (with xattr/hash fallback, ensures ctime stored)
   - Determine type (file/dir)
   - Create `FSNode`
   - Store in `nodes[eid]` and `path_index[path]`
   - Update `children_index` if parent exists
3. Return populated `HyFS` instance

**Performance**: ~1ms per 100 nodes on modern hardware. Metadata (size, mtime) skipped unless requested.

### Tagging: Bidirectional Index

**Data structures**:
- `tags[tag_name]` → `{eids}` (forward: tag to entities)
- `eid_tags[eid]` → `{tags}` (reverse: entity to tags)

**Operations**:
- `tag(eid, tag)`: Update both indexes (O(1))
- `untag(eid, tag)`: Remove from both, cleanup empty sets (O(1))
- `tagged(tag)`: Return `tags[tag]` (O(1))
- `tags_of(eid)`: Return `eid_tags[eid]` (O(1), previously O(n))

**Auto-cleanup**: Empty sets removed to prevent `defaultdict` accumulation.

## Method Patterns

### Querying: Returns vs Side Effects

**Returns data**: `filter()`, `find()`, `get()`, `tagged()`, `tags_of()`, `tree()`
- Enable chaining: `hyfs.filter(pred1).filter(pred2)`
- Use `L` for lists (fastcore convention)
- Return actual references (sets) when mutation might be useful

**Side effects**: `tag()`, `untag()`, `add_node()`, `update_cids()`
- Modify internal state
- Idempotent where sensible
- Return minimal info or self for chaining

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

### Index Maintenance

**Three indexes** updated atomically in `add_node()`:
- `path_index[path] = eid`
- `children_index[parent_eid].add(eid)`
- `nodes[eid] = node`

When write operations added (rename/move), all three must update atomically.

### Xattr Helpers

Centralized xattr handling through three functions:
- `_get_xattr(path, key, default)`: Safe read with fallback
- `_set_xattr(path, key, value)`: Safe write, returns success boolean
- `_ensure_xattr(path, key, compute_fn)`: Read-or-compute-and-store pattern

All HyFS xattrs use `user.hyfs.*` namespace. Failures handled gracefully (no exceptions).

### Tag Cleanup

`untag()` removes empty tag sets from both `tags` and `eid_tags` to prevent `defaultdict` accumulation. Tradeoff: extra check on every untag, but keeps dict keys clean.

### defaultdict Usage

- `tags`: `defaultdict(set)` - tags auto-create on first use
- `eid_tags`: `defaultdict(set)` - reverse index auto-creates
- `children_index`: `defaultdict(set)` - children auto-create
- `relations`: `defaultdict(lambda: defaultdict(set))` - two-level auto-creation

Enables `hyfs.tags[new_tag].add(eid)` without checking if tag exists.

## Performance Characteristics

**O(1) - Fast**:
- Lookup by eid: `get(eid)`
- Lookup by path: `find_by_path(path)` (with index)
- Get all tagged: `tagged(tag)`
- Get tags of eid: `tags_of(eid)` (with bidirectional index)
- Get children: `children_index[parent_eid]`

**O(n) - Linear**:
- Filter/find operations (scan all nodes)
- Filesystem scan
- Tree construction (with children index)

**Cached after first access**:
- Content hash: `node.cid` (node dict cache)
- Content hash: xattr `user.hyfs.cid` (persistent cache)
- Entity ID: xattr `user.hyfs.uuid` (persistent)
- Creation time: xattr `user.hyfs.ctime` (persistent)

## Edge Cases Handled

- **Missing xattr support**: Falls back to deterministic hash for eid
- **Empty tag sets**: Auto-cleanup in `untag()`
- **Multiple roots**: `tree()` requires explicit root_path
- **Non-existent paths**: `find_by_path()` returns `None`
- **Duplicate tags/untags**: Idempotent operations
- **Directories**: `cid` returns `None` (no content)
- **Stale content hashes**: `update_cids()` forces recompute
- **Missing parent in index**: `children_index` check handles gracefully

## Persistence Strategy (Future)

**Current state**: All data in-memory only. Tags/relations lost on session end. Xattrs persist on filesystem.

**What persists now**:
- `user.hyfs.uuid`: Entity ID (when xattr available)
- `user.hyfs.ctime`: Creation time (when xattr available)
- `user.hyfs.cid`: Content hash (when xattr available)

**Planned approach**:
- Xattrs for per-file metadata (eid, ctime, cid)
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
- **os.{get,set,remove}xattr**: Extended attributes (stdlib, Unix only)
- **collections.defaultdict**: Auto-creating dicts (stdlib)

No external dependencies beyond fastcore.

---

*This document describes current implementation. Update as architecture evolves.*


Key updates:
- ✅ Added custom `__repr__` details for both classes
- ✅ Documented `children_index` and O(n) tree construction
- ✅ Documented bidirectional tag index (`eid_tags`)
- ✅ Updated eid computation to show `ctime` as first-class metadata
- ✅ Added two-tier caching for `cid` (xattr + node dict)
- ✅ Added `update_cids()` method documentation
- ✅ Updated performance characteristics to show new O(1) operations
- ✅ Added xattr helpers section
- ✅ Updated persistence strategy to show what persists now
