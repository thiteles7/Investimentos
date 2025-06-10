# investimentos.py

import streamlit as st

def rerun():
    """Compatibility wrapper to restart the Streamlit app."""
    if hasattr(st, "rerun"):
        st.rerun()
    else:  # Fall back for older Streamlit versions
        st.experimental_rerun()
import sqlite3
import bcrypt
import yfinance as yf
import plotly.express as px
import pandas as pd
import numpy as np
import io
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from db import initialize_db, get_connection

# Limite máximo de alocação por ativo (em %)
MAX_ASSET_PERCENT = 5.0

# ------------------------------------------------------------
# 1) Inicialização do SQLite
# ------------------------------------------------------------
initialize_db()

# ------------------------------------------------------------
# 2) Funções de log
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
# 3) Funções de usuário (create / verify)
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
    except sqlite3.IntegrityError:
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
# 4) Funções de Carteira (CRUD)
# ------------------------------------------------------------
def get_portfolio(username: str) -> list:
    conn = get_connection()
    cur = conn.execute("SELECT * FROM portfolio WHERE username = ?", (username,))
    results = cur.fetchall()
    conn.close()
    return results

def delete_all_assets_for_user(username: str):
    """
    Remove toda a carteira do usuário antes de inserir nova planilha.
    """
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM portfolio WHERE username = ?", (username,))
    conn.close()
    log_event(username, "Limpeza de carteira", "Carteira anterior removida para upload de nova planilha.")

def add_asset(username: str, asset_name: str, asset_class: str, target_percent: float, quantity: float, current_value: float):
    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO portfolio (username, asset_name, asset_class, target_percent, quantity, current_value) VALUES (?, ?, ?, ?, ?, ?)",
            (username, asset_name.upper(), asset_class, target_percent, quantity, current_value)
        )
    log_event(username, "Adição de ativo", f"Ativo {asset_name.upper()} adicionado.")
    conn.close()

def update_asset(asset_id: int, asset_name: str, asset_class: str, target_percent: float, quantity: float, current_value: float, username: str):
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE portfolio SET asset_name = ?, asset_class = ?, target_percent = ?, quantity = ?, current_value = ? WHERE id = ?",
            (asset_name.upper(), asset_class, target_percent, quantity, current_value, asset_id)
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
# 5) Funções de Classes de Ativos
# ------------------------------------------------------------
def get_asset_classes(username: str) -> list:
    conn = get_connection()
    cur = conn.execute("SELECT * FROM asset_classes WHERE username = ?", (username,))
    results = cur.fetchall()
    conn.close()
    return results

def add_asset_class(username: str, class_name: str, target_percent: float):
    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO asset_classes (username, class_name, target_percent) VALUES (?, ?, ?)",
            (username, class_name, target_percent)
        )
    log_event(username, "Adição de classe de ativo", f"Classe {class_name} adicionada.")
    conn.close()

