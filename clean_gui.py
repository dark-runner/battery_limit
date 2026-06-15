"""Remove cloud login code from gui.py"""
with open(r'D:\JavaDev\codeB\battery_limit\src\gui.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and remove from "_cloud_login" to just before "_save"
start = content.find('    def _cloud_login(self, card, sc):')
end = content.find('    def _save(self):')

if start >= 0 and end >= 0:
    # Remove from the line before _cloud_login to the line before _save
    # Find the previous line (the self.token_ent.config line)
    prev_line = content.rfind('\n', 0, start - 2)
    if prev_line >= 0:
        start = prev_line
    
    removed = content[start:end]
    content = content[:start] + content[end:]
    print(f"Removed {len(removed)} chars")
    print(f"Removed lines: {removed.count(chr(10))}")
else:
    print(f"start={start}, end={end}")
    # Try alternative search
    start2 = content.find("self.token_ent.config")
    if start2 >= 0:
        print(f"Found token_ent at {start2}")

with open(r'D:\JavaDev\codeB\battery_limit\src\gui.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Done")
