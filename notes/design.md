# HyFS Design Document
> Hyper FileSystem - A filesystem abstraction with stable identity and semantic relationships

## Vision

HyFS provides stable entity identification and semantic organization for filesystems. Files and directories get persistent identities (eids) that survive renames and moves, enabling tagging, relationship tracking, and multiple views of the same underlying data.

Built for interactive exploration in SolveIT notebooks using fastcore principles.

## Core Philosophy

### Principle of Lean Information Form (LIF)

Information must be expressed in its meaningful form, preserving integrity without requiring decoders. Store semantic structure directly, decide display independently.

**LIF Lemma 1: Separation of Concerns**

Three orthogonal concepts, stored separately:
1. **Entity storage**: Flat dict `{eid -> node}` (canonical)
2. **Filesystem hierarchy**: Derived from `path` relationships (view)
3. **Semantic organization**: Tags and relations (metadata layer)

Don't mix these. Tags are many-to-many mappings. Relations are typed connections. Tree structure is computed on-demand from path relationships.

### The fastcore Way

Methods return transformed data when possible, enabling chaining. `filter()` returns a flat list of nodes, not print output. This separates data transformation from presentation.

**REPL excellence**: Custom `__repr__` methods show just enough information. `HyFS` displays counts with emoji. `FSNode` shows icon, name, and truncated eid. Like `L`, the goal is maximum clarity at a glance.

### Make Side Effects Explicit and Deferrable

Inspired by Git's staging area and ZFS transactions:
- **Read operations**: Immediate (work directly on flat storage)
- **Write operations**: Return a Plan/Transaction object that can be inspected, then executed
- Example: `plan = hyfs.rename(eid, 'newname')` → `plan.preview()` → `plan.execute()`

Provides safety, composability, and clear boundaries between observation and mutation.

## Architecture Decisions

### Flat Storage with Derived Views

**Choice**: Store nodes in flat dict `{eid -> FSNode}`, derive tree structure on-demand.

**Why flat**:
- O(1) lookup by eid
- No nested traversal for global operations
- Tags/relations are just dicts
- Multiple views from single source
- Easy serialization
- Scales better

**Why derived trees**:
- Tree structure implicit in `path` property
- Compute hierarchy when needed via `children_index`
- Display is a view concern, not data concern
- Can build multiple trees: filesystem, tags, relations

### Multiple Indexes Over Canonical Data

**Pattern**: Maintain several indexes over the flat `nodes` storage:
- `path_index`: Fast path lookups (O(1))
- `children_index`: Fast tree construction (O(n) not O(n²))
- `eid_tags`: Bidirectional tag lookup (O(1) both ways)

All indexes derive from canonical data and can be rebuilt. This is the database approach: primary key + secondary indexes.

### Entity Identification: UUID with xattr

Every node gets a stable `eid` (Entity ID). Try to store UUID in xattr `user.hyfs.uuid`. If xattr unavailable, fall back to deterministic hash of `(st_dev, st_ino, ctime)`.

**Why `eid` not `fid`/`nid`**: Directories are entities too—structure has semantic meaning. `eid` sits at perfect abstraction level between content (`cid`) and filesystem implementation (`nid`).

**Three-tier approach**:
1. **Best**: UUID in xattr (true stability)
2. **Good**: Deterministic hash using `ctime` from xattr (stable if xattr persists)
3. **Fallback**: Deterministic hash using `st_mtime` (changes on file modification)

### Creation Time: First-Class Metadata

`ctime` is always stored when possible (via `user.hyfs.ctime` xattr), initialized from `st_mtime` on first encounter. This provides:
- Valuable metadata in its own right (Linux lacks creation time in stat)
- Stable timestamp for eid computation in fallback scenarios
- Historical record of when HyFS first saw the entity

**Why `st_mtime` as initial value**: Files are typically created then immediately written. `st_mtime` is the best available approximation of creation time on first encounter.

### Content Addressing: Lazy SHA256 with Two-Tier Cache

`cid` property on `FSNode` uses two-level caching:
1. Node dict cache (session-only, ~7x speedup on repeated access)
2. Xattr cache `user.hyfs.cid` (persistent across sessions)

Computed on first access using ZFS-style 64KB streaming chunks. Returns `None` for directories.

**Update mechanism**: `update_cids()` clears both caches and forces recompute from disk. Chainable on `L` for workflows like `hyfs.find('*.py').update_cids()`.

### Path Index: O(1) Lookups

Maintain `path_index = {path: eid}` updated in `add_node()`. Makes `find_by_path()` O(1) instead of O(n) scan.

### Children Index: O(n) Tree Construction

Maintain `children_index = {parent_eid: {child_eids}}` updated in `add_node()`. Tree construction becomes O(n) instead of O(n²) - just walk the index instead of scanning all nodes for each parent.

