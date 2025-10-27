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
- Compute hierarchy when needed
- Display is a view concern, not data concern
- Can build multiple trees: filesystem, tags, relations

### Entity Identification: UUID with xattr

Every node gets a stable `eid` (Entity ID). Try to store UUID in xattr `user.hyfs.uuid`. If xattr unavailable, fall back to deterministic hash of `(st_dev, st_ino, st_mtime)`.

**Why `eid` not `fid`/`nid`**: Directories are entities too—structure has semantic meaning. `eid` sits at perfect abstraction level between content (`cid`) and filesystem implementation (`nid`).

### Content Addressing: Lazy SHA256

`cid` property on `FSNode` computes SHA256 hash on first access, caches result. Uses ZFS-style 64KB streaming chunks. Returns `None` for directories.

### Path Index: O(1) Lookups

Maintain `path_index = {path: eid}` updated in `add_node()`. Makes `find_by_path()` O(1) instead of O(n) scan.

### Tagging: Singular Operations

Four methods for many-to-many relationships:
- `tag(eid, tag)` - add one tag to one eid
- `untag(eid, tag)` - remove one tag from one eid  
- `tagged(tag)` - get all eids with this tag
- `tags_of(eid)` - get all tags for this eid

Singular operations over variadic (Unix philosophy). Idempotent. Auto-cleanup empty tags. No validation, tags auto-create.

## What HyFS Enables

**Track files across renames**: eid persists through filesystem changes

**Detect duplicates**: Content-based deduplication via `cid`

**Compare trees**: Diff snapshots by eid to find added/removed/moved files

**Semantic relationships**: Tag files, build import graphs, track generation lineage

**Persistent selections**: Tags survive renames, moves, even filesystem boundaries

**Multiple views**: Same data, different perspectives—tree by path, tree by tags, graph by imports

## Development Principles

- **Vertical space efficiency**: Favor one-liners where clarity isn't sacrificed
- **Fastcore alignment**: Use `L`, `AttrDict`, `@patch`, `Path`
- **REPL-driven**: Optimize for tab completion and exploration
- **Composability over monoliths**: Do one thing well
- **No premature optimization**: Measure first
- **No ceremony**: Terse, clear code

## Future Directions

**Immediate**: Relations API, filtered tree views, write operations (rename/move/copy as Plans)

**Medium**: Serialization, deduplication, snapshots, metadata properties (size, mtime, permissions)

**Long-term**: Multi-host tracking, semantic relationships (imports, lineage), FastHTML web interface, CLI tool

---

*This is a living document. Update as HyFS evolves.*