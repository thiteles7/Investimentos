import streamlit as st
import sqlite3
import bcrypt
import yfinance as yf
import plotly.express as px
import pandas as pd
import numpy as np
import os
from fpdf import FPDF2
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta
import io

# ---------------- CONFIGURAÇÃO ------------------
DB_PATH = "investments.db"

# Função auxiliar para "rerun" seguro
def safe_rerun():
    if hasattr(st, "experimental_rerun"):
        st.experimental_rerun()

# Retorna uma nova conexão com o banco para cada operação
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Criação das tabelas necessárias
def create_tables():
    conn = get_db_connection()
    with conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        ''')
        # Tabela portfolio com as colunas: asset_name, asset_class, target_percent, current_value
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
        conn.execute('''
            CREATE TABLE IF NOT EXISTS asset_classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                class_name TEXT NOT NULL,
                target_value REAL NOT NULL DEFAULT 0.0
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                ticker TEXT NOT NULL,
                company_name TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                event_type TEXT NOT NULL,
                details TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    conn.close()

# Garante que a tabela portfolio possua a coluna asset_class (migrar caso não tenha)
def ensure_portfolio_table():
    conn = get_db_connection()
    cur = conn.execute("PRAGMA table_info(portfolio)")
    columns = [row["name"] for row in cur.fetchall()]
    if "asset_class" not in columns:
        with conn:
            conn.execute("ALTER TABLE portfolio ADD COLUMN asset_class TEXT")
    conn.close()

# Inicialização do banco
create_tables()
ensure_portfolio_table()

# ---------------- FUNÇÕES DE LOG ------------------
def log_event(username: str, event_type: str, details: str = ""):
    conn = get_db_connection()
    with conn:
        conn.execute(
            "INSERT INTO user_logs (username, event_type, details) VALUES (?, ?, ?)",
            (username, event_type, details)
        )
    conn.close()

# ---------------- FUNÇÕES DE USUÁRIO ------------------
def get_user(username: str):
    conn = get_db_connection()
    cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
    result = cur.fetchone()
    conn.close()
    return result

def create_user(username: str, password: str):
    conn = get_db_connection()
    pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    try:
        with conn:
            conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, pw_hash))
        log_event(username, "Criação de usuário", "Usuário criado com sucesso.")
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def verify_user(username: str, password: str):
    user = get_user(username)
    if user:
        stored_hash = user["password_hash"].encode('utf-8')
        valid = bcrypt.checkpw(password.encode('utf-8'), stored_hash)
        if valid:
            log_event(username, "Login", "Usuário logado com sucesso.")
        return valid
    return False

# ---------------- FUNções DE CARTEIRA ------------------
def get_portfolio(username: str):
    conn = get_db_connection()
    cur = conn.execute("SELECT * FROM portfolio WHERE username = ?", (username,))
    results = cur.fetchall()
    conn.close()
    return results

def add_asset(username: str, asset_name: str, asset_class: str, target_percent: float, current_value: float):
    conn = get_db_connection()
    with conn:
        conn.execute(
            "INSERT INTO portfolio (username, asset_name, asset_class, target_percent, current_value) VALUES (?, ?, ?, ?, ?)",
            (username, asset_name.upper(), asset_class, target_percent, current_value)
        )
    log_event(username, "Adição de ativo", f"Ativo {asset_name.upper()} adicionado.")
    conn.close()

def update_asset(asset_id: int, asset_name: str, asset_class: str, target_percent: float, current_value: float, username: str):
    conn = get_db_connection()
    with conn:
        conn.execute(
            "UPDATE portfolio SET asset_name = ?, asset_class = ?, target_percent = ?, current_value = ? WHERE id = ?",
            (asset_name.upper(), asset_class, target_percent, current_value, asset_id)
        )
    log_event(username, "Atualização de ativo", f"Ativo {asset_name.upper()} atualizado.")
    conn.close()

