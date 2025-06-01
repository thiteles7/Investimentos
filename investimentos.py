# ------------------------- app.py -------------------------

import streamlit as st
import bcrypt
from datetime import datetime
from db import initialize_db, get_connection
import yfinance as yf
import plotly.express as px
import pandas as pd
import numpy as np

# ------------------------------------------------------------
# 1) Garante que o SQLite e as tabelas já existam
# ------------------------------------------------------------
initialize_db()

# ------------------------------------------------------------
# 2) Funções para log de eventos
# ------------------------------------------------------------
def log_event(username: str, event_type: str, details: str = ""):
    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO user_logs (username, event_type, details) VALUES (?, ?, ?)",
            (username, event_type, details)
        )
    conn.close()

# ------------------------------------------------------------
# 3) Funções de usuário: create_user, verify_user
# ------------------------------------------------------------
def create_user(username: str, password: str) -> bool:
    conn = get_connection()
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    try:
        with conn:
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, pw_hash)
            )
        log_event(username, "Criação de usuário", "Usuário criado com sucesso.")
        return True
    except:
        return False
    finally:
        conn.close()

def verify_user(username: str, password: str) -> bool:
    conn = get_connection()
    cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return False
    stored_hash = row["password_hash"].encode("utf-8")
    valid = bcrypt.checkpw(password.encode("utf-8"), stored_hash)
    if valid:
        log_event(username, "Login", "Usuário logado com sucesso.")
    return valid

# ------------------------------------------------------------
# 4) Funções de carteira (CRUD)
# ------------------------------------------------------------
def get_portfolio(username: str) -> list:
    conn = get_connection()
    cur = conn.execute("SELECT * FROM portfolio WHERE username = ?", (username,))
    results = cur.fetchall()
    conn.close()
    return results

def add_asset(username: str, asset_name: str, asset_class: str, target_percent: float, current_value: float):
    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO portfolio (username, asset_name, asset_class, target_percent, current_value) VALUES (?, ?, ?, ?, ?)",
            (username, asset_name.upper(), asset_class, target_percent, current_value)
        )
    log_event(username, "Adição de ativo", f"Ativo {asset_name.upper()} adicionado.")
    conn.close()

def update_asset(asset_id: int, asset_name: str, asset_class: str, target_percent: float, current_value: float, username: str):
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE portfolio SET asset_name = ?, asset_class = ?, target_percent = ?, current_value = ? WHERE id = ?",
            (asset_name.upper(), asset_class, target_percent, current_value, asset_id)
        )
    log_event(username, "Atualização de ativo", f"Ativo {asset_name.upper()} atualizado.")
    conn.close()

def delete_asset(asset_id: int, username: str, asset_name: str):
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM portfolio WHERE id = ?", (asset_id,))
    log_event(username, "Exclusão de ativo", f"Ativo {asset_name} removido.")
    conn.close()

# ------------------------------------------------------------
# 5) Funções de classes de ativos
# ------------------------------------------------------------
def get_asset_classes(username: str) -> list:
    conn = get_connection()
    cur = conn.execute("SELECT * FROM asset_classes WHERE username = ?", (username,))
    results = cur.fetchall()
    conn.close()
    return results

def add_asset_class(username: str, class_name: str, target_value: float):
    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO asset_classes (username, class_name, target_value) VALUES (?, ?, ?)",
            (username, class_name, target_value)
        )
    log_event(username, "Adição de classe de ativo", f"Classe {class_name} adicionada.")
    conn.close()

def update_asset_class(class_id: int, class_name: str, target_value: float, username: str):
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE asset_classes SET class_name = ?, target_value = ? WHERE id = ?",
            (class_name, target_value, class_id)
        )
    log_event(username, "Atualização de classe", f"Classe {class_name} atualizada.")
    conn.close()

def delete_asset_class(class_id: int, username: str, class_name: str):
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM asset_classes WHERE id = ?", (class_id,))
    log_event(username, "Exclusão de classe", f"Classe {class_name} removida.")
    conn.close()

