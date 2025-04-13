import streamlit as st
import sqlite3
import bcrypt
import yfinance as yf
import plotly.express as px
import pandas as pd
import os
from streamlit_autorefresh import st_autorefresh

# ---------------- CONFIGURAÇÃO ------------------
DB_PATH = "investments.db"

# Função que sempre retorna uma nova conexão com o banco, garantindo que as operações sejam efetivadas
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Criação das tabelas necessárias (usuários, carteira, classes e favoritos)
def create_tables():
    conn = get_db_connection()
    with conn:
        # Tabela de usuários com senha hasheada
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        ''')
        # Tabela de ativos (portfolio) com coluna asset_class
        conn.execute('''
            CREATE TABLE IF NOT EXISTS portfolio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                asset_name TEXT NOT NULL,
                asset_class TEXT,
                target_percent REAL NOT NULL,
                current_value REAL NOT NULL
            )
        ''')
        # Tabela para gerenciar as classes de ativos
        conn.execute('''
            CREATE TABLE IF NOT EXISTS asset_classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                class_name TEXT NOT NULL,
                target_value REAL NOT NULL DEFAULT 0.0
            )
        ''')
        # Tabela para armazenar os ativos favoritados
        conn.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                ticker TEXT NOT NULL,
                company_name TEXT
            )
        ''')

# Executa a criação das tabelas
create_tables()

# ---------------- FUNÇÕES DE USUÁRIO ------------------
def get_user(username: str):
    conn = get_db_connection()
    cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
    return cur.fetchone()

def create_user(username: str, password: str):
    conn = get_db_connection()
    pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    try:
        with conn:
            conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, pw_hash))
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
    conn = get_db_connection()
    cur = conn.execute("SELECT * FROM portfolio WHERE username = ?", (username,))
    return cur.fetchall()

def add_asset(username: str, asset_name: str, asset_class: str, target_percent: float, current_value: float):
    conn = get_db_connection()
    with conn:
        conn.execute(
            "INSERT INTO portfolio (username, asset_name, asset_class, target_percent, current_value) VALUES (?, ?, ?, ?, ?)",
            (username, asset_name.upper(), asset_class, target_percent, current_value)
        )

def update_asset(asset_id: int, asset_name: str, asset_class: str, target_percent: float, current_value: float):
    conn = get_db_connection()
    with conn:
        conn.execute(
            "UPDATE portfolio SET asset_name = ?, asset_class = ?, target_percent = ?, current_value = ? WHERE id = ?",
            (asset_name.upper(), asset_class, target_percent, current_value, asset_id)
        )

def delete_asset(asset_id: int):
    conn = get_db_connection()
    with conn:
        conn.execute("DELETE FROM portfolio WHERE id = ?", (asset_id,))

# ---------------- FUNÇÕES DE CLASSES DE ATIVOS ------------------
def get_asset_classes(username: str):
    conn = get_db_connection()
    cur = conn.execute("SELECT * FROM asset_classes WHERE username = ?", (username,))
    return cur.fetchall()

def add_asset_class(username: str, class_name: str, target_value: float):
    conn = get_db_connection()
    with conn:
        conn.execute(
            "INSERT INTO asset_classes (username, class_name, target_value) VALUES (?, ?, ?)",
            (username, class_name, target_value)
        )

def update_asset_class(class_id: int, class_name: str, target_value: float):
    conn = get_db_connection()
    with conn:
        conn.execute(
            "UPDATE asset_classes SET class_name = ?, target_value = ? WHERE id = ?",
            (class_name, target_value, class_id)
        )

def delete_asset_class(class_id: int):
    conn = get_db_connection()
    with conn:
        conn.execute("DELETE FROM asset_classes WHERE id = ?", (class_id,))

# ---------------- FUNÇÕES DE FAVORITOS ------------------
def get_favorites(username: str):
    conn = get_db_connection()
    cur = conn.execute("SELECT * FROM favorites WHERE username = ?", (username,))
    return cur.fetchall()

def add_favorite(username: str, ticker: str, company_name: str):
    conn = get_db_connection()
    with conn:
        conn.execute(
            "INSERT INTO favorites (username, ticker, company_name) VALUES (?, ?, ?)",
            (username, ticker.upper(), company_name)
        )

def delete_favorite(fav_id: int):
    conn = get_db_connection()
    with conn:
        conn.execute("DELETE FROM favorites WHERE id = ?", (fav_id,))

# ---------------- FUNÇÕES FINANCEIRAS ------------------
def fetch_stock_price(ticker: str):
    try:
        stock = yf.Ticker(ticker)
        data = stock.history(period="1d")
        if not data.empty:
            price = data["Close"].iloc[-1]
            return price
    except Exception as e:
        st.error(f"Erro ao buscar cotação do ativo {ticker}: {e}")
    return None

