import streamlit as st
import matplotlib.pyplot as plt
import json
import os

# ---------------- CONFIGURAÇÃO ------------------
SAVE_DIR = "dados_usuarios"
os.makedirs(SAVE_DIR, exist_ok=True)
st.set_page_config(page_title="Investimentos", layout="wide")

def load_ativos(username: str):
    """
    Carrega os dados dos ativos do usuário a partir de um arquivo JSON.
    """
    file_path = os.path.join(SAVE_DIR, f"{username}.json")
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return json.load(f)
    return []

def save_ativos(username: str, ativos):
    """
    Salva os dados dos ativos do usuário em um arquivo JSON.
    """
    file_path = os.path.join(SAVE_DIR, f"{username}.json")
    with open(file_path, "w") as f:
        json.dump(ativos, f, indent=4)

def main():
    # ---------------- LOGIN ------------------
    st.title("🔐 Login")
    username = st.text_input("Insira seu nome de usuário para continuar:")

    if not username:
        st.warning("Por favor, digite seu nome de usuário para acessar o app.")
        return

    ativos = load_ativos(username)
    st.success(f"Bem-vindo, {username}!")

    # ---------------- APLICATIVO DE INVESTIMENTOS ------------------
    st.title("💰 App de Investimentos")
    st.subheader("📊 Carteira de Investimentos")

    # Formulário para atualizar ou remover ativos existentes
    with st.form("editar_ativos"):
        st.write("### Atualize ou remova seus ativos")
        ativos_atualizados = []
        if ativos:
            for idx, ativo in enumerate(ativos):
                col_nome, col_percentual, col_valor, col_remover = st.columns([3, 2, 2, 1])
                nome = col_nome.text_input("Ativo", value=ativo.get("nome", ""), key=f"nome_{idx}")
                percentual = col_percentual.number_input("% Alvo", value=float(ativo.get("percentual", 0)), key=f"perc_{idx}")
                atual = col_valor.number_input("Atual", value=float(ativo.get("atual", 0)), step=0.01, key=f"atual_{idx}")
                remover = col_remover.checkbox("🗑️", key=f"remove_{idx}")
                if not remover and nome:
                    ativos_atualizados.append({"nome": nome, "percentual": percentual, "atual": atual})
        else:
            st.info("Nenhum ativo cadastrado até o momento.")

        if st.form_submit_button("Salvar Dados"):
            save_ativos(username, ativos_atualizados)
            st.success("Ativos salvos com sucesso!")
            # Atualiza a lista local para refletir os dados salvos
            ativos = ativos_atualizados

    # Seção para adicionar um novo ativo
    st.markdown("### Adicionar Novo Ativo")
    col1, col2, col3 = st.columns(3)
    novo_ativo = col1.text_input("Novo Ativo", key="novo_ativo")
    novo_percentual = col2.number_input("% Alvo", min_value=0.0, step=0.1, key="novo_percentual")
    novo_valor = col3.number_input("Valor Atual", min_value=0.0, step=0.01, key="novo_valor")

    if st.button("Adicionar Ativo") and novo_ativo:
        ativos.append({"nome": novo_ativo, "percentual": novo_percentual, "atual": novo_valor})
        save_ativos(username, ativos)
        st.success("Ativo adicionado com sucesso! Atualize a página para ver as mudanças.")

    st.markdown("---")
    valor_aporte = st.number_input("💵 Valor do novo aporte (R$)", step=0.01, key="valor_aporte")

    # Cálculo do aporte ideal e exibição dos gráficos
    if st.button("Calcular Aporte Ideal") and ativos:
        total_atual = sum(ativo["atual"] for ativo in ativos)
        total_geral = total_atual + valor_aporte
        st.success(f"Total atual: R$ {total_atual:.2f} | Total com aporte: R$ {total_geral:.2f}")

        # Calcula a distribuição ideal e a sugestão de aporte para cada ativo
        sugestoes = []
        for ativo in ativos:
            ideal_total = (ativo["percentual"] / 100) * total_geral
            aporte_ideal = ideal_total - ativo["atual"]
            sugestoes.append({
                "nome": ativo["nome"],
                "aporte_ideal": aporte_ideal,
                "ideal_total": ideal_total
            })

        st.write("### Sugestão de Aporte")
        for sugestao in sugestoes:
            st.write(f"**{sugestao['nome']}**: Aportar R$ {sugestao['aporte_ideal']:.2f} (Ideal: R$ {sugestao['ideal_total']:.2f})")

        st.write("### Gráficos de Distribuição Ideal")
        # Gráfico de Pizza: distribuição percentual dos valores ideais
        labels = [s["nome"] for s in sugestoes]
        sizes = [s["ideal_total"] for s in sugestoes]

        fig1, ax1 = plt.subplots()
        ax1.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90, wedgeprops={'edgecolor': 'white'})
        ax1.axis('equal')
        st.pyplot(fig1)

        # Gráfico de Barras: aporte ideal para cada ativo
        fig2, ax2 = plt.subplots()
        aporte_values = [s["aporte_ideal"] for s in sugestoes]
        ax2.bar(labels, aporte_values)
        ax2.set_title("Aporte Ideal por Ativo")
        ax2.set_ylabel("Valor do Aporte (R$)")
        ax2.set_xlabel("Ativo")
        st.pyplot(fig2)

if __name__ == "__main__":
    main()