def delete_asset(asset_id: int, username: str, asset_name: str):
    conn = get_db_connection()
    with conn:
        conn.execute("DELETE FROM portfolio WHERE id = ?", (asset_id,))
    log_event(username, "Exclusão de ativo", f"Ativo {asset_name} removido.")
    conn.close()

# ---------------- FUNÇÕES DE CLASSES DE ATIVOS ------------------
def get_asset_classes(username: str):
    conn = get_db_connection()
    cur = conn.execute("SELECT * FROM asset_classes WHERE username = ?", (username,))
    results = cur.fetchall()
    conn.close()
    return results

def add_asset_class(username: str, class_name: str, target_value: float):
    conn = get_db_connection()
    with conn:
        conn.execute(
            "INSERT INTO asset_classes (username, class_name, target_value) VALUES (?, ?, ?)",
            (username, class_name, target_value)
        )
    log_event(username, "Adição de classe de ativo", f"Classe {class_name} adicionada.")
    conn.close()

def update_asset_class(class_id: int, class_name: str, target_value: float, username: str):
    conn = get_db_connection()
    with conn:
        conn.execute(
            "UPDATE asset_classes SET class_name = ?, target_value = ? WHERE id = ?",
            (class_name, target_value, class_id)
        )
    log_event(username, "Atualização de classe", f"Classe {class_name} atualizada.")
    conn.close()

def delete_asset_class(class_id: int, username: str, class_name: str):
    conn = get_db_connection()
    with conn:
        conn.execute("DELETE FROM asset_classes WHERE id = ?", (class_id,))
    log_event(username, "Exclusão de classe", f"Classe {class_name} removida.")
    conn.close()

# ---------------- FUNÇÕES DE FAVORITOS ------------------
def get_favorites(username: str):
    conn = get_db_connection()
    cur = conn.execute("SELECT * FROM favorites WHERE username = ?", (username,))
    results = cur.fetchall()
    conn.close()
    return results

def add_favorite(username: str, ticker: str, company_name: str):
    conn = get_db_connection()
    with conn:
        conn.execute(
            "INSERT INTO favorites (username, ticker, company_name) VALUES (?, ?, ?)",
            (username, ticker.upper(), company_name)
        )
    log_event(username, "Adição de favorito", f"Ticker {ticker.upper()} adicionado aos favoritos.")
    conn.close()

def delete_favorite(fav_id: int, username: str, ticker: str):
    conn = get_db_connection()
    with conn:
        conn.execute("DELETE FROM favorites WHERE id = ?", (fav_id,))
    log_event(username, "Exclusão de favorito", f"Ticker {ticker} removido dos favoritos.")
    conn.close()

# ---------------- FUNÇÕES FINANCEIRAS ------------------

def fetch_stock_price(ticker: str):
    """
    Retorna o último preço de fechamento do ticker (ou None em caso de erro).
    """
    try:
        stock = yf.Ticker(ticker)
        data = stock.history(period="1d")
        if not data.empty:
            return float(data["Close"].iloc[-1])
    except Exception as e:
        return None
    return None

def get_stock_info(ticker: str):
    """
    Retorna o dicionário 'info' do yfinance para esse ticker (ou None em caso de erro).
    """
    try:
        stock = yf.Ticker(ticker)
        return stock.info
    except Exception:
        return None

def update_portfolio_prices(username: str):
    """
    Para cada ativo cadastrado no portfolio do usuário, busca o preço atual via yfinance
    e atualiza o campo current_value (pressupõe que current_value armazena o valor de mercado).
    """
    portfolio = get_portfolio(username)
    conn = get_db_connection()
    with conn:
        for row in portfolio:
            ticker = row["asset_name"].strip().upper()
            price = fetch_stock_price(ticker)
            if price is not None:
                # Supondo que current_value = quantidade de ativos * preço,
                # MAS como o modelo atual só armazena o valor total do investido (sem qtd),
                # iremos considerar que current_value representa o valor total = preço atual.
                # Caso você queira manter quantidade em vez de valor, é só alterar a estrutura.
                conn.execute(
                    "UPDATE portfolio SET current_value = ? WHERE id = ?",
                    (price, row["id"])
                )
    conn.close()

