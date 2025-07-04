# db.py
import sqlite3

DB_PATH = "investments.db"

def get_connection():
    """
    Retorna uma conexão SQLite para o arquivo investments.db.
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_db():
    """
    Cria as tabelas principais (users, portfolio, asset_classes, favorites, user_logs)
    se elas ainda não existirem.
    Deve ser chamada uma vez no startup do app.
    """
    conn = get_connection()
    with conn:
        # Usuários
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            );
        """)
        # Carteira de ativos
        conn.execute("""
            CREATE TABLE IF NOT EXISTS portfolio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                asset_name TEXT NOT NULL,
                asset_class TEXT,
                target_percent REAL NOT NULL,
                quantity REAL NOT NULL DEFAULT 0.0,
                current_value REAL NOT NULL
            );
        """)
        # Classes de ativo
        conn.execute("""
            CREATE TABLE IF NOT EXISTS asset_classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                class_name TEXT NOT NULL,
                target_percent REAL NOT NULL DEFAULT 0.0
            );
        """)
        # Favoritos
        conn.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                ticker TEXT NOT NULL,
                company_name TEXT
            );
        """)
        # Logs de atividade
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                event_type TEXT NOT NULL,
                details TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
    # Verifica se as colunas extras existem e cria caso contrário
    cur = conn.execute("PRAGMA table_info(portfolio)")
    cols = {row[1] for row in cur.fetchall()}
    if "quantity" not in cols:
        conn.execute("ALTER TABLE portfolio ADD COLUMN quantity REAL NOT NULL DEFAULT 0.0")

    cur = conn.execute("PRAGMA table_info(asset_classes)")
    cols = {row[1] for row in cur.fetchall()}
    if "target_percent" not in cols:
        conn.execute("ALTER TABLE asset_classes ADD COLUMN target_percent REAL NOT NULL DEFAULT 0.0")

    conn.close()