# ------------------------------------------------------------
# 6) Funções de favoritos
# ------------------------------------------------------------
def get_favorites(username: str) -> list:
    conn = get_connection()
    cur = conn.execute("SELECT * FROM favorites WHERE username = ?", (username,))
    results = cur.fetchall()
    conn.close()
    return results

def add_favorite(username: str, ticker: str, company_name: str):
    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO favorites (username, ticker, company_name) VALUES (?, ?, ?)",
            (username, ticker.upper(), company_name)
        )
    log_event(username, "Adição de favorito", f"Ticker {ticker.upper()} adicionado aos favoritos.")
    conn.close()

def delete_favorite(fav_id: int, username: str, ticker: str):
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM favorites WHERE id = ?", (fav_id,))
    log_event(username, "Exclusão de favorito", f"Ticker {ticker} removido dos favoritos.")
    conn.close()

# ------------------------------------------------------------
# 7) Atualização de preços
# ------------------------------------------------------------
def fetch_stock_price(ticker: str) -> float | None:
    try:
        stock = yf.Ticker(ticker)
        data = stock.history(period="1d")
        if not data.empty:
            return float(data["Close"].iloc[-1])
    except:
        return None
    return None

def update_portfolio_prices(username: str):
    """
    Para cada ativo na carteira, busca o preço atual e salva em current_value.
    """
    assets = get_portfolio(username)
    conn = get_connection()
    with conn:
        for row in assets:
            ticker = row["asset_name"].upper()
            price = fetch_stock_price(ticker)
            if price is not None:
                conn.execute(
                    "UPDATE portfolio SET current_value = ? WHERE id = ?",
                    (price, row["id"])
                )
    conn.close()

# ------------------------------------------------------------
# 8) Cálculo de alocação e rebalance
# ------------------------------------------------------------
def calcular_alocacao(df_port: pd.DataFrame) -> pd.DataFrame:
    total = df_port["current_value"].sum()
    df_port["aloc_atual_pct"] = df_port["current_value"].apply(
        lambda x: (x / total * 100) if total > 0 else 0
    )
    return df_port

def sugerir_rebalance(df_port: pd.DataFrame) -> pd.DataFrame:
    total = df_port["current_value"].sum()
    df_port["valor_alvo"] = df_port["target_percent"] / 100 * total
    df_port["diff"] = df_port["valor_alvo"] - df_port["current_value"]
    return df_port

# Função auxiliar (mantida igual àquela que você já conhecia)
def simulate_rebalance_assets(portfolio_df: pd.DataFrame, extra_amount: float):
    total_current = portfolio_df["current_value"].sum()
    total_new = total_current + extra_amount
    portfolio_df["ideal_value"] = portfolio_df["target_percent"] / 100 * total_new
    portfolio_df["aporte_ideal"] = portfolio_df["ideal_value"] - portfolio_df["current_value"]
    return portfolio_df, total_current, total_new

# ------------------------------------------------------------
# 9) Página: Dashboard
# ------------------------------------------------------------
def dashboard_page(username: str):
    st.subheader("Dashboard")
    # Primeiro, atualiza preços (salvando no SQLite)
    update_portfolio_prices(username)

    assets = get_portfolio(username)
    if not assets:
        st.info("Nenhum ativo cadastrado para análise.")
        return

    df_port = pd.DataFrame(assets, columns=assets[0].keys())
    total_value = df_port["current_value"].sum()
    st.metric(label="Valor Total da Carteira", value=f"R$ {total_value:,.2f}")

    if "asset_class" in df_port.columns:
        st.markdown("**Distribuição por Classe**")
        fig_pie = px.pie(df_port, names="asset_class", values="current_value", title="Por Classe de Ativo")
        st.plotly_chart(fig_pie, use_container_width=True)

    st.markdown("**Top 5 Ativos por Valor**")
    df_top = df_port.sort_values(by="current_value", ascending=False).head(5)
    fig_bar = px.bar(df_top, x="asset_name", y="current_value",
                     title="Top 5 Ativos", labels={"asset_name": "Ativo", "current_value": "Valor Atual (R$)"})
    st.plotly_chart(fig_bar, use_container_width=True)

