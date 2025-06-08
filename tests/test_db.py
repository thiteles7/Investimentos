import sqlite3
import db

# Para executar os testes, rode `pytest` na raiz do projeto.

def test_initialize_db_creates_tables(tmp_path):
    # Usa um arquivo SQLite temporário para não interferir em dados reais
    db.DB_PATH = str(tmp_path / "test_investments.db")
    db.initialize_db()

    conn = sqlite3.connect(db.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    expected = {"users", "portfolio", "asset_classes", "favorites", "user_logs"}
    for table in expected:
        assert table in tables
    conn.close()
