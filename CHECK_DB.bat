@echo off
python -c "import sqlite3,os; db=os.path.join(os.path.expanduser('~'),'Documents','NEW_INDIAN_STEEL','billing.db'); con=sqlite3.connect(db); total=con.execute('SELECT COUNT(*) FROM products').fetchone()[0]; print('Products in REAL DB:',total); [print(f'  {r[0]:3d}  {r[1]}') for r in con.execute('SELECT id,name FROM products ORDER BY id DESC LIMIT 10').fetchall()]"
pause