# ------------------------------------------------------------
# 10) Página: Carteira
# ------------------------------------------------------------
def carteira_page(username: str):
    st.subheader("Sua Carteira")
    # Atualiza antes de exibir
    update_portfolio_prices(username)

    assets = get_portfolio(username)
    if not assets:
        st.info("Nenhum ativo cadastrado.")
        return

    df_port = pd.DataFrame(assets, columns=assets[0].keys())
    total = df_port["current_value"].sum()
    st.metric(label="Valor Total da Carteira", value=f"R$ {total:,.2f}")

    order_by = st.selectbox("Ordenar por:", options=["asset_name", "current_value", "target_percent"])
    df_port = df_port.sort_values(by=order_by, ascending=True)
    st.dataframe(df_port.style.format({
        "current_value": "R$ {:,.2f}",
        "target_percent": "{:.2f}%"
    }), height=300)

    st.write("### Atualize ou Remova Ativos")
    for _, row in df_port.iterrows():
        col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 1.5, 1.5, 1, 1])
        novo_nome = col1.text_input("Ativo", value=row["asset_name"], key=f"nome_{row['id']}_{username}")
        novo_classe = col2.text_input("Classe", value=row["asset_class"] or "", key=f"classe_{row['id']}_{username}")
        novo_percent = col3.number_input("% Alvo", value=row["target_percent"], key=f"percent_{row['id']}_{username}")
        novo_valor = col4.number_input("Valor Atual (R$)", value=row["current_value"], step=0.01, key=f"valor_{row['id']}_{username}")
        atualizar = col5.button("Atualizar", key=f"atualizar_{row['id']}_{username}")
        remover = col6.button("🗑️", key=f"remover_{row['id']}_{username}")
        if atualizar:
            update_asset(row["id"], novo_nome, novo_classe, novo_percent, novo_valor, username)
            st.success(f"Ativo {novo_nome} atualizado.")
            st.experimental_rerun()
        if remover:
            delete_asset(row["id"], username, row["asset_name"])
            st.success(f"Ativo {row['asset_name']} removido.")
            st.experimental_rerun()

    st.markdown("**Distribuição da Carteira por Ativo**")
    fig_pie2 = px.pie(df_port, names="asset_name", values="current_value", title="Alocação Atual")
    st.plotly_chart(fig_pie2, use_container_width=True)

# ------------------------------------------------------------
# 11) Página: Nova Ação
# ------------------------------------------------------------
def nova_acao_page(username: str):
    st.subheader("Adicionar Novo Ativo")
    classes = get_asset_classes(username)
    classes_list = [cl["class_name"] for cl in classes] if classes else []

    with st.form("form_novo_ativo", clear_on_submit=True):
        novo_ticker = st.text_input("Ticker do Ativo (ex.: PETR4.SA ou AAPL)")
        novo_percentual = st.number_input("% Alvo", min_value=0.0, step=0.1)
        if classes_list:
            novo_classe = st.selectbox("Classe do Ativo", options=classes_list)
        else:
            novo_classe = st.text_input("Classe do Ativo")
        cotacao_atual = None
        if novo_ticker:
            if st.form_submit_button("Buscar Cotação"):
                price = fetch_stock_price(novo_ticker.upper())
                if price:
                    st.success(f"Cotação atual: R$ {price:.2f}")
                    cotacao_atual = price
                else:
                    st.error("Ticker inválido ou sem dados.")
        if st.form_submit_button("Adicionar Ativo"):
            ticker_f = novo_ticker.upper().strip()
            valor_atual = cotacao_atual if cotacao_atual else 0.0
            if ticker_f:
                add_asset(username, ticker_f, novo_classe, novo_percentual, valor_atual)
                st.success("Ativo adicionado com sucesso!")
                st.experimental_rerun()
            else:
                st.error("Digite um ticker válido.")

    st.markdown("---")
    st.write("#### Upload de Planilha para Adição em Massa")
    st.info("Planilha: colunas [Ticker, Valor Aplicado, Saldo Bruto, Classe do Ativo]")
    has_header = st.checkbox("O arquivo possui cabeçalho?", value=True)
    uploaded_file = st.file_uploader("Faça upload do arquivo (.csv/.xls/.xlsx)", type=["csv", "xlsx", "xls"])
    if uploaded_file:
        try:
            if uploaded_file.name.endswith(".csv"):
                df = pd.read_csv(uploaded_file, header=0 if has_header else None)
            else:
                df = pd.read_excel(uploaded_file, header=0 if has_header else None)
            st.write("Visualização dos dados:")
            st.dataframe(df.head())

            for _, row in df.iterrows():
                try:
                    ticker = str(row.iloc[0]).strip().upper()
                    saldo_bruto = float(row.iloc[2])
                    asset_class = str(row.iloc[3]).strip()
                except:
                    continue
                add_asset(username, ticker, asset_class, 0.0, saldo_bruto)
            st.success("Ativos adicionados via upload com sucesso!")
            st.experimental_rerun()
        except Exception as e:
            st.error("Erro ao processar o arquivo: " + str(e))

