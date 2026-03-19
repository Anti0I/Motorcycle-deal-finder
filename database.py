import sqlite3

DB_PATH = 'otomoto_listings.db'


def init_db(clean_start=False):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if clean_start:
        cursor.execute('DROP TABLE IF EXISTS listings')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS listings (
            id TEXT PRIMARY KEY
        )
    ''')
    conn.commit()
    conn.close()


def is_listing_new(listing_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM listings WHERE id = ?', (listing_id,))
    result = cursor.fetchone()
    conn.close()
    return result is None


def save_listing(listing_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO listings (id) VALUES (?)', (listing_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()
