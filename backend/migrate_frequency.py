import sqlite3
import json
import os
import sys

# Configure stdout to use UTF-8
sys.stdout.reconfigure(encoding='utf-8')

def migrate():
    db_path = 'd:/Xâm/xOCS/backend/checksheet.db'
    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, title, items FROM templates")
    rows = cursor.fetchall()
    
    updated_count = 0
    for row in rows:
        template_id = row['id']
        title = row['title']
        items_json = row['items']
        
        try:
            items = json.loads(items_json)
        except Exception as e:
            print(f"Error parsing JSON for template {template_id}: {e}")
            continue
            
        changed = False
        for item in items:
            if 'frequency' in item:
                freq = item['frequency']
                if not freq:
                    continue
                clean = str(freq).replace('\r', '').replace('\n', ' ').strip().lower()
                
                new_freq = freq
                if 'ca' in clean or 'shift' in clean:
                    new_freq = '1lần/ca'
                elif 'ngày' in clean or 'day' in clean:
                    new_freq = '1lần/ngày'
                elif 'khởi động' in clean or 'start up' in clean or 'startup' in clean:
                    new_freq = '1lần/khởi động'
                
                if new_freq != freq:
                    item['frequency'] = new_freq
                    changed = True
                    
        if changed:
            cursor.execute(
                "UPDATE templates SET items = ? WHERE id = ?",
                (json.dumps(items, ensure_ascii=False), template_id)
            )
            updated_count += 1
            print(f"Updated template items for: {title}")
            
    conn.commit()
    conn.close()
    print(f"Migration completed successfully! Updated {updated_count} templates.")

if __name__ == '__main__':
    migrate()
