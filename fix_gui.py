"""Remove cloud login code and fix _save method"""
with open(r'D:\JavaDev\codeB\battery_limit\src\gui.py', 'r', encoding='utf-8') as f:
    c = f.read()

# Find the section to remove: from _cloud_login def to just before __init__ of next class
start_marker = '    def _cloud_login(self, card, sc):'
end_marker = 'class BatteryMonitorGUI:'

s = c.find(start_marker)
e = c.find(end_marker)

if s > 0 and e > 0:
    # Go back to find the previous blank line or comment
    prev = c.rfind('\n\n', 0, s)
    if prev > 0:
        s = prev + 1
    
    removed = c[s:e]
    c = c[:s] + c[e:]
    print(f"Removed {len(removed)} chars ({removed.count(chr(10))} lines)")
    
    with open(r'D:\JavaDev\codeB\battery_limit\src\gui.py', 'w', encoding='utf-8') as f:
        f.write(c)
    print("Done")
else:
    print(f"start={s}, end={e}")
