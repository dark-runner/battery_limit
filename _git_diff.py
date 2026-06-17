"""临时脚本：对比工作区与上次提交的文件差异"""
import os
import zlib
import hashlib

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Read HEAD commit
with open('.git/refs/heads/main') as f:
    head = f.read().strip()

# Read commit object
obj_path = f'.git/objects/{head[:2]}/{head[2:]}'
with open(obj_path, 'rb') as f:
    raw = zlib.decompress(f.read())

# Parse commit to get tree hash
lines = raw.decode('utf-8').split('\n')
tree_hash = None
for line in lines:
    if line.startswith('tree '):
        tree_hash = line.split()[1]
        break

# Read tree object
tree_path = f'.git/objects/{tree_hash[:2]}/{tree_hash[2:]}'
with open(tree_path, 'rb') as f:
    tree_raw = zlib.decompress(f.read())

# Parse tree entries
pos = 0
tracked = {}
while pos < len(tree_raw):
    space = tree_raw.index(b' ', pos)
    null = tree_raw.index(b'\0', space + 1)
    mode = tree_raw[pos:space].decode()
    name = tree_raw[space+1:null].decode('utf-8')
    hash_bytes = tree_raw[null+1:null+21]
    tracked[name] = hash_bytes.hex()
    pos = null + 21

print("=== 上次提交追踪的文件 ===")
for name in sorted(tracked):
    print(f"  {name}")

# 读取当前工作区文件
IGNORE_DIRS = {'.git', '__pycache__', '.venv', 'venv', 'env', '.pytest_cache', 
               '.mypy_cache', 'build', 'dist', '.eggs', '*.egg-info', 
               '.vscode', '.idea', 'node_modules'}
IGNORE_EXTS = {'.pyc', '.pyo', '.so', '.egg', '.spec'}

def should_ignore(name):
    # Check if any parent dir is in ignore list
    parts = name.replace('\\', '/').split('/')
    for p in parts:
        if p in IGNORE_DIRS or p.startswith('.') and p != '.':
            return True
    if any(name.endswith(ext) for ext in IGNORE_EXTS):
        return True
    # Check gitignore patterns roughly
    if name.endswith('.log') or name == '样式参考.jfif' or name == 'app_preview.png':
        return True
    return False

workspace_files = set()
for root, dirs, files in os.walk('.'):
    # Skip ignored dirs
    dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith('.') or d == '.']
    for f in files:
        rel = os.path.relpath(os.path.join(root, f), '.')
        if not should_ignore(rel):
            workspace_files.add(rel)

print("\n=== 工作区文件 (排除忽略) ===")
for name in sorted(workspace_files):
    status = "  (已追踪)" if name in tracked else "  (新增)"
    print(f"  {name}{status}")

print("\n=== 需要提交的变更 ===")
# New files
new_files = [f for f in sorted(workspace_files) if f not in tracked]
# Removed files
removed_files = [f for f in sorted(tracked) if f not in workspace_files]
# Modified files - just check size change
modified_files = []
for name in sorted(workspace_files):
    if name in tracked and os.path.isfile(name):
        stat = os.stat(name)
        # Read file content and hash it
        with open(name, 'rb') as f:
            content = f.read()
        # Git blob hash
        blob = f'blob {len(content)}\0'.encode() + content
        h = hashlib.sha1(blob).hexdigest()
        if h != tracked[name]:
            modified_files.append(name)

if new_files:
    print(f"\n  新增文件 ({len(new_files)}):")
    for f in new_files:
        print(f"    + {f}")
if removed_files:
    print(f"\n  删除文件 ({len(removed_files)}):")
    for f in removed_files:
        print(f"    - {f}")
if modified_files:
    print(f"\n  修改文件 ({len(modified_files)}):")
    for f in modified_files:
        print(f"    M {f}")
if not new_files and not removed_files and not modified_files:
    print("  没有变更 (工作区干净)")

# Clean up
os.remove(__file__)
