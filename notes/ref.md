# Core Implementation
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