# ------------------------------------------------------------
# 12) Página: Classes de Ativos
# ------------------------------------------------------------
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
                st.experimental_rerun()
            if remover:
                delete_asset_class(row["id"], username, row["class_name"])
                st.success(f"Classe {row['class_name']} removida.")
                st.experimental_rerun()
    else:
        st.info("Nenhuma classe cadastrada.")
    st.write("### Adicionar Nova Classe de Ativo")
    with st.form("nova_classe", clear_on_submit=True):
        nova_classe = st.text_input("Nome da Classe")
        novo_valor_alvo = st.number_input("Valor Alvo (R$)", min_value=0.0, step=0.01)
        if st.form_submit_button("Adicionar Classe"):
            if nova_classe:
                add_asset_class(username, nova_classe, novo_valor_alvo)
                st.success("Classe adicionada com sucesso!")
                st.experimental_rerun()

# ------------------------------------------------------------
# 13) Página: Simulação
# ------------------------------------------------------------
def simulacao_page(username: str):
    st.subheader("Simulação de Aporte e Rebalanceamento")
    update_portfolio_prices(username)
    assets = get_portfolio(username)
    if not assets:
        st.info("Nenhum ativo cadastrado para simulação.")
        return

    df_port = pd.DataFrame(assets, columns=assets[0].keys())
    st.write("### Carteira Atual")
    st.dataframe(df_port.style.format({
        "current_value": "R$ {:,.2f}",
        "target_percent": "{:.2f}%"
    }), height=250)

    aporte = st.number_input("Digite o valor do novo aporte (R$)", min_value=0.0, step=0.01, value=0.0)
    if st.button("Simular Aporte por Ativo"):
        df_reb, tot_atual, tot_new = simulate_rebalance_assets(df_port.copy(), aporte)
        st.write(f"Total Atual: R$ {tot_atual:,.2f} | Total c/ Aporte: R$ {tot_new:,.2f}")
        st.dataframe(df_reb[["asset_name", "current_value", "ideal_value", "aporte_ideal"]].style.format({
            "current_value": "R$ {:,.2f}",
            "ideal_value": "R$ {:,.2f}",
            "aporte_ideal": "R$ {:,.2f}"
        }), height=250)

        fig = px.bar(df_reb, x="asset_name", y="aporte_ideal", title="Aporte Ideal por Ativo",
                     labels={"asset_name": "Ativo", "aporte_ideal": "Aporte Ideal (R$)"})
        st.plotly_chart(fig, use_container_width=True)

    st.write("### Simulação por Classe de Ativo")
    classes = get_asset_classes(username)
    if classes:
        df_class = pd.DataFrame(classes, columns=classes[0].keys())
        df_port_group = df_port.groupby("asset_class")["current_value"].sum().reset_index()
        df_merge = pd.merge(df_class, df_port_group, how="left", left_on="class_name", right_on="asset_class")
        df_merge["current_value"] = df_merge["current_value"].fillna(0)
        df_merge["aporte_ideal"] = df_merge["target_value"] - df_merge["current_value"]
        st.dataframe(df_merge[["class_name", "current_value", "target_value", "aporte_ideal"]].style.format({
            "current_value": "R$ {:,.2f}",
            "target_value": "R$ {:,.2f}",
            "aporte_ideal": "R$ {:,.2f}"
        }), height=250)

        fig2 = px.bar(df_merge, x="class_name", y="aporte_ideal", title="Aporte Ideal por Classe",
                      labels={"class_name": "Classe de Ativo", "aporte_ideal": "Aporte Ideal (R$)"})
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Nenhuma classe cadastrada.")

