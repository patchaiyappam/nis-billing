@echo off
python -c "
import sqlite3, os
db = os.path.join(os.path.expanduser('~'),'Documents','NEW_INDIAN_STEEL','billing.db')
con = sqlite3.connect(db)
con.row_factory = sqlite3.Row
lines = []
lines.append('=== invoice_items columns ===')
cols = [r[1] for r in con.execute('PRAGMA table_info(invoice_items)')]
lines.append(str(cols))
lines.append('')
lines.append('=== invoice_items (last 30 rows) ===')
for r in con.execute('SELECT * FROM invoice_items ORDER BY id DESC LIMIT 30').fetchall():
    lines.append(str(dict(r)))
lines.append('')
lines.append('=== products table columns ===')
pcols = [r[1] for r in con.execute('PRAGMA table_info(products)')]
lines.append(str(pcols))
out = os.path.join(os.path.expanduser('~'),'Desktop','NIS_CHECK.txt')
open(out,'w').write('\n'.join(lines))
print('Done! Check NIS_CHECK.txt on your Desktop')
" > "%USERPROFILE%\Desktop\NIS_CHECK.txt" 2>&1
echo Done. Open NIS_CHECK.txt on your Desktop.
pause
