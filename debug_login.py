"""Debug micloud login - write to file to avoid terminal issues"""
import sys
import inspect
from micloud import MiCloud

# Get the source
src = inspect.getsource(MiCloud)

# Write the login method to a file
with open("micloud_login_source.txt", "w", encoding="utf-8") as f:
    lines = src.split("\n")
    in_login = False
    for i, line in enumerate(lines):
        if "def login" in line:
            in_login = True
        if in_login:
            f.write(f"{i}: {line}\n")
            if in_login and line.strip() and not line.startswith(" ") and not line.startswith("\t") and not line.startswith("def"):
                if i > 0 and lines[i-1].strip() and not lines[i-1].startswith(" "):
                    pass
                elif i > 0:
                    in_login = False

    # Better approach - just print all defs
    f.write("\n\n=== ALL FUNCTIONS ===\n")
    for i, line in enumerate(lines):
        if line.startswith("    def ") or line.startswith("def "):
            f.write(f"{i}: {line}\n")

print("Done - check micloud_login_source.txt")