def get_stock_info(ticker: str):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        return info
    except Exception as e:
        st.error(f"Erro ao buscar informações do ativo {ticker}: {e}")
    return None

def simulate_rebalance_assets(portfolio_df: pd.DataFrame, extra_amount: float):
    total_current = portfolio_df["current_value"].sum()
    total_new = total_current + extra_amount
    portfolio_df["ideal_value"] = portfolio_df["target_percent"] / 100 * total_new
    portfolio_df["aporte_ideal"] = portfolio_df["ideal_value"] - portfolio_df["current_value"]
    return portfolio_df, total_current, total_new

# ---------------- INTERFACE DO STREAMLIT ------------------
def main():
    st.set_page_config(page_title="Investimentos", layout="wide")
    st.sidebar.title("Navegação")

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
        
        menu_opcao = st.sidebar.radio("Escolha uma ação", 
                                      ["Carteira", "Nova Ação", "Classes de Ativos", "Simulação", "Cotações", "Exportar Dados"])
        
        if menu_opcao == "Carteira":
            st.subheader("Sua Carteira")
            portfolio = get_portfolio(username)
            if portfolio:
                df_port = pd.DataFrame(portfolio, columns=portfolio[0].keys())
                st.dataframe(df_port)
                st.write("### Atualize ou Remova Ativos")
                for _, row in df_port.iterrows():
                    col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 2, 2, 2, 1])
                    novo_nome = col1.text_input("Ativo", value=row["asset_name"], key=f"nome_{row['id']}")
                    novo_classe = col2.text_input("Classe", value=row["asset_class"] if row["asset_class"] else "", key=f"classe_{row['id']}")
                    novo_percent = col3.number_input("% Alvo", value=row["target_percent"], key=f"percent_{row['id']}")
                    novo_valor = col4.number_input("Valor Atual", value=row["current_value"], step=0.01, key=f"valor_{row['id']}")
                    atualizar = col5.button("Atualizar", key=f"atualizar_{row['id']}")
                    remover = col6.button("🗑️", key=f"remover_{row['id']}")
                    if atualizar:
                        update_asset(row["id"], novo_nome, novo_classe, novo_percent, novo_valor)
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
            classes = get_asset_classes(username)
            classes_list = [cl["class_name"] for cl in classes] if classes else []
            with st.form("form_novo_ativo", clear_on_submit=True):
                novo_ticker = st.text_input("Ticker do Ativo (ex.: PETR4.SA ou AAPL)")
                novo_percentual = st.number_input("% Alvo", min_value=0.0, step=0.1)
                if classes_list:
                    novo_classe = st.selectbox("Classe do Ativo", options=classes_list)
                else:
                    novo_classe = st.text_input("Classe do Ativo (sem classes definidas)")
                cotacao_atual = None
                if novo_ticker:
                    if st.form_submit_button("Buscar Cotação"):
                        cotacao_atual = fetch_stock_price(novo_ticker.upper())
                        if cotacao_atual:
                            st.success(f"Cotação atual de {novo_ticker.upper()}: R$ {cotacao_atual:.2f}")
                        else:
                            st.error("Não foi possível buscar a cotação.")
                if st.form_submit_button("Adicionar Ativo"):
                    if cotacao_atual is None:
                        valor_atual = st.number_input("Valor Atual", min_value=0.0, step=0.01)
                    else:
                        valor_atual = cotacao_atual
                    add_asset(username, novo_ticker, novo_classe, novo_percentual, valor_atual)
                    st.success("Ativo adicionado com sucesso!")
                    st.experimental_rerun()

        elif menu_opcao == "Classes de Ativos":
            st.subheader("Gerencie suas Classes de Ativos")
            classes = get_asset_classes(username)
            if classes:
                df_classes = pd.DataFrame(classes, columns=classes[0].keys())
                st.dataframe(df_classes)
                for _, row in df_classes.iterrows():
                    col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
                    novo_nome = col1.text_input("Classe", value=row["class_name"], key=f"class_name_{row['id']}")
                    novo_target = col2.number_input("Valor Alvo (R$)", value=row["target_value"], step=0.01, key=f"target_{row['id']}")
                    atualizar = col3.button("Atualizar", key=f"update_class_{row['id']}")
                    remover = col4.button("Remover", key=f"delete_class_{row['id']}")
                    if atualizar:
                        update_asset_class(row["id"], novo_nome, novo_target)
                        st.success(f"Classe {novo_nome} atualizada.")
                        st.experimental_rerun()
                    if remover:
                        delete_asset_class(row["id"])
                        st.success(f"Classe {novo_nome} removida.")
                        st.experimental_rerun()
            else:
                st.info("Nenhuma classe de ativo cadastrada.")
            st.write("### Adicionar Nova Classe de Ativo")
            with st.form("nova_classe", clear_on_submit=True):
                nova_classe = st.text_input("Nome da Classe")
                novo_valor_alvo = st.number_input("Valor Alvo (R$)", min_value=0.0, step=0.01)
                if st.form_submit_button("Adicionar Classe"):
                    if nova_classe:
                        add_asset_class(username, nova_classe, novo_valor_alvo)
                        st.success("Classe adicionada com sucesso!")
                        st.experimental_rerun()

        elif menu_opcao == "Simulação":
            st.subheader("Simulação de Aporte e Rebalanceamento")
            portfolio = get_portfolio(username)
            if portfolio:
                df_port = pd.DataFrame(portfolio, columns=portfolio[0].keys())
                st.write("### Carteira Individual")
                st.dataframe(df_port)
                aporte = st.number_input("Digite o valor do novo aporte (R$)", min_value=0.0, step=0.01)
                if st.button("Simular Aporte por Ativo"):
                    sim_df, total_atual, total_new = simulate_rebalance_assets(df_port.copy(), aporte)
                    st.write(f"Total atual: R$ {total_atual:.2f} | Total com aporte: R$ {total_new:.2f}")
                    st.write("### Sugestão de Aporte Ideal (Por Ativo)")
                    st.dataframe(sim_df[["asset_name", "current_value", "ideal_value", "aporte_ideal"]])
                    fig = px.bar(sim_df, x="asset_name", y="aporte_ideal",
                                 title="Aporte Ideal por Ativo",
                                 labels={"asset_name": "Ativo", "aporte_ideal": "Aporte Ideal (R$)"})
                    st.plotly_chart(fig, use_container_width=True)
                
                st.write("### Simulação por Classe de Ativo")
                asset_classes = get_asset_classes(username)
                if asset_classes:
                    df_class = pd.DataFrame(asset_classes, columns=asset_classes[0].keys())
                    df_port_group = df_port.groupby("asset_class")["current_value"].sum().reset_index()
                    df_merge = pd.merge(df_class, df_port_group, how="left", left_on="class_name", right_on="asset_class")
                    df_merge["current_value"] = df_merge["current_value"].fillna(0)
                    df_merge["aporte_ideal"] = df_merge["target_value"] - df_merge["current_value"]
                    st.dataframe(df_merge[["class_name", "current_value", "target_value", "aporte_ideal"]])
                    fig2 = px.bar(df_merge, x="class_name", y="aporte_ideal",
                                  title="Aporte Ideal por Classe de Ativo",
                                  labels={"class_name": "Classe de Ativo", "aporte_ideal": "Aporte Ideal (R$)"})
                    st.plotly_chart(fig2, use_container_width=True)
                else:
                    st.info("Nenhuma classe de ativo definida para simulação.")
            else:
                st.info("Nenhum ativo cadastrado para simulação.")

        elif menu_opcao == "Cotações":
            st.subheader("Consulta de Ativos, Ações e FIIs da B3")
            
            # Campo de busca e opção para pesquisar na B3
            search_query = st.text_input("Digite o ticker ou nome da empresa/fundo")
            usar_B3 = st.checkbox("Pesquisar na B3 (.SA automaticamente)", value=True)
            
            if st.button("Buscar Ativo"):
                if search_query:
                    ticker = search_query.strip().upper()
                    if usar_B3 and not ticker.endswith(".SA"):
                        ticker = ticker + ".SA"
                    info = get_stock_info(ticker)
                    if info and "regularMarketPrice" in info:
                        price = info.get("regularMarketPrice", None)
                        shortName = info.get("shortName", ticker)
                        st.write(f"**{shortName} ({ticker})** - Cotação Atual: R$ {price:.2f}")
                        if st.button("Favoritar Este Ativo", key=f"fav_add_{ticker}"):
                            add_favorite(username, ticker, shortName)
                            st.success(f"{shortName} adicionado aos favoritos!")
                            st.experimental_rerun()
                    else:
                        st.error("Ativo não encontrado. Verifique o ticker ou nome da empresa/fundo.")
            
            # Atualiza os favoritos automaticamente a cada 30 segundos
            st_autorefresh(interval=30000, key="fav_autorefresh")
            
            st.write("### Favoritos")
            favorites = get_favorites(username)
            if favorites:
                for fav in favorites:
                    ticker = fav["ticker"]
                    info = get_stock_info(ticker)
                    if info and "regularMarketPrice" in info:
                        price = info.get("regularMarketPrice", None)
                        shortName = info.get("shortName", ticker)
                        col1, col2, col3 = st.columns([3, 2, 1])
                        col1.write(f"**{shortName} ({ticker})**")
                        col2.write(f"Cotação: R$ {price:.2f}")
                        if col3.button("Remover", key=f"rem_fav_{fav['id']}"):
                            delete_favorite(fav["id"])
                            st.success(f"{shortName} removido dos favoritos.")
                            st.experimental_rerun()
                    else:
                        st.write(f"Não foi possível obter a cotação para {ticker}.")
            else:
                st.info("Nenhum ativo favoritado.")
                        
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