def calcular_alocacao(df_port: pd.DataFrame):
    """
    Calcula a alocação atual (%) de cada ativo a partir dos valores de mercado,
    comparando com target_percent armazenado.
    Retorna um DataFrame com colunas: asset_name, current_value, target_percent, aloc_atual_pct.
    """
    total = df_port["current_value"].sum()
    df_port["aloc_atual_pct"] = df_port["current_value"].apply(
        lambda x: (x / total * 100) if total > 0 else 0
    )
    return df_port

def sugerir_rebalance(df_port: pd.DataFrame):
    """
    Para cada ativo, calcula o valor alvo em R$ (target_percent% do total)
    e a diferença entre valor alvo e valor atual.
    Retorna DataFrame com colunas: asset_name, current_value, target_percent, valor_alvo, diff.
    """
    total = df_port["current_value"].sum()
    df_port["valor_alvo"] = df_port["target_percent"] / 100 * total
    df_port["diff"] = df_port["valor_alvo"] - df_port["current_value"]
    return df_port

# ---------------- PÁGINAS EXISTENTES (Dashboard, Carteira, Relatórios, Histórico de Logs, Notícias, etc.) ----------------

def dashboard_page(username: str):
    st.subheader("Dashboard")
    portfolio = get_portfolio(username)
    if not portfolio:
        st.info("Nenhum ativo cadastrado para análise.")
        return
    # Atualiza preços automaticamente antes de mostrar o dashboard
    update_portfolio_prices(username)
    portfolio = get_portfolio(username)
    df_port = pd.DataFrame(portfolio, columns=portfolio[0].keys())

    # Cálculo de totais e alocação
    total_value = df_port["current_value"].sum()
    st.metric(label="Valor Total da Carteira", value=f"R$ {total_value:,.2f}")

    # Gráfico de pizza por classe de ativo
    if "asset_class" in df_port.columns:
        st.markdown("**Distribuição por Classe de Ativo**")
        fig_pie = px.pie(df_port, names="asset_class", values="current_value",
                         title="Distribuição por Classe")
        st.plotly_chart(fig_pie, use_container_width=True)

    # Top 5 ativos por valor
    df_top = df_port.sort_values(by="current_value", ascending=False).head(5)
    st.markdown("**Top 5 Ativos por Valor**")
    fig_bar = px.bar(df_top, x="asset_name", y="current_value",
                     title="Top 5 Ativos",
                     labels={"asset_name": "Ativo", "current_value": "Valor Atual (R$)"})
    st.plotly_chart(fig_bar, use_container_width=True)