def update_asset_class(class_id: int, class_name: str, target_percent: float, username: str):
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE asset_classes SET class_name = ?, target_percent = ? WHERE id = ?",
            (class_name, target_percent, class_id)
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
# 6) Funções de Favoritos
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
# 7) Atualização de Preço / Valor de Mercado
# ------------------------------------------------------------
def fetch_stock_price(ticker: str) -> float | None:
    """
    Retorna o último preço de fechamento do ticker (ou None em caso de erro).
    """
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
    Para cada ativo na carteira, busca o preço atual e calcula current_value = price * quantity.
    """
    assets = get_portfolio(username)
    conn = get_connection()
    with conn:
        for row in assets:
            ticker = row["asset_name"].upper()
            price = fetch_stock_price(ticker)
            if price is not None:
                new_value = price * row["quantity"]
                conn.execute(
                    "UPDATE portfolio SET current_value = ? WHERE id = ?",
                    (new_value, row["id"])
                )
    conn.close()

# ------------------------------------------------------------
# 8) Busca de Tickers por Nome
# ------------------------------------------------------------
def search_tickers(query: str) -> list:
    """Retorna uma lista de resultados de ticker para o termo informado."""
    try:
        results = yf.search(query)
        if isinstance(results, dict):
            return results.get("quotes", [])
        return results
    except Exception:
        return []

# ------------------------------------------------------------
# 9) Cálculo de Alocação e Rebalance por Classe
# ------------------------------------------------------------
def calcular_alocacao_por_classe(df_port: pd.DataFrame) -> pd.DataFrame:
    """
    Retorna um DataFrame agrupado por asset_class com:
    - total_current_value (soma de current_value por classe)
    - target_percent (alvo percentual da classe)
    - target_value calculado com base no valor total da carteira
    - diff = target_value - total_current_value
    """
    df_cls_sum = df_port.groupby("asset_class")["current_value"].sum().reset_index()
    df_cls_sum = df_cls_sum.rename(columns={"current_value": "total_current_value"})

    classes = get_asset_classes(df_port["username"].iloc[0])
    if classes:
        df_classes = pd.DataFrame(classes, columns=classes[0].keys()).rename(columns={"class_name": "asset_class"})
    else:
        df_classes = pd.DataFrame(columns=["asset_class", "target_percent"])

    total_port = df_port["current_value"].sum()
    df_merged = pd.merge(df_cls_sum, df_classes, how="left", on="asset_class")
    df_merged["target_percent"] = df_merged["target_percent"].fillna(0.0)
    df_merged["target_value"] = df_merged["target_percent"] / 100.0 * total_port
    df_merged["diff"] = df_merged["target_value"] - df_merged["total_current_value"]
    return df_merged

# ------------------------------------------------------------
# 9) Páginas do App
# ------------------------------------------------------------

def dashboard_page(username: str):
    st.subheader("Dashboard")
    update_portfolio_prices(username)

    assets = get_portfolio(username)
    if not assets:
        st.info("Nenhum ativo cadastrado para análise.")
        return

    df_port = pd.DataFrame(assets, columns=assets[0].keys())
    total_value = df_port["current_value"].sum()
    st.metric(label="Valor Total da Carteira", value=f"R$ {total_value:,.2f}")

    if not df_port["asset_class"].isnull().all():
        st.markdown("**Distribuição por Classe**")
        fig_pie = px.pie(df_port, names="asset_class", values="current_value", title="Por Classe de Ativo")
        st.plotly_chart(fig_pie, use_container_width=True)

    st.markdown("**Top 5 Ativos por Valor**")
    df_top = df_port.sort_values(by="current_value", ascending=False).head(5)
    fig_bar = px.bar(df_top, x="asset_name", y="current_value",
                     title="Top 5 Ativos", labels={"asset_name": "Ativo", "current_value": "Valor Atual (R$)"})
    st.plotly_chart(fig_bar, use_container_width=True)

def carteira_page(username: str):
    st.subheader("Sua Carteira")
    update_portfolio_prices(username)

    assets = get_portfolio(username)
    if not assets:
        st.info("Nenhum ativo cadastrado.")
        return

    df_port = pd.DataFrame(assets, columns=assets[0].keys())
    total = df_port["current_value"].sum()
    df_port["percent_of_total"] = df_port["current_value"] / total * 100
    st.metric(label="Valor Total da Carteira", value=f"R$ {total:,.2f}")

    acima_limite = df_port[df_port["percent_of_total"] > MAX_ASSET_PERCENT]
    if not acima_limite.empty:
        st.warning(
            "Ativos excedendo limite de {:.1f}%: {}".format(
                MAX_ASSET_PERCENT,
                ", ".join(acima_limite["asset_name"].tolist()),
            )
        )

    order_by = st.selectbox("Ordenar por:", options=["asset_name", "current_value", "target_percent", "percent_of_total"])
    df_port = df_port.sort_values(by=order_by, ascending=True)
    st.dataframe(df_port.style.format({
        "current_value": "R$ {:,.2f}",
        "target_percent": "{:.2f}%",
        "percent_of_total": "{:.2f}%",
        "quantity": "{:.0f}"
    }), height=300)

    st.write("### Atualize ou Remova Ativos")
    for _, row in df_port.iterrows():
        col1, col2, col3, col4, col5, col6, col7 = st.columns([2, 2, 1.5, 1.5, 1.5, 1, 1])
        novo_nome = col1.text_input("Ativo", value=row["asset_name"], key=f"nome_{row['id']}_{username}")
        novo_classe = col2.text_input("Classe", value=row["asset_class"] or "", key=f"classe_{row['id']}_{username}")
        novo_percent = col3.number_input("% Alvo", value=row["target_percent"], key=f"percent_{row['id']}_{username}")
        nova_qtd = col4.number_input("Quantidade", value=row["quantity"], step=1.0, key=f"qtd_{row['id']}_{username}")
        novo_valor = col5.number_input("Valor Atual (R$)", value=row["current_value"], step=0.01, key=f"valor_{row['id']}_{username}")
        atualizar = col6.button("Atualizar", key=f"atualizar_{row['id']}_{username}")
        remover = col7.button("🗑️", key=f"remover_{row['id']}_{username}")
        if atualizar:
            update_asset(row["id"], novo_nome, novo_classe, novo_percent, nova_qtd, novo_valor, username)
            st.success(f"Ativo {novo_nome} atualizado.")
            rerun()
        if remover:
            delete_asset(row["id"], username, row["asset_name"])
            st.success(f"Ativo {row['asset_name']} removido.")
            rerun()

    st.markdown("**Distribuição da Carteira por Ativo**")
    fig_pie2 = px.pie(df_port, names="asset_name", values="current_value", title="Alocação Atual")
    st.plotly_chart(fig_pie2, use_container_width=True)

def nova_acao_page(username: str):
    st.subheader("Substituir Carteira por Planilha Excel/CSV")

    st.write("**NOTA:** A planilha deve conter *exatamente* as colunas (case-insensitive):")
    st.markdown("- **Ticker**")
    st.markdown("- **Valor aplicado**")
    st.markdown("- **Saldo bruto**")
    st.markdown("- **Classe do Ativo**")
    st.info("Ao fazer upload, a carteira atual será **substituída** pelos dados desta planilha.")

    uploaded_file = st.file_uploader("Faça upload (.csv, .xls, .xlsx)", type=["csv", "xls", "xlsx"])
    if uploaded_file is not None:
        try:
            # Ler arquivo conforme extensão
            if uploaded_file.name.lower().endswith(".csv"):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)

            # Verificar colunas obrigatórias
            df_cols = [c.strip().lower() for c in df.columns]
            required = {"ticker", "valor aplicado", "saldo bruto", "classe do ativo"}
            if not required.issubset(set(df_cols)):
                st.error("Planilha precisa conter as colunas: Ticker, Valor aplicado, Saldo bruto, Classe do Ativo.")
            else:
                # Limpar carteira anterior
                delete_all_assets_for_user(username)

                # Mapeamento das colunas originais
                col_map = {c.strip().lower(): c for c in df.columns}

                # Iterar linhas e inserir
                for _, row in df.iterrows():
                    ticker = str(row[col_map["ticker"]]).strip().upper()
                    valor_aplicado = float(row[col_map["valor aplicado"]])
                    saldo_bruto = float(row[col_map["saldo bruto"]])
                    classe = str(row[col_map["classe do ativo"]]).strip()

                    # target_percent e quantity podem ficar 0. current_value = saldo_bruto
                    add_asset(username, ticker, classe, 0.0, 0.0, saldo_bruto)

                st.success("Carteira substituída com sucesso pelos dados da planilha!")
                rerun()
        except Exception as e:
            st.error("Erro ao processar a planilha: " + str(e))

def classes_de_ativos_page(username: str):
    st.subheader("Gerencie suas Classes de Ativos")
    classes = get_asset_classes(username)
    if classes:
        df_classes = pd.DataFrame(classes, columns=classes[0].keys())
        st.dataframe(df_classes)
        for _, row in df_classes.iterrows():
            col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
            novo_nome = col1.text_input("Classe", value=row["class_name"], key=f"class_name_{row['id']}_{username}")
            novo_target = col2.number_input("Alocação Alvo (%)", value=row["target_percent"], step=0.01, key=f"target_{row['id']}_{username}")
            atualizar = col3.button("Atualizar", key=f"update_class_{row['id']}_{username}")
            remover = col4.button("Remover", key=f"delete_class_{row['id']}_{username}")
            if atualizar:
                update_asset_class(row["id"], novo_nome, novo_target, username)
                st.success(f"Classe {novo_nome} atualizada.")
                rerun()
            if remover:
                delete_asset_class(row["id"], username, row["class_name"])
                st.success(f"Classe {row['class_name']} removida.")
                rerun()
    else:
        st.info("Nenhuma classe cadastrada.")
    st.write("### Adicionar Nova Classe de Ativo")
    with st.form("nova_classe", clear_on_submit=True):
        nova_classe = st.text_input("Nome da Classe")
        novo_valor_alvo = st.number_input("Alocação Alvo (%)", min_value=0.0, step=0.01)
        if st.form_submit_button("Adicionar Classe"):
            if nova_classe:
                add_asset_class(username, nova_classe, novo_valor_alvo)
                st.success("Classe adicionada com sucesso!")
                rerun()

def simulacao_page(username: str):
    st.subheader("Simulação de Aporte e Rebalanceamento por Classe")
    update_portfolio_prices(username)
    assets = get_portfolio(username)
    if not assets:
        st.info("Nenhum ativo cadastrado para simulação.")
        return

    df_port = pd.DataFrame(assets, columns=assets[0].keys())
    st.write("### Carteira Atual")
    st.dataframe(df_port.style.format({
        "current_value": "R$ {:,.2f}",
        "target_percent": "{:.2f}%",
        "quantity": "{:.0f}"
    }), height=250)

    aporte = st.number_input("Digite o valor do novo aporte (R$)", min_value=0.0, step=0.01, value=0.0)
    if st.button("Simular Aporte por Classe"):
        df_port["username"] = username
        df_cls = calcular_alocacao_por_classe(df_port)
        total_atual = df_cls["total_current_value"].sum()
        total_new = total_atual + aporte

        df_cls["aporte_ideal"] = df_cls["target_value"] - df_cls["total_current_value"]

        st.write(f"**Total Atual (todas classes):** R$ {total_atual:,.2f} | **Total c/ Aporte:** R$ {total_new:,.2f}")
        st.write("#### Sugestão de Aporte/Saque por Classe")
        df_report = df_cls[["asset_class", "total_current_value", "target_percent", "target_value", "aporte_ideal"]].rename(columns={
            "asset_class": "Classe",
            "total_current_value": "Atual (R$)",
            "target_percent": "Alvo (%)",
            "target_value": "Alvo (R$)",
            "aporte_ideal": "Diferença (R$)"
        })
        st.dataframe(df_report.style.format({
            "Atual (R$)": "R$ {:,.2f}",
            "Alvo (%)": "{:.2f}%",
            "Alvo (R$)": "R$ {:,.2f}",
            "Diferença (R$)": "R$ {:,.2f}"
        }), height=300)

        fig = px.bar(df_cls, x="asset_class", y="aporte_ideal",
                     title="Aporte Ideal por Classe",
                     labels={"asset_class": "Classe", "aporte_ideal": "Aporte Ideal (R$)"})
        st.plotly_chart(fig, use_container_width=True)

def cotacoes_page(username: str):
    st.subheader("Consulta de Ativos e Favoritos")
    query = st.text_input("Digite o ticker ou nome da empresa/fundo")
    usar_B3 = st.checkbox("Pesquisar na B3 (.SA automaticamente)", value=True)
    if st.button("Buscar Ativo"):
        if query:
            results = search_tickers(query.strip())
            if results:
                st.session_state["search_results"] = results
            else:
                st.error("Ativo não encontrado.")
                st.session_state.pop("search_results", None)
        else:
            st.warning("Informe um termo para busca.")

    if "search_results" in st.session_state:
        st.write("### Resultados da Busca")
        for item in st.session_state["search_results"]:
            ticker = item.get("symbol")
            name = item.get("shortname", ticker)
            t_use = ticker
            if usar_B3 and not t_use.endswith(".SA"):
                t_use += ".SA"
            info = yf.Ticker(t_use).info
            price = info.get("regularMarketPrice") if info else None
            if price:
                st.write(f"**{name} ({t_use})** - Cotação: R$ {price:.2f}")
                if st.button("Favoritar", key=f"btn_fav_{ticker}"):
                    add_favorite(username, t_use, name)
                    st.success(f"{name} adicionado aos favoritos.")
                    rerun()
            else:
                st.write(f"{name} ({t_use}) - dados não encontrados.")

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
                    rerun()
            else:
                st.write(f"Não foi possível obter cotação para {t}.")
    else:
        st.info("Nenhum favorito cadastrado.")

def relatorios_avancados_page(username: str):
    st.subheader("Relatórios Avançados (Rebalance por Classe)")
    update_portfolio_prices(username)
    assets = get_portfolio(username)
    if not assets:
        st.info("Nenhum ativo para relatório.")
        return

    df_port = pd.DataFrame(assets, columns=assets[0].keys())
    df_port["username"] = username
    df_cls = calcular_alocacao_por_classe(df_port)

    st.write("### Visão Geral por Classe")
    df_display = df_cls.rename(columns={
        "asset_class": "Classe",
        "total_current_value": "Atual (R$)",
        "target_percent": "Alvo (%)",
        "target_value": "Alvo (R$)",
        "diff": "Diferença (R$)"
    })
    st.dataframe(df_display.style.format({
        "Atual (R$)": "R$ {:,.2f}",
        "Alvo (%)": "{:.2f}%",
        "Alvo (R$)": "R$ {:,.2f}",
        "Diferença (R$)": "R$ {:,.2f}"
    }), height=300)

    fig = px.bar(df_cls, x="asset_class", y="diff",
                 title="Diferença (Alvo - Atual) por Classe",
                 labels={"asset_class": "Classe", "diff": "Diferença (R$)"})
    st.plotly_chart(fig, use_container_width=True)

    st.write("#### Exportar Relatório (CSV)")
    csv_buf = io.StringIO()
    df_export = df_display.copy()
    df_export.to_csv(csv_buf, sep=";", float_format="%.2f", index=False)
    st.download_button(
        label="⬇️ Baixar CSV",
        data=csv_buf.getvalue().encode("utf-8"),
        file_name="relatorio_classe.csv",
        mime="text/csv"
    )

    if st.button("⬇️ Baixar PDF"):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 14)
        pdf.cell(0, 10, f"Relatório por Classe - {username}", ln=True, align="C")
        pdf.ln(8)
        pdf.set_font("Arial", size=12)
        for _, row in df_cls.iterrows():
            pdf.cell(0, 8, f"{row['asset_class']} | Atual: R$ {row['total_current_value']:,.2f} | Alvo: {row['target_percent']:.2f}% (R$ {row['target_value']:,.2f}) | Diferença: R$ {row['diff']:,.2f}", ln=True)
        pdf_output = pdf.output(dest="S").encode("latin1")
        st.download_button(label="Baixar PDF", data=pdf_output, file_name="relatorio_classe.pdf", mime="application/pdf")

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
                    pub = news.get("publisher", "")
                    ts = news.get("providerPublishTime", "")
                    st.markdown(f"**{titulo}**")
                    if link:
                        st.markdown(link)
                    st.markdown(f"*{pub} - {ts}*")
                    st.markdown("---")
            else:
                st.info("Nenhuma notícia encontrada para esse ticker.")
        except Exception as e:
            st.error(f"Erro ao buscar notícias: {e}")

# ------------------------------------------------------------
# 10) Interface Principal
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
                    rerun()
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
            "Dashboard", "Carteira", "Nova Ação (Upload)", "Classes de Ativos",
            "Simulação", "Cotações", "Relatórios Avançados",
            "Histórico", "Notícias"
        ]
        choice = st.sidebar.radio("Escolha uma ação", options=menu_options)

        if choice == "Dashboard":
            dashboard_page(username)
        elif choice == "Carteira":
            carteira_page(username)
        elif choice == "Nova Ação (Upload)":
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
            rerun()

if __name__ == "__main__":
    main()
