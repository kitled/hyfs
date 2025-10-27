

import os
from pathlib import Path

# Root directory
root = Path("/app/data/dev/hyfs/test/fs")

# Create the root directory
root.mkdir(parents=True, exist_ok=True)

# Define the filesystem structure with lots of variety and edge cases
filesystem = {
    # Regular files at root
    "README.md": "# Test Project\n",
    "config.json": '{"version": "1.0"}\n',
    ".gitignore": "*.pyc\n__pycache__/\n",
    ".env": "SECRET_KEY=test123\n",
    "requirements.txt": "numpy==1.24.0\npandas>=2.0.0\n",
    
    # Source code directory
    "src/main.py": "def main():\n    pass\n",
    "src/utils.py": "# Utilities\n",
    "src/__init__.py": "",
    "src/models/user.py": "class User:\n    pass\n",
    "src/models/__init__.py": "",
    "src/models/product.py": "class Product:\n    pass\n",
    
    # Tests directory
    "tests/test_main.py": "def test_main():\n    assert True\n",
    "tests/__init__.py": "",
    "tests/fixtures/data.json": '{"test": "data"}\n',
    "tests/fixtures/sample.csv": "id,name,value\n1,test,100\n",
    
    # Data directory with various file types
    "data/raw/dataset_2023.csv": "col1,col2,col3\n1,2,3\n",
    "data/raw/dataset_2024.csv": "col1,col2,col3\n4,5,6\n",
    "data/processed/cleaned_data.parquet": b"fake parquet data",
    "data/processed/features.pkl": b"fake pickle data",
    "data/images/photo1.jpg": b"fake jpg data",
    "data/images/photo2.png": b"fake png data",
    "data/images/thumbnails/thumb1.jpg": b"fake thumbnail",
    
    # Documentation
    "docs/index.html": "<html><body>Docs</body></html>\n",
    "docs/api/endpoints.md": "# API Endpoints\n",
    "docs/api/authentication.md": "# Auth\n",
    "docs/guides/getting-started.pdf": b"fake pdf data",
    
    # Configuration files
    "config/development.yaml": "debug: true\n",
    "config/production.yaml": "debug: false\n",
    "config/database.ini": "[database]\nhost=localhost\n",
    
    # Build artifacts
    "build/output.js": "console.log('built');\n",
    "build/styles.css": "body { margin: 0; }\n",
    "dist/bundle.min.js": "!function(){console.log('minified')}();\n",
    
    # Edge cases
    "files with spaces/document 1.txt": "Content with spaces\n",
    "files with spaces/my file (copy).docx": b"fake docx",
    "special-chars/file@2024.txt": "File with @ symbol\n",
    "special-chars/data#1.csv": "test,data\n",
    "special-chars/report_v2.1.pdf": b"fake pdf",
    "multiple.dots.in.name.txt": "Multiple dots\n",
    "UPPERCASE.TXT": "UPPERCASE FILE\n",
    "MixedCase.TxT": "Mixed case extension\n",
    
    # Hidden files and directories
    ".hidden/secret.txt": "Hidden content\n",
    ".hidden/.config": "hidden config\n",
    ".cache/temp1.tmp": "cache data\n",
    
    # Empty directory (will create separately)
    "empty_dir/.keep": "",
    
    # Deep nesting
    "a/b/c/d/e/deep_file.txt": "Very nested\n",
    
    # Various extensions
    "scripts/deploy.sh": "#!/bin/bash\necho 'deploying'\n",
    "scripts/backup.bat": "@echo off\necho backing up\n",
    "notebooks/analysis.ipynb": '{"cells": []}\n',
    "media/video.mp4": b"fake video data",
    "media/audio.mp3": b"fake audio data",
    "archives/backup.zip": b"fake zip data",
    "archives/old_data.tar.gz": b"fake tar.gz data",
    
    # Files with no extension
    "LICENSE": "MIT License\n",
    "Makefile": "all:\n\techo 'building'\n",
    "Dockerfile": "FROM python:3.11\n",
    
    # Very long filename
    "long_filename_that_goes_on_and_on_and_on_to_test_length_limits.txt": "Long name\n",
    
    # Numeric filenames
    "logs/2024-01-01.log": "[INFO] Log entry\n",
    "logs/2024-01-02.log": "[ERROR] Error entry\n",
    "reports/001_report.txt": "Report 1\n",
    "reports/002_report.txt": "Report 2\n",
}

# Create all files and directories
for filepath, content in filesystem.items():
    full_path = root / filepath
    full_path.parent.mkdir(parents=True, exist_ok=True)
    
    if isinstance(content, bytes):
        full_path.write_bytes(content)
    else:
        full_path.write_text(content)

# Create a truly empty directory
(root / "truly_empty").mkdir(exist_ok=True)

# Create another empty nested directory
(root / "temp/cache/empty").mkdir(parents=True, exist_ok=True)

print(f"✓ Created dummy filesystem at {root}")
print(f"✓ Total files created: {len(filesystem)}")
print(f"✓ Includes edge cases: spaces, special chars, hidden files, deep nesting, various extensions")










# Scan the filesystem first
hyfs = scan_fs('/app/data/dev/hyfs/test/fs')

# Tag some files
py_files = hyfs.find('*.py')
print(f"Found {len(py_files)} Python files")

# Tag the first few Python files as 'important'
for node in py_files[:3]:
    hyfs.tag(node.eid, 'important')
    print(f"Tagged {node.path.name}")

# Tag some as 'code'
for node in py_files:
    hyfs.tag(node.eid, 'code')

# Tag a config file as 'important' too
config = hyfs.find_by_path(root / 'config.json')
if config:
    hyfs.tag(config.eid, 'important')
    hyfs.tag(config.eid, 'config')

# Query: What's tagged as 'important'?
important_eids = hyfs.tagged('important')
print(f"\n{len(important_eids)} files tagged 'important':")
for eid in important_eids:
    node = hyfs.get(eid)
    print(f"  - {node.path.name}")

# Query: What's tagged as 'code'?
code_eids = hyfs.tagged('code')
print(f"\n{len(code_eids)} files tagged 'code':")
for eid in code_eids:
    node = hyfs.get(eid)
    print(f"  - {node.path.name}")

# Query: What tags does the first Python file have?
first_py = py_files[0]
tags = hyfs.tags_of(first_py.eid)
print(f"\nTags for {first_py.path.name}: {tags}")

# Test untag
hyfs.untag(first_py.eid, 'important')
print(f"\nAfter untag, {first_py.path.name} tags: {hyfs.tags_of(first_py.eid)}")
print(f"Important count now: {len(hyfs.tagged('important'))}")

# Show all tags
print(f"\nAll tags in system: {list(hyfs.tags.keys())}")


























































































