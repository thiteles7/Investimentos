import streamlit as st
import sqlite3
import bcrypt
import yfinance as yf
import plotly.express as px
import pandas as pd
import os

# ---------------- CONFIGURAÇÃO ------------------
DB_PATH = "investments.db"

# Criação/Conexão com o banco de dados SQLite
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Criação das tabelas necessárias (usuários e carteira) se não existirem
def create_tables(conn):
    with conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS portfolio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                asset_name TEXT NOT NULL,
                target_percent REAL NOT NULL,
                current_value REAL NOT NULL
            )
        ''')

conn = get_db_connection()
create_tables(conn)

# ---------------- FUNÇÕES DE USUÁRIO ------------------
def get_user(username: str):
    cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
    return cur.fetchone()

def create_user(username: str, password: str):
    pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    try:
        with conn:
            conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                         (username, pw_hash))
        return True
    except sqlite3.IntegrityError:
        return False

def verify_user(username: str, password: str):
    user = get_user(username)
    if user:
        stored_hash = user["password_hash"].encode('utf-8')
        return bcrypt.checkpw(password.encode('utf-8'), stored_hash)
    return False

# ---------------- FUNÇÕES DE CARTEIRA ------------------
def get_portfolio(username: str):
    cur = conn.execute("SELECT * FROM portfolio WHERE username = ?", (username,))
    return cur.fetchall()

def add_asset(username: str, asset_name: str, target_percent: float, current_value: float):
    with conn:
        conn.execute(
            "INSERT INTO portfolio (username, asset_name, target_percent, current_value) VALUES (?, ?, ?, ?)",
            (username, asset_name.upper(), target_percent, current_value)
        )

def update_asset(asset_id: int, asset_name: str, target_percent: float, current_value: float):
    with conn:
        conn.execute(
            "UPDATE portfolio SET asset_name = ?, target_percent = ?, current_value = ? WHERE id = ?",
            (asset_name.upper(), target_percent, current_value, asset_id)
        )

def delete_asset(asset_id: int):
    with conn:
        conn.execute("DELETE FROM portfolio WHERE id = ?", (asset_id,))

# ---------------- FUNÇÕES DE FINANÇAS ------------------
def fetch_stock_price(ticker: str):
    # Tenta buscar cotação atual via yfinance
    try:
        stock = yf.Ticker(ticker)
        data = stock.history(period="1d")
        if not data.empty:
            price = data["Close"].iloc[-1]
            return price
    except Exception as e:
        st.error(f"Erro ao buscar cotação do ativo {ticker}: {e}")
    return None

def simulate_rebalance(portfolio_df: pd.DataFrame, extra_amount: float):
    total_current = portfolio_df["current_value"].sum()
    total_new = total_current + extra_amount
    # Calcula o valor ideal e a diferença (aporte ideal) para cada ativo
    portfolio_df["ideal_value"] = portfolio_df["target_percent"] / 100 * total_new
    portfolio_df["aporte_ideal"] = portfolio_df["ideal_value"] - portfolio_df["current_value"]
    return portfolio_df, total_current, total_new

# ---------------- INTERFACE DO STREAMLIT ------------------
def main():
    st.set_page_config(page_title="Investimentos", layout="wide")
    st.sidebar.title("Navegação")

    # Estado de autenticação com session_state
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        menu = st.sidebar.selectbox("Menu", ["Login", "Criar Novo Usuário"])
        if menu == "Login":
            st.title("🔐 Login")
            username = st.text_input("Nome de usuário", key="login_username")
            password = st.text_input("Senha", type="password", key="login_password")
            if st.button("Entrar"):
                if verify_user(username, password):
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.success(f"Bem-vindo, {username}!")
                else:
                    st.error("Nome de usuário ou senha incorretos.")
        else:
            st.title("📋 Criar Novo Usuário")
            new_username = st.text_input("Novo nome de usuário", key="new_username")
            new_password = st.text_input("Nova senha", type="password", key="new_password")
            if st.button("Criar Usuário"):
                if new_username and new_password:
                    if create_user(new_username, new_password):
                        st.success("Usuário criado com sucesso. Faça login agora!")
                    else:
                        st.error("Este nome de usuário já existe. Tente outro.")
                else:
                    st.warning("Preencha todos os campos.")
    else:
        username = st.session_state.username
        st.title("💰 App de Investimentos - Dashboard")
        st.sidebar.write(f"Usuário: {username}")
        menu_opcao = st.sidebar.radio("Escolha uma ação", ["Carteira", "Nova Ação", "Simulação", "Exportar Dados"])

        if menu_opcao == "Carteira":
            st.subheader("Sua Carteira")
            portfolio = get_portfolio(username)
            if portfolio:
                # Converte para DataFrame para facilitar visualizações
                df_port = pd.DataFrame(portfolio, columns=portfolio[0].keys())
                st.dataframe(df_port)
                # Possibilidade de atualizar ou remover ativos
                st.write("### Atualize ou Remova Ativos")
                for i, row in df_port.iterrows():
                    col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 1])
                    novo_nome = col1.text_input("Ativo", value=row["asset_name"], key=f"nome_{row['id']}")
                    novo_percent = col2.number_input("% Alvo", value=row["target_percent"], key=f"percent_{row['id']}")
                    novo_valor = col3.number_input("Valor Atual", value=row["current_value"], step=0.01, key=f"valor_{row['id']}")
                    atualizar = col4.button("Atualizar", key=f"atualizar_{row['id']}")
                    remover = col5.button("🗑️", key=f"remover_{row['id']}")
                    if atualizar:
                        update_asset(row["id"], novo_nome, novo_percent, novo_valor)
                        st.success(f"Ativo {novo_nome} atualizado.")
                        st.experimental_rerun()
                    if remover:
                        delete_asset(row["id"])
                        st.success(f"Ativo {novo_nome} removido.")
                        st.experimental_rerun()
            else:
                st.info("Nenhum ativo cadastrado.")

        elif menu_opcao == "Nova Ação":
            st.subheader("Adicionar Novo Ativo")
            with st.form("form_novo_ativo", clear_on_submit=True):
                novo_ticker = st.text_input("Ticker do Ativo (ex.: PETR4.SA ou AAPL)")
                novo_percentual = st.number_input("% Alvo", min_value=0.0, step=0.1)
                # Permite buscar o valor atual via yfinance
                cotacao_atual = None
                if novo_ticker:
                    if st.form_submit_button("Buscar Cotação"):
                        cotacao_atual = fetch_stock_price(novo_ticker.upper())
                        if cotacao_atual:
                            st.success(f"Cotação atual de {novo_ticker.upper()}: R$ {cotacao_atual:.2f}")
                        else:
                            st.error("Não foi possível buscar a cotação.")
                if st.form_submit_button("Adicionar Ativo"):
                    # Se não foi buscado, o usuário precisa informar manualmente
                    valor_atual = cotacao_atual if cotacao_atual is not None else st.number_input("Valor Atual", min_value=0.0, step=0.01)
                    add_asset(username, novo_ticker, novo_percentual, valor_atual)
                    st.success("Ativo adicionado com sucesso!")
                    st.experimental_rerun()

        elif menu_opcao == "Simulação":
            st.subheader("Simulação de Aporte e Rebalanceamento")
            portfolio = get_portfolio(username)
            if portfolio:
                df_port = pd.DataFrame(portfolio, columns=portfolio[0].keys())
                df_port["target_percent"] = df_port["target_percent"].astype(float)
                df_port["current_value"] = df_port["current_value"].astype(float)
                st.dataframe(df_port)
                aporte = st.number_input("Digite o valor do novo aporte (R$)", min_value=0.0, step=0.01)
                if st.button("Calcular Aporte Ideal"):
                    sim_df, total_atual, total_new = simulate_rebalance(df_port.copy(), aporte)
                    st.write(f"Total atual: R$ {total_atual:.2f} | Total com aporte: R$ {total_new:.2f}")
                    st.write("### Sugestão de Aporte Ideal")
                    st.dataframe(sim_df[["asset_name", "current_value", "ideal_value", "aporte_ideal"]])
                    # Gráfico interativo de aporte ideal
                    fig = px.bar(sim_df, x="asset_name", y="aporte_ideal",
                                 title="Aporte Ideal por Ativo",
                                 labels={"asset_name": "Ativo", "aporte_ideal": "Aporte Ideal (R$)"})
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Nenhum ativo cadastrado para simulação.")

        elif menu_opcao == "Exportar Dados":
            st.subheader("Exportar sua Carteira")
            portfolio = get_portfolio(username)
            if portfolio:
                df_port = pd.DataFrame(portfolio, columns=portfolio[0].keys())
                csv_data = df_port.to_csv(index=False).encode('utf-8')
                st.download_button(label="Download CSV", data=csv_data, file_name="portfolio.csv", mime="text/csv")
            else:
                st.info("Nenhum dado para exportar.")

        st.sidebar.button("Sair", on_click=logout)

def logout():
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.experimental_rerun()

if __name__ == "__main__":
    main()