def carteira_page(username: str):
    st.subheader("Sua Carteira")
    portfolio = get_portfolio(username)
    if portfolio:
        # Atualiza preços antes de exibir
        update_portfolio_prices(username)
        portfolio = get_portfolio(username)
        df_port = pd.DataFrame(portfolio, columns=portfolio[0].keys())

        # Ordenação interativa
        order_by = st.selectbox("Ordenar por:", options=["asset_name", "current_value", "target_percent"])
        df_port = df_port.sort_values(by=order_by, ascending=True)

        total_carteira = df_port["current_value"].sum()
        st.metric(label="Valor Total da Carteira", value=f"R$ {total_carteira:,.2f}")
        st.dataframe(df_port.style.format({
            "current_value": "R$ {:,.2f}",
            "target_percent": "{:.2f}%",
        }), height=300)

        st.write("### Atualize ou Remova Ativos")
        for _, row in df_port.iterrows():
            col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 1.5, 1.5, 1, 1])
            novo_nome = col1.text_input("Ativo", value=row["asset_name"], key=f"nome_{row['id']}_{username}")
            novo_classe = col2.text_input("Classe", value=row["asset_class"] if row["asset_class"] else "", key=f"classe_{row['id']}_{username}")
            novo_percent = col3.number_input("% Alvo", value=row["target_percent"], key=f"percent_{row['id']}_{username}")
            novo_valor = col4.number_input("Valor Atual (R$)", value=row["current_value"], step=0.01, key=f"valor_{row['id']}_{username}")
            atualizar = col5.button("Atualizar", key=f"atualizar_{row['id']}_{username}")
            remover = col6.button("🗑️", key=f"remover_{row['id']}_{username}")
            if atualizar:
                update_asset(row["id"], novo_nome, novo_classe, novo_percent, novo_valor, username)
                st.success(f"Ativo {novo_nome} atualizado.")
                safe_rerun()
            if remover:
                delete_asset(row["id"], username, row["asset_name"])
                st.success(f"Ativo {row['asset_name']} removido.")
                safe_rerun()

        # Gráfico de pizza por ativo (distribuição)
        st.markdown("**Distribuição da Carteira por Ativo**")
        fig_pie2 = px.pie(df_port, names="asset_name", values="current_value",
                          title="Alocação Atual")
        st.plotly_chart(fig_pie2, use_container_width=True)
    else:
        st.info("Nenhum ativo cadastrado.")

def nova_acao_page(username: str):
    st.subheader("Adicionar Novo Ativo")
    st.write("#### Cadastro Manual")
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
            if st.form_submit_button("Buscar Cotação Manual"):
                cotacao_atual = fetch_stock_price(novo_ticker.upper())
                if cotacao_atual:
                    st.success(f"Cotação atual de {novo_ticker.upper()}: R$ {cotacao_atual:.2f}")
                else:
                    st.error("Ticker inválido ou cotação não encontrada.")
        if st.form_submit_button("Adicionar Ativo Manualmente"):
            if novo_ticker.strip() == "":
                st.error("Insira um ticker válido.")
            else:
                ticker_upper = novo_ticker.upper()
                # Se não buscou cotação, deixar current_value como zero até edição manual
                valor_atual = cotacao_atual if cotacao_atual is not None else 0.0
                add_asset(username, ticker_upper, novo_classe, novo_percentual, valor_atual)
                st.success("Ativo adicionado manualmente com sucesso!")
                safe_rerun()

    st.markdown("---")
    st.write("#### Upload de Planilha para Adição de Ativos")
    st.info("A planilha deve ter 4 colunas (de A a D): 'Ticker', 'Valor Aplicado', 'Saldo Bruto' e 'Classe do Ativo'.")
    has_header = st.checkbox("O arquivo possui cabeçalho?", value=True, key="header_check")
    uploaded_file = st.file_uploader("Faça upload do arquivo", type=["csv", "xlsx", "xls"])
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith(".csv"):
                df = pd.read_csv(uploaded_file, header=0 if has_header else None)
            else:
                # xls ou xlsx
                if has_header:
                    df = pd.read_excel(uploaded_file, engine="openpyxl" if uploaded_file.name.endswith(".xlsx") else "xlrd")
                else:
                    df = pd.read_excel(uploaded_file, engine="openpyxl" if uploaded_file.name.endswith(".xlsx") else "xlrd", header=None)
            st.write("Visualização dos dados carregados:")
            st.dataframe(df.head())
            for index, row in df.iterrows():
                try:
                    ticker = str(row.iloc[0]).strip().upper()
                    valor_aplicado = float(row.iloc[1])
                    saldo_bruto = float(row.iloc[2])
                    asset_class = str(row.iloc[3]).strip()
                except Exception as e:
                    st.error(f"Erro ao processar a linha {index}: {e}")
                    continue
                current_value = saldo_bruto
                add_asset(username, ticker, asset_class, 0.0, current_value)
            st.success("Ativos adicionados via upload com sucesso!")
            safe_rerun()
        except Exception as e:
            st.error("Erro ao processar o arquivo: " + str(e))

