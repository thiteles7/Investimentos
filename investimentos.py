import streamlit as st
import sqlite3
import bcrypt
import yfinance as yf
import plotly.express as px
import pandas as pd
import os
from fpdf import FPDF
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta

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
        # Tabela portfolio sem asset_class inicialmente
        conn.execute('''
            CREATE TABLE IF NOT EXISTS portfolio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                asset_name TEXT NOT NULL,
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

# Garante que a tabela portfolio possua a coluna asset_class
def ensure_portfolio_table():
    conn = get_db_connection()
    cur = conn.execute("PRAGMA table_info(portfolio)")
    columns = [row["name"] for row in cur.fetchall()]
    if "asset_class" not in columns:
        with conn:
            conn.execute("ALTER TABLE portfolio ADD COLUMN asset_class TEXT")
    conn.close()

# Cria as tabelas e ajusta a estrutura
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

# ---------------- FUNÇÕES DE CARTEIRA ------------------
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

# ---------------- NOVAS FUNCIONALIDADES: HISTÓRICO DE PREÇOS E ALERTAS ----------------

def historico_precos_page(username: str):
    st.subheader("Histórico de Preços")
    # Permite escolher um ticker ou selecionar a partir da carteira
    portfolio = get_portfolio(username)
    tickers = list({row["asset_name"] for row in portfolio}) if portfolio else []
    ticker_choice = st.selectbox("Selecione um ticker:", options=[""] + tickers)
    ticker_input = st.text_input("Ou insira um ticker:", value=ticker_choice)
    
    period_options = {
        "1 mês": "1mo",
        "3 meses": "3mo",
        "6 meses": "6mo",
        "1 ano": "1y",
        "5 anos": "5y",
        "Máximo": "max"
    }
    selected_period = st.selectbox("Selecione o período:", options=list(period_options.keys()))
    
    if ticker_input:
        ticker = ticker_input.strip().upper()
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period=period_options[selected_period])
            if hist.empty:
                st.error("Nenhum dado histórico encontrado.")
            else:
                st.line_chart(hist["Close"])
                st.write(hist.tail())
        except Exception as e:
            st.error(f"Erro ao buscar dados históricos: {e}")

def alertas_page(username: str):
    st.subheader("Alertas de Preço")
    ticker = st.text_input("Ticker para monitorar:", value="")
    condition = st.selectbox("Condição:", options=["Abaixo de", "Acima de"])
    threshold = st.number_input("Valor de Alerta (R$):", min_value=0.0, step=0.01)
    if st.button("Checar Alerta"):
        if ticker:
            ticker = ticker.strip().upper()
            current_price = fetch_stock_price(ticker)
            if current_price is None:
                st.error("Não foi possível obter a cotação atual.")
            else:
                st.write(f"Cotação atual de {ticker}: R$ {current_price:.2f}")
                if condition == "Abaixo de" and current_price < threshold:
                    st.error(f"Alerta: {ticker} está abaixo de R$ {threshold:.2f}!")
                elif condition == "Acima de" and current_price > threshold:
                    st.error(f"Alerta: {ticker} está acima de R$ {threshold:.2f}!")
                else:
                    st.success("Nenhum alerta no momento.")
        else:
            st.warning("Insira um ticker para monitorar.")

# ---------------- PÁGINAS EXISTENTES (Dashboard, Relatórios, Histórico de Logs, Notícias) ----------------

def dashboard_page(username: str):
    st.subheader("Dashboard")
    portfolio = get_portfolio(username)
    if not portfolio:
        st.info("Nenhum ativo cadastrado para análise.")
        return
    df_port = pd.DataFrame(portfolio, columns=portfolio[0].keys())
    total_value = df_port["current_value"].sum()
    st.metric(label="Valor Total da Carteira", value=f"R$ {total_value:,.2f}")
    if "asset_class" in df_port.columns:
        fig_pie = px.pie(df_port, names="asset_class", values="current_value",
                         title="Distribuição por Classe")
        st.plotly_chart(fig_pie, use_container_width=True)
    df_top = df_port.sort_values(by="current_value", ascending=False).head(5)
    fig_bar = px.bar(df_top, x="asset_name", y="current_value",
                     title="Top 5 Ativos por Valor",
                     labels={"asset_name": "Ativo", "current_value": "Valor Atual"})
    st.plotly_chart(fig_bar, use_container_width=True)

def relatorios_page(username: str):
    st.subheader("Relatórios Avançados")
    portfolio = get_portfolio(username)
    if not portfolio:
        st.info("Nenhum ativo para gerar relatório.")
        return
    df_port = pd.DataFrame(portfolio, columns=portfolio[0].keys())
    asset_classes = df_port["asset_class"].dropna().unique().tolist()
    selected_classes = st.multiselect("Filtrar por Classe de Ativo:", options=asset_classes, default=asset_classes)
    min_value, max_value = st.slider("Filtrar por Valor Atual (R$):", 
                                     float(df_port["current_value"].min()), 
                                     float(df_port["current_value"].max()),
                                     (float(df_port["current_value"].min()), float(df_port["current_value"].max())))
    df_filtered = df_port[
        (df_port["asset_class"].isin(selected_classes)) &
        (df_port["current_value"] >= min_value) &
        (df_port["current_value"] <= max_value)
    ]
    st.dataframe(df_filtered)
    if st.button("Exportar Relatório em PDF"):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, f"Relatório de Carteira - {username}", ln=True, align="C")
        pdf.set_font("Arial", size=12)
        pdf.ln(10)
        for index, row in df_filtered.iterrows():
            pdf.cell(0, 10, f"{row['asset_name']} | Classe: {row['asset_class']} | Valor: R$ {row['current_value']:.2f}", ln=True)
        pdf_output = pdf.output(dest="S").encode("latin1")
        st.download_button(label="Baixar PDF", data=pdf_output, file_name="relatorio_carteira.pdf", mime="application/pdf")

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
                    st.markdown(f"**{news.get('title', 'Sem Título')}**")
                    st.markdown(news.get("link", ""))
                    st.markdown(f"*{news.get('publisher', '')} - {news.get('providerPublishTime', '')}*")
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
            "Simulação", "Cotações", "Relatórios", "Histórico", 
            "Notícias", "Histórico de Preços", "Alertas", "Exportar Dados"
        ]
        menu_opcao = st.sidebar.radio("Escolha uma ação", options=menu_options)
        
        if menu_opcao == "Dashboard":
            dashboard_page(username)
        elif menu_opcao == "Carteira":
            st.subheader("Sua Carteira")
            portfolio = get_portfolio(username)
            if portfolio:
                df_port = pd.DataFrame(portfolio, columns=portfolio[0].keys())
                order_by = st.selectbox("Ordenar por:", options=["asset_name", "current_value", "target_percent"])
                df_port = df_port.sort_values(by=order_by, ascending=True)
                total_carteira = df_port["current_value"].sum()
                st.metric(label="Valor Total da Carteira", value=f"R$ {total_carteira:,.2f}")
                st.dataframe(df_port)
                st.write("### Atualize ou Remova Ativos")
                for _, row in df_port.iterrows():
                    col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 2, 2, 2, 1])
                    novo_nome = col1.text_input("Ativo", value=row["asset_name"], key=f"nome_{row['id']}_{username}")
                    novo_classe = col2.text_input("Classe", value=row["asset_class"] if row["asset_class"] else "", key=f"classe_{row['id']}_{username}")
                    novo_percent = col3.number_input("% Alvo", value=row["target_percent"], key=f"percent_{row['id']}_{username}")
                    novo_valor = col4.number_input("Valor Atual", value=row["current_value"], step=0.01, key=f"valor_{row['id']}_{username}")
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
                fig_pie = px.pie(df_port, names="asset_name", values="current_value",
                                 title="Distribuição da Carteira")
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("Nenhum ativo cadastrado.")
        elif menu_opcao == "Nova Ação":
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
                    if cotacao_atual is None:
                        valor_atual = st.number_input("Valor Atual", min_value=0.0, step=0.01)
                    else:
                        valor_atual = cotacao_atual
                    if fetch_stock_price(novo_ticker.upper()) is None:
                        st.error("Não foi possível validar o ticker. Verifique se está correto.")
                    else:
                        add_asset(username, novo_ticker, novo_classe, novo_percentual, valor_atual)
                        st.success("Ativo adicionado manualmente com sucesso!")
                        safe_rerun()
            st.markdown("---")
            st.write("#### Upload de Planilha para Adição de Ativos")
            st.info("A planilha deve ter 4 colunas (de A a D): 'Ticker', 'Valor Aplicado', 'Saldo Bruto' e 'Classe do Ativo'. Você pode carregar arquivos CSV ou Excel (XLS/XLSX).")
            has_header = st.checkbox("O arquivo possui cabeçalho?", value=True, key="header_check")
            uploaded_file = st.file_uploader("Faça upload do arquivo", type=["csv", "xlsx", "xls"])
            if uploaded_file is not None:
                try:
                    if uploaded_file.name.endswith(".csv"):
                        df = pd.read_csv(uploaded_file, header=0 if has_header else None)
                    elif uploaded_file.name.endswith((".xls", ".xlsx")):
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
        elif menu_opcao == "Classes de Ativos":
            st.subheader("Gerencie suas Classes de Ativos")
            classes = get_asset_classes(username)
            if classes:
                df_classes = pd.DataFrame(classes, columns=classes[0].keys())
                st.dataframe(df_classes)
                for _, row in df_classes.iterrows():
                    col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
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
        elif menu_opcao == "Relatórios":
            relatorios_page(username)
        elif menu_opcao == "Histórico":
            historico_page(username)
        elif menu_opcao == "Notícias":
            noticias_page(username)
        elif menu_opcao == "Histórico de Preços":
            historico_precos_page(username)
        elif menu_opcao == "Alertas":
            alertas_page(username)
        elif menu_opcao == "Exportar Dados":
            st.subheader("Exportar sua Carteira")
            portfolio = get_portfolio(username)
            if portfolio:
                df_port = pd.DataFrame(portfolio, columns=portfolio[0].keys())
                csv_data = df_port.to_csv(index=False).encode('utf-8')
                st.download_button(label="Download CSV", data=csv_data, file_name="portfolio.csv", mime="text/csv")
            else:
                st.info("Nenhum dado para exportar.")
        
        if st.sidebar.button("Sair"):
            st.session_state.logged_in = False
            st.session_state.pop("searched_asset", None)
            st.experimental_set_query_params()
            safe_rerun()

if __name__ == "__main__":
    main()