# ------------------------------------------------------------
# 14) Página: Cotações e Favoritos
# ------------------------------------------------------------
def cotacoes_page(username: str):
    st.subheader("Consulta de Ativos e Favoritos")
    query = st.text_input("Digite o ticker ou nome da empresa/fundo")
    usar_B3 = st.checkbox("Pesquisar na B3 (.SA automaticamente)", value=True)
    if st.button("Buscar Ativo"):
        if query:
            ticker = query.strip().upper()
            if usar_B3 and not ticker.endswith(".SA"):
                ticker += ".SA"
            stock_info = yf.Ticker(ticker).info
            if stock_info and "regularMarketPrice" in stock_info:
                price = stock_info["regularMarketPrice"]
                name = stock_info.get("shortName", ticker)
                st.write(f"**{name} ({ticker})** - Cotação: R$ {price:.2f}")
                st.session_state["searched"] = {"ticker": ticker, "name": name, "price": price}
            else:
                st.error("Ativo não encontrado ou sem dados.")
    if "searched" in st.session_state:
        asset = st.session_state["searched"]
        st.write(f"**{asset['name']} ({asset['ticker']})** - Cotação: R$ {asset['price']:.2f}")
        if st.button("Favoritar", key="btn_fav"):
            add_favorite(username, asset["ticker"], asset["name"])
            st.success(f"{asset['name']} adicionado aos favoritos.")
            st.session_state.pop("searched")
            st.experimental_rerun()

    st_autorefresh(interval=30000, key="refresh_favs")
    st.write("### Seus Favoritos")
    favs = get_favorites(username)
    if favs:
        for fav in favs:
            t = fav["ticker"]
            info = yf.Ticker(t).info
            price = info.get("regularMarketPrice", None) if info else None
            if price:
                short = info.get("shortName", t)
                col1, col2, col3 = st.columns([3, 2, 1])
                col1.write(f"**{short} ({t})**")
                col2.write(f"Cotação: R$ {price:.2f}")
                if col3.button("Remover", key=f"btn_rem_{fav['id']}"):
                    delete_favorite(fav["id"], username, t)
                    st.success(f"{short} removido dos favoritos.")
                    st.experimental_rerun()
            else:
                st.write(f"Não foi possível obter cotação para {t}.")
    else:
        st.info("Nenhum favorito cadastrado.")