def classes_de_ativos_page(username: str):
    st.subheader("Gerencie suas Classes de Ativos")
    classes = get_asset_classes(username)
    if classes:
        df_classes = pd.DataFrame(classes, columns=classes[0].keys())
        st.dataframe(df_classes)
        for _, row in df_classes.iterrows():
            col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
            novo_nome = col1.text_input("Classe", value=row["class_name"], key=f"class_name_{row['id']}_{username}")
            novo_target = col2.number_input("Valor Alvo (R$)", value=row["target_value"], step=0.01, key=f"target_{row['id']}_{username}")
            atualizar = col3.button("Atualizar", key=f"update_class_{row['id']}_{username}")
            remover = col4.button("Remover", key=f"delete_class_{row['id']}_{username}")
            if atualizar:
                update_asset_class(row["id"], novo_nome, novo_target, username)
                st.success(f"Classe {novo_nome} atualizada.")
                safe_rerun()
            if remover:
                delete_asset_class(row["id"], username, row["class_name"])
                st.success(f"Classe {row['class_name']} removida.")
                safe_rerun()
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
                safe_rerun()

def simulacao_page(username: str):
    st.subheader("Simulação de Aporte e Rebalanceamento")
    portfolio = get_portfolio(username)
    if portfolio:
        # Atualiza preços antes de simular
        update_portfolio_prices(username)
        portfolio = get_portfolio(username)
        df_port = pd.DataFrame(portfolio, columns=portfolio[0].keys())

        st.write("### Carteira Atual")
        st.dataframe(df_port.style.format({
            "current_value": "R$ {:,.2f}",
            "target_percent": "{:.2f}%"
        }), height=250)

        aporte = st.number_input("Digite o valor do novo aporte (R$)", min_value=0.0, step=0.01, value=0.0)
        if st.button("Simular Aporte por Ativo"):
            df_reb, total_atual, total_new = simulate_rebalance_assets(df_port.copy(), aporte)
            st.write(f"**Total Atual:** R$ {total_atual:,.2f} | **Total com Aporte:** R$ {total_new:,.2f}")
            st.write("#### Sugestão de Aporte Ideal por Ativo")
            st.dataframe(df_reb[["asset_name", "current_value", "ideal_value", "aporte_ideal"]].style.format({
                "current_value": "R$ {:,.2f}",
                "ideal_value": "R$ {:,.2f}",
                "aporte_ideal": "R$ {:,.2f}"
            }), height=250)

            fig = px.bar(df_reb, x="asset_name", y="aporte_ideal",
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
            st.dataframe(df_merge[["class_name", "current_value", "target_value", "aporte_ideal"]].style.format({
                "current_value": "R$ {:,.2f}",
                "target_value": "R$ {:,.2f}",
                "aporte_ideal": "R$ {:,.2f}"
            }), height=250)

            fig2 = px.bar(df_merge, x="class_name", y="aporte_ideal",
                          title="Aporte Ideal por Classe de Ativo",
                          labels={"class_name": "Classe de Ativo", "aporte_ideal": "Aporte Ideal (R$)"})
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Nenhuma classe de ativo definida para simulação.")
    else:
        st.info("Nenhum ativo cadastrado para simulação.")

# Reaproveitamos a função simulate_rebalance_assets original
def simulate_rebalance_assets(portfolio_df: pd.DataFrame, extra_amount: float):
    total_current = portfolio_df["current_value"].sum()
    total_new = total_current + extra_amount
    portfolio_df["ideal_value"] = portfolio_df["target_percent"] / 100 * total_new
    portfolio_df["aporte_ideal"] = portfolio_df["ideal_value"] - portfolio_df["current_value"]
    return portfolio_df, total_current, total_new

def cotacoes_page(username: str):
    st.subheader("Consulta de Ativos, Ações e FIIs da B3")
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
                st.session_state["searched_asset"] = {"ticker": ticker, "shortName": shortName, "price": price}
            else:
                st.error("Ativo não encontrado. Verifique o ticker ou nome da empresa/fundo.")
    if "searched_asset" in st.session_state:
        asset = st.session_state["searched_asset"]
        st.write(f"**{asset['shortName']} ({asset['ticker']})** - Cotação Atual: R$ {asset['price']:.2f}")
        if st.button("Favoritar Este Ativo", key="favorite_button"):
            add_favorite(username, asset["ticker"], asset["shortName"])
            st.success(f"{asset['shortName']} adicionado aos favoritos!")
            st.session_state.pop("searched_asset")
            safe_rerun()
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
                if col3.button("Remover", key=f"rem_fav_{fav['id']}_{username}"):
                    delete_favorite(fav["id"], username, ticker)
                    st.success(f"{shortName} removido dos favoritos.")
                    safe_rerun()
            else:
                st.write(f"Não foi possível obter a cotação para {ticker}.")
    else:
        st.info("Nenhum ativo favoritado.")

def relatorios_avancados_page(username: str):
    st.subheader("Relatórios Avançados")
    # Antes de gerar relatório, atualiza preços
    update_portfolio_prices(username)
    portfolio = get_portfolio(username)
    if not portfolio:
        st.info("Nenhum ativo para gerar relatório.")
        return

    df_port = pd.DataFrame(portfolio, columns=portfolio[0].keys())
    df_port = calcular_alocacao(df_port)

    st.write("### Alocação Atual (%) × Alocação Desejada (%)")
    df_display = df_port[["asset_name", "current_value", "target_percent", "aloc_atual_pct"]].copy()
    df_display = df_display.rename(columns={
        "asset_name": "Ativo",
        "current_value": "Valor Atual (R$)",
        "target_percent": "Alocação Desejada (%)",
        "aloc_atual_pct": "Alocação Atual (%)"
    })
    st.dataframe(df_display.style.format({
        "Valor Atual (R$)": "R$ {:,.2f}",
        "Alocação Desejada (%)": "{:.2f}%",
        "Alocação Atual (%)": "{:.2f}%"
    }), height=300)

    # Gráfico comparativo de alocação
    fig_alloc = px.bar(df_port, x="asset_name", y=["aloc_atual_pct", "target_percent"],
                       barmode="group",
                       labels={"asset_name": "Ativo", "value": "Percentual (%)", "variable": "Tipo"},
                       title="Alocação Atual vs Desejada")
    st.plotly_chart(fig_alloc, use_container_width=True)

    # Sugerir rebalance
    df_reb = sugerir_rebalance(df_port.copy())
    st.write("### Sugestão de Rebalance (em R$)")
    df_reb_display = df_reb[["asset_name", "current_value", "valor_alvo", "diff"]].rename(columns={
        "asset_name": "Ativo",
        "current_value": "Valor Atual (R$)",
        "valor_alvo": "Valor Alvo (R$)",
        "diff": "Diferença (R$)"
    })
    st.dataframe(df_reb_display.style.format({
        "Valor Atual (R$)": "R$ {:,.2f}",
        "Valor Alvo (R$)": "R$ {:,.2f}",
        "Diferença (R$)": "R$ {:,.2f}"
    }), height=300)
    st.write("*Valores positivos em 'Diferença (R$)' indicam aporte sugerido; negativos indicam saque possível.*")

    # Exportar relatório em CSV
    st.write("#### Exportar Relatório de Rebalance (CSV)")
    csv_buf = io.StringIO()
    df_reb_export = df_reb_display.copy()
    df_reb_export.to_csv(csv_buf, sep=";", float_format="%.2f", index=False)
    st.download_button(
        label="⬇️ Baixar CSV de Rebalance",
        data=csv_buf.getvalue().encode("utf-8"),
        file_name="relatorio_rebalance.csv",
        mime="text/csv"
    )

    # Exportar relatório em PDF
    if st.button("⬇️ Baixar PDF de Rebalance"):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 14)
        pdf.cell(0, 10, f"Relatório de Rebalance - {username}", ln=True, align="C")
        pdf.ln(8)
        pdf.set_font("Arial", size=12)
        for _, row in df_reb.iterrows():
            pdf.cell(0, 8, f"{row['asset_name']} | Atual: R$ {row['current_value']:,.2f} | Alvo: R$ {row['valor_alvo']:,.2f} | Diferença: R$ {row['diff']:,.2f}", ln=True)
        pdf_output = pdf.output(dest="S").encode("latin1")
        st.download_button(label="Baixar PDF", data=pdf_output, file_name="relatorio_rebalance.pdf", mime="application/pdf")

