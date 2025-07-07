import sqlite3

class SQLiteDB:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_path)

    def execute(self, query, params=None):
        if self.conn is None:
            self.connect()
        cursor = self.conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        self.conn.commit()
        return cursor

    def fetchall(self, query, params=None):
        cursor = self.execute(query, params)
        return cursor.fetchall()

    def fetchone(self, query, params=None):
        cursor = self.execute(query, params)
        return cursor.fetchone()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None


class JobDatabase(SQLiteDB):
    def __init__(self, db_path):
        super().__init__(db_path)
        self.create_table()

    def create_table(self):
        self.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                link TEXT NOT NULL,
                checked BOOLEAN DEFAULT 0
            )
        ''')

    def add_job(self, title, link):
        self.execute('INSERT INTO jobs (title, link) VALUES (?, ?)', (title, link))

    def get_unchecked_jobs(self):
        return self.fetchall('SELECT * FROM jobs WHERE checked = 0')

    def mark_job_as_checked(self, job_id):
        self.execute('UPDATE jobs SET checked = 1 WHERE id = ?', (job_id,))

    def get_job_by_id(self, job_id):
        return self.fetchone('SELECT * FROM jobs WHERE id = ?', (job_id,))
    
    def job_exists(self, link):
        return self.fetchone('SELECT 1 FROM jobs WHERE link = ?', (link,)) is not None


class UserDatabase(SQLiteDB):
    def __init__(self, db_path):
        super().__init__(db_path)
        self.create_table()

    def create_table(self):
        self.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                username TEXT NOT NULL,
                resume TEXT DEFAULT NULL,
                expected_salary INTEGER DEFAULT NULL,
                graduation_date TEXT DEFAULT NULL
            )
        ''')

    def add_user(self, name, username, resume=None, expected_salary=None, graduation_date=None):
        self.execute(
            'INSERT INTO users (name, username, resume, expected_salary, graduation_date) VALUES (?, ?, ?, ?, ?)',
            (name, username, resume, expected_salary, graduation_date)
        )

    def get_user(self, username):
        return self.fetchone('SELECT * FROM users WHERE username = ?', (username,))
    
    def update_user(self,username, resume=None, expected_salary=None, graduation_date=None):
        updates = []
        params = []
        if resume:
            updates.append("resume = ?")
            params.append(resume)
        if expected_salary is not None:
            updates.append("expected_salary = ?")
            params.append(expected_salary)
        if graduation_date:
            updates.append("graduation_date = ?")
            params.append(graduation_date)

        if updates:
            query = f"UPDATE users SET {', '.join(updates)} WHERE username = ?"
            params.append(username)
            self.execute(query, tuple(params))


if __name__ == "__main__":
    db = SQLiteDB("jobs.db")
    db.execute("ALTER TABLE jobs ADD COLUMN checked BOOLEAN DEFAULT 0")
    db.close()
