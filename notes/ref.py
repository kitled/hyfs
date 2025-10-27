import uuid
import os
import errno
from hashlib import sha256
from pathlib import Path
from fastcore.basics import AttrDict, patch
from fastcore.foundation import L
from fnmatch import fnmatch
from collections import defaultdict

# Xattr helpers
def _get_xattr(path, key, default=None):
    """Get HyFS xattr value, return default if not found"""
    try:
        return os.getxattr(str(path), f'user.hyfs.{key}').decode()
    except OSError:
        return default

def _set_xattr(path, key, value):
    """Set HyFS xattr value, return True on success"""
    try:
        os.setxattr(str(path), f'user.hyfs.{key}', str(value).encode())
        return True
    except OSError:
        return False

def _ensure_xattr(path, key, compute_fn):
    """Get xattr value, computing and storing if missing. Returns (value, stored_successfully)"""
    value = _get_xattr(path, key)
    if value is not None:
        return value, True
    
    value = compute_fn()
    stored = _set_xattr(path, key, value)
    return value, stored

class FSNode(AttrDict):
    def __getattribute__(self, key):
        cls = object.__getattribute__(self, '__class__')
        if key in cls.__dict__ and isinstance(cls.__dict__[key], property):
            return cls.__dict__[key].fget(self)
        return super().__getattribute__(key)

class HyFS:
    def __init__(self):
        self.nodes = {}  # eid -> FSNode
        self.path_index = {}  # path -> eid
        self.children_index = defaultdict(set)  # parent_eid -> {child_eids}
        self.tags = defaultdict(set)  # tag_name -> {eid, ...}
        self.eid_tags = defaultdict(set)  # eid -> {tag_name, ...}
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
        self.path_index[path] = eid
        
        # Update children index
        parent_path = path.parent
        parent_eid = self.path_index.get(parent_path)
        if parent_eid:
            self.children_index[parent_eid].add(eid)
        
        return eid

    def get(self, eid):
        """O(1) lookup by eid"""
        return self.nodes[eid]
    
    def find_by_path(self, path):
        """Find node by path (O(1) with index)"""
        path = Path(path)
        eid = self.path_index.get(path)
        return self.nodes.get(eid) if eid else None
    
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
        """Recursively build tree structure for a node (O(n) with children index)"""
        tree_node = FSNode(node)  # Copy node data
        
        if node.type == 'dir':
            # Use children index for O(1) lookup
            child_eids = self.children_index.get(node.eid, set())
            children = []
            for child_eid in child_eids:
                child_node = self.nodes[child_eid]
                children.append(self._build_tree_node(child_node))
            tree_node['children'] = children
        
        return tree_node

    def filter(self, pred):
        """Filter nodes by predicate, returns flat list"""
        return L([node for node in self.nodes.values() if pred(node)])
    
    def find(self, pattern):
        """Find nodes matching glob pattern"""
        return self.filter(lambda n: fnmatch(n.path.name, pattern))

    def __repr__(self):
        n_files = sum(1 for n in self.nodes.values() if n.type == 'file')
        n_dirs = sum(1 for n in self.nodes.values() if n.type == 'dir')
        n_tags = len(self.tags)
        return f"HyFS(📄 {n_files} files, 📁 {n_dirs} dirs, 🏷️  {n_tags} tags)"

def _compute_eid(path):
    """Compute stable UUID for a path. Uses xattr if available, else deterministic hash from creation time."""
    # Always try to ensure ctime is stored (valuable metadata)
    ctime, _ = _ensure_xattr(path, 'ctime', lambda: str(path.stat().st_mtime))
    
    # Try to get existing UUID
    eid = _get_xattr(path, 'uuid')
    if eid:
        return eid
    
    # No UUID yet, generate one
    new_uuid = str(uuid.uuid4())
    
    # Try to store it
    if _set_xattr(path, 'uuid', new_uuid):
        return new_uuid
    
    # Xattr not supported for UUID, fall back to deterministic hash
    # Use ctime (from xattr if available, else st_mtime from above)
    s = path.stat()
    data = f"{s.st_dev}:{s.st_ino}:{ctime}".encode()
    hash_hex = sha256(data).hexdigest()
    return f"{hash_hex[:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"

def _compute_cid(path):
    """Compute SHA256 content hash for a file. Uses xattr cache if available."""
    if not path.is_file():
        return None
    
    # Check for cached cid in xattr
    cached_cid = _get_xattr(path, 'cid')
    if cached_cid:
        return cached_cid
    
    # Compute hash
    h = sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(65536):  # 64KB chunks
            h.update(chunk)
    
    cid = h.hexdigest()
    
    # Try to cache it
    _set_xattr(path, 'cid', cid)
    
    return cid

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

# Add cid property to FSNode
@property
def cid(self):
    """Lazy-computed content ID (SHA256 hash) for files"""
    if 'cid' not in self:
        self['cid'] = _compute_cid(self.path)
    return self['cid']

FSNode.cid = cid

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

@patch
def __repr__(self:FSNode):
    name = self.path.name if hasattr(self, 'path') else 'unknown'
    type_icon = '📁' if self.get('type') == 'dir' else '📄'
    eid_short = self.eid[:8] if hasattr(self, 'eid') else 'no-eid'
    return f"FSNode({type_icon} {name!r}, {eid_short}...)"

@patch
def tag(self:HyFS, eid, tag):
    """Add a tag to an eid (idempotent)"""
    self.tags[tag].add(eid)
    self.eid_tags[eid].add(tag)

@patch
def untag(self:HyFS, eid, tag):
    """Remove a tag from an eid (idempotent)"""
    self.tags[tag].discard(eid)
    self.eid_tags[eid].discard(tag)
    
    # Clean up empty sets
    if not self.tags[tag]:
        del self.tags[tag]
    if not self.eid_tags[eid]:
        del self.eid_tags[eid]

@patch
def tagged(self:HyFS, tag):
    """Get all eids with this tag"""
    return self.tags[tag]  # Returns set (possibly empty)

@patch
def tags_of(self:HyFS, eid):
    """Get all tags for this eid (O(1) with bidirectional index)"""
    return self.eid_tags[eid]  # Returns set (possibly empty)

@patch
def update_cids(self:L):
    """Update cids for a list of nodes (chainable), recomputing from disk"""
    for node in self:
        if node.type == 'file':
            # Clear node dict cache
            if 'cid' in node:
                del node['cid']
            # Clear xattr cache to force recompute
            try:
                os.removexattr(str(node.path), 'user.hyfs.cid')
            except OSError:
                pass  # Wasn't set or xattr not supported
            # Now access will recompute from file content
            _ = node.cid
    return self