### Tagging: Singular Operations with Bidirectional Index

Four methods for many-to-many relationships:
- `tag(eid, tag)` - add one tag to one eid
- `untag(eid, tag)` - remove one tag from one eid  
- `tagged(tag)` - get all eids with this tag
- `tags_of(eid)` - get all tags for this eid

**Bidirectional storage**:
- `tags[tag] -> {eids}` (forward: tag to entities)
- `eid_tags[eid] -> {tags}` (reverse: entity to tags)

Makes both directions O(1). Singular operations over variadic (Unix philosophy). Idempotent. Auto-cleanup empty tags. No validation, tags auto-create.

## What HyFS Enables

**Track files across renames**: eid persists through filesystem changes

**Detect duplicates**: Content-based deduplication via `cid`

**Compare trees**: Diff snapshots by eid to find added/removed/moved files

**Semantic relationships**: Tag files, build import graphs, track generation lineage

**Persistent selections**: Tags survive renames, moves, even filesystem boundaries

**Multiple views**: Same data, different perspectives—tree by path, tree by tags, graph by imports

**Historical metadata**: Creation time tracking even on filesystems that don't support it natively

**Efficient exploration**: REPL-optimized repr methods show exactly what you need at a glance

## Development Principles

- **Vertical space efficiency**: Favor one-liners where clarity isn't sacrificed
- **Fastcore alignment**: Use `L`, `AttrDict`, `@patch`, `Path`
- **REPL-driven**: Optimize for tab completion and exploration
- **Composability over monoliths**: Do one thing well
- **No premature optimization**: Measure first, but design for scale
- **No ceremony**: Terse, clear code
- **Index liberally**: Multiple views over canonical data
- **Make it chainable**: Return data structures that enable composition

## Current Capabilities

**Scanning**: Walk filesystem, assign stable eids, store in flat structure

**Querying**: Find by eid (O(1)), path (O(1)), pattern (O(n)), predicate (O(n))

**Tree views**: Build hierarchical structure on-demand from flat storage (O(n))

**Tagging**: Many-to-many relationships with O(1) lookups both directions

**Content hashing**: SHA256 with persistent xattr cache and session cache

**Metadata tracking**: Creation time, entity ID, content hash (all via xattr when possible)

**REPL exploration**: Custom repr methods, chainable operations, fastcore idioms

## Future Directions

**Immediate**: 
- Relations API: `hyfs.relate(eid1, 'imports', eid2)`
- Filtered tree views: Build trees from tagged subsets
- Write operations as Plans: `plan = hyfs.rename(...); plan.preview(); plan.execute()`

**Medium**: 
- Serialization: Save/load semantic layer (tags, relations)
- Deduplication: Find and merge identical content
- Snapshots: Track filesystem state over time
- Additional metadata properties: `size`, `mtime`, `permissions`

**Long-term**: 
- Multi-host tracking: Follow entities across machines
- Semantic relationships: Import graphs, generation lineage
- FastHTML web interface: Visual exploration and manipulation
- CLI tool: `hyfs tag`, `hyfs find`, `hyfs tree`
- Smart sync: Content-aware file synchronization

## Design Evolution

HyFS is in exploration phase (iteration 4). Previous attempts tried nested storage, different identity schemes, various tree construction approaches. Current design emerged from use, not upfront planning.

**Key learnings**:
- Flat storage beats nested for most operations
- Multiple indexes over canonical data scales better than denormalization
- Bidirectional indexes eliminate O(n) scans
- Xattr provides best stability, but graceful fallback essential
- REPL experience matters as much as API design
- Metadata like `ctime` valuable independent of implementation needs

**What changed this iteration**:
- Added `children_index` for O(n) tree construction
- Added `eid_tags` for O(1) reverse tag lookup
- Made `ctime` first-class metadata, not just fallback
- Two-tier caching for `cid` (xattr + node dict)
- Custom `__repr__` for REPL excellence
- Centralized xattr helpers for DRY

---

*This is a living document. Update as HyFS evolves.*

Key updates:
- ✅ Added REPL excellence to "The fastcore Way" section
- ✅ New section on "Multiple Indexes Over Canonical Data" pattern
- ✅ Updated Entity Identification to show three-tier approach
- ✅ New section on "Creation Time: First-Class Metadata"
- ✅ Updated Content Addressing to show two-tier cache
- ✅ New section on "Children Index: O(n) Tree Construction"
- ✅ Updated Tagging section to show bidirectional index
- ✅ Added "Historical metadata" and "Efficient exploration" to What HyFS Enables
- ✅ Updated Development Principles with "Index liberally" and "Make it chainable"
- ✅ Expanded Current Capabilities to reflect all new features
- ✅ New "Design Evolution" section documenting iteration 4 changes