def historico_page(username: str):
    st.subheader("Histórico de Atividades")
    conn = get_db_connection()
    cur = conn.execute("SELECT * FROM user_logs WHERE username = ? ORDER BY timestamp DESC", (username,))
    logs = cur.fetchall()
    conn.close()
    if not logs:
        st.info("Nenhuma atividade registrada.")
        return
    df_logs = pd.DataFrame(logs, columns=logs[0].keys())
    event_types = df_logs["event_type"].unique().tolist()
    selected_event = st.selectbox("Filtrar por Evento:", options=["Todos"] + event_types)
    if selected_event != "Todos":
        df_logs = df_logs[df_logs["event_type"] == selected_event]
    st.dataframe(df_logs)

def noticias_page(username: str):
    st.subheader("Notícias do Mercado")
    ticker_input = st.text_input("Digite o Ticker para buscar notícias (ex.: PETR4.SA)")
    if ticker_input:
        ticker = ticker_input.strip().upper()
        stock = yf.Ticker(ticker)
        try:
            news_list = stock.news
            if news_list:
                for news in news_list:
                    titulo = news.get("title", "Sem Título")
                    link = news.get("link", "")
                    publisher = news.get("publisher", "")
                    timestamp = news.get("providerPublishTime", "")
                    st.markdown(f"**{titulo}**")
                    if link:
                        st.markdown(link)
                    st.markdown(f"*{publisher} - {timestamp}*")
                    st.markdown("---")
            else:
                st.info("Nenhuma notícia encontrada para esse ticker.")
        except Exception as e:
            st.error(f"Erro ao buscar notícias: {e}")