# ------------------------------------------------------------
# 15) Página: Relatórios Avançados
# ------------------------------------------------------------
def relatorios_avancados_page(username: str):
    st.subheader("Relatórios Avançados")
    update_portfolio_prices(username)
    assets = get_portfolio(username)
    if not assets:
        st.info("Nenhum ativo para relatório.")
        return

    df_port = pd.DataFrame(assets, columns=assets[0].keys())
    df_port = calcular_alocacao(df_port)

    st.write("### Alocação Atual (%) × Desejada (%)")
    df_display = df_port[["asset_name", "current_value", "target_percent", "aloc_atual_pct"]].rename(columns={
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

    fig_alloc = px.bar(df_port, x="asset_name", y=["aloc_atual_pct", "target_percent"],
                       barmode="group",
                       labels={"asset_name": "Ativo", "value": "Percentual (%)", "variable": "Tipo"},
                       title="Alocação Atual vs Desejada")
    st.plotly_chart(fig_alloc, use_container_width=True)

    st.write("### Sugestão de Rebalance (em R$)")
    df_reb = sugerir_rebalance(df_port.copy())
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

    st.write("*Valores positivos em 'Diferença (R$)' indicam aporte; negativos, saque.*")

    # Exportar CSV
    csv_buf = io.StringIO()
    df_reb_export = df_reb_display.copy()
    df_reb_export.to_csv(csv_buf, sep=";", float_format="%.2f", index=False)
    st.download_button(
        label="⬇️ Baixar CSV de Rebalance",
        data=csv_buf.getvalue().encode("utf-8"),
        file_name="relatorio_rebalance.csv",
        mime="text/csv"
    )

# ------------------------------------------------------------
# 16) Página: Histórico de Logs
# ------------------------------------------------------------
def historico_page(username: str):
    st.subheader("Histórico de Atividades")
    conn = get_connection()
    cur = conn.execute("SELECT * FROM user_logs WHERE username = ? ORDER BY timestamp DESC", (username,))
    logs = cur.fetchall()
    conn.close()
    if not logs:
        st.info("Nenhuma atividade registrada.")
        return
    df_logs = pd.DataFrame(logs, columns=logs[0].keys())
    event_types = df_logs["event_type"].unique().tolist()
    selected = st.selectbox("Filtrar por Evento:", options=["Todos"] + event_types)
    if selected != "Todos":
        df_logs = df_logs[df_logs["event_type"] == selected]
    st.dataframe(df_logs)

# ------------------------------------------------------------
# 17) Página: Notícias
# ------------------------------------------------------------
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
                    t = news.get("title", "Sem Título")
                    l = news.get("link", "")
                    p = news.get("publisher", "")
                    ts = news.get("providerPublishTime", "")
                    st.markdown(f"**{t}**")
                    if l:
                        st.markdown(l)
                    st.markdown(f"*{p} - {ts}*")
                    st.markdown("---")
            else:
                st.info("Nenhuma notícia encontrada.")
        except Exception as e:
            st.error(f"Erro ao buscar notícias: {e}")

# ------------------------------------------------------------
# 18) Interface Principal (login + páginas)
# ------------------------------------------------------------
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
                    st.experimental_rerun()
                else:
                    st.error("Usuário ou senha incorretos.")
        else:
            st.title("📋 Criar Novo Usuário")
            new_username = st.text_input("Novo nome de usuário", key="new_username")
            new_password = st.text_input("Nova senha", type="password", key="new_password")
            if st.button("Criar Usuário"):
                if new_username and new_password:
                    if create_user(new_username, new_password):
                        st.success("Usuário criado com sucesso! Faça login abaixo.")
                    else:
                        st.error("Este nome de usuário já existe.")
                else:
                    st.warning("Preencha ambos os campos.")
    else:
        username = st.session_state.username
        st.title("💰 App de Investimentos - Dashboard")
        st.sidebar.write(f"Usuário: {username}")

        menu_options = [
            "Dashboard", "Carteira", "Nova Ação", "Classes de Ativos",
            "Simulação", "Cotações", "Relatórios Avançados",
            "Histórico", "Notícias"
        ]
        choice = st.sidebar.radio("Escolha uma ação", options=menu_options)

        if choice == "Dashboard":
            dashboard_page(username)
        elif choice == "Carteira":
            carteira_page(username)
        elif choice == "Nova Ação":
            nova_acao_page(username)
        elif choice == "Classes de Ativos":
            classes_de_ativos_page(username)
        elif choice == "Simulação":
            simulacao_page(username)
        elif choice == "Cotações":
            cotacoes_page(username)
        elif choice == "Relatórios Avançados":
            relatorios_avancados_page(username)
        elif choice == "Histórico":
            historico_page(username)
        elif choice == "Notícias":
            noticias_page(username)

        if st.sidebar.button("Sair"):
            st.session_state.logged_in = False
            st.session_state.pop("searched", None)
            st.experimental_rerun()

if __name__ == "__main__":
    main()