# ---------------- INTERFACE PRINCIPAL ------------------
def main():
    st.set_page_config(page_title="Investimentos", layout="wide")
    st.sidebar.title("Navegação")

    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    # Tela de login / criação de usuário
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
                    safe_rerun()
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

        menu_options = [
            "Dashboard", "Carteira", "Nova Ação", "Classes de Ativos",
            "Simulação", "Cotações", "Relatórios Avançados",
            "Histórico", "Notícias"
        ]
        menu_opcao = st.sidebar.radio("Escolha uma ação", options=menu_options)

        if menu_opcao == "Dashboard":
            dashboard_page(username)
        elif menu_opcao == "Carteira":
            carteira_page(username)
        elif menu_opcao == "Nova Ação":
            nova_acao_page(username)
        elif menu_opcao == "Classes de Ativos":
            classes_de_ativos_page(username)
        elif menu_opcao == "Simulação":
            simulacao_page(username)
        elif menu_opcao == "Cotações":
            cotacoes_page(username)
        elif menu_opcao == "Relatórios Avançados":
            relatorios_avancados_page(username)
        elif menu_opcao == "Histórico":
            historico_page(username)
        elif menu_opcao == "Notícias":
            noticias_page(username)

        if st.sidebar.button("Sair"):
            st.session_state.logged_in = False
            st.session_state.pop("searched_asset", None)
            st.experimental_set_query_params()
            safe_rerun()

if __name__ == "__main__":
    main()
