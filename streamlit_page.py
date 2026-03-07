import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import re

st.set_page_config(page_title="Estruturador de Energia", layout="centered")

def interpolar_flat_forward(du_alvo, curva):
    dias = sorted(curva.keys())
    if du_alvo <= dias[0]: return curva[dias[0]] / 100
    if du_alvo >= dias[-1]: return curva[dias[-1]] / 100
    
    du_ant = max([d for d in dias if d <= du_alvo])
    du_post = min([d for d in dias if d > du_alvo])
    i_ant = curva[du_ant] / 100
    i_post = curva[du_post] / 100
    
    termo_ant = (1 + i_ant) ** (du_ant / 252)
    fator_fwd = ((1 + i_post) ** (du_post / 252)) / ((1 + i_ant) ** (du_ant / 252))
    expoente_fwd = (du_alvo - du_ant) / (du_post - du_ant)
    
    taxa_interpolada = (termo_ant * (fator_fwd ** expoente_fwd)) ** (252 / du_alvo) - 1
    return taxa_interpolada

def formatar_moeda_abrev(valor):
    if abs(valor) >= 1_000_000:
        return f"{valor/1_000_000:,.2f}M".replace(",", "X").replace(".", ",").replace("X", ".")
    else:
        return f"{valor/1_000:,.0f}k".replace(",", ".")

def parse_curva_cdi_colada(texto):
    """
    Interpreta o formato grudado: DU + TAXA(com 4 decimais).
    Exemplo: 2114,5479 -> DU: 21, Taxa: 14,5479
    """
    texto_limpo = texto.replace(".", "").replace(" ", "").replace("\n", "").replace("\t", "")
    
    # Busca o padrão: (alguns dígitos) + (digitos , 4 digitos)
    # O lookahead (?=\d|$) garante que pegamos o grupo corretamente
    encontrados = re.findall(r'(\d+)(\d{2},\d{4})', texto_limpo)
    
    if not encontrados:
        return None

    try:
        resultado = {int(du): float(taxa.replace(",", ".")) for du, taxa in encontrados}
        return resultado
    except:
        return None

st.title("⚡ Operações de Crédito")
st.markdown("Cálculo de fluxo descontado com base na curva de juros colada.")
st.markdown("Site da Curva de Juros: https://www.anbima.com.br/pt_br/informar/curvas-de-juros-fechamento.htm")

with st.expander("📈 1. Cole a Curva CDI (ANBIMA)", expanded=True):
    st.caption("Cole o bloco de texto da curva abaixo:")
    curva_raw = st.text_area("Dados da Curva", 
                             value="2114,547950413,02414214,449675613,22196314,31861.00813,468712613,88061.26013,678025213,26332.52014,0008",
                             help="O sistema separa automaticamente os Dias Úteis das Taxas.")
    
    curva_anbima = parse_curva_cdi_colada(curva_raw)
    
    if curva_anbima:
        st.success(f"✅ Curva identificada: {len(curva_anbima)} vértices.")
        # Exibe a curva organizada para conferência
        df_curva = pd.DataFrame(list(curva_anbima.items()), columns=['Dias Úteis', 'Taxa (%)']).sort_values('Dias Úteis')
        st.dataframe(df_curva.T, use_container_width=True)
    else:
        st.error("❌ Erro ao ler a curva. Certifique-se que os números contêm vírgulas para as taxas.")
        st.stop()

with st.expander("📅 2. Período e Volume", expanded=True):
    col_a, col_b = st.columns(2)
    with col_a:
        inicio_default = datetime.now().strftime("%m/%Y")
        inicio_str = st.text_input("Início da Operação (mm/aaaa)", value=inicio_default)
        volume_mwm = st.number_input("Volume (MWm)", value=10.0, step=1.0)
    with col_b:
        fim_str = st.text_input("Fim da Operação (mm/aaaa)", value="12/2027")
        spread = st.number_input("Spread CDI (ex: 0.06)", value=0.06, format="%.4f", help="Taxa adicional ao CDI.")

try:
    data_inicio = datetime.strptime(inicio_str, "%m/%Y")
    data_fim = datetime.strptime(fim_str, "%m/%Y")
    hoje = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    if data_inicio < hoje:
        st.error(f"Início inválido. O mês mínimo é {hoje.strftime('%m/%Y')}.")
        st.stop()
    if data_fim < data_inicio:
        st.error("A data de fim deve ser posterior ao início.")
        st.stop()
except ValueError:
    st.warning("Formato de data inválido.")
    st.stop()

with st.expander("💰 3. Preços por Ano", expanded=True):
    anos = list(range(data_inicio.year, data_fim.year + 1))
    dados_operacao = {}
    for ano in anos:
        st.write(f"**Ano {ano}**")
        c1, c2 = st.columns(2)
        with c1:
            p_mercado = st.number_input(f"Preço Mercado (R$/MWh)", value=150.0, key=f"m_{ano}")
        with c2:
            p_contrato = st.number_input(f"Preço Contrato (R$/MWh)", value=130.0, key=f"c_{ano}")
        dados_operacao[ano] = {"mercado": p_mercado, "contrato": p_contrato}

st.divider()

if st.button("🚀 Gerar Análise", use_container_width=True):
    datas = pd.date_range(start=data_inicio, end=data_fim, freq='MS')
    df = pd.DataFrame({'Data_Obj': datas})
    df['mês'] = df['Data_Obj'].dt.strftime('%m/%Y')
    df['Ano'] = df['Data_Obj'].dt.year
    df['indices'] = range(1, len(df) + 1)
    df['Horas'] = df['Data_Obj'].dt.days_in_month * 24
    
    df['Preço Mercado'] = df['Ano'].map(lambda x: dados_operacao[x]['mercado'])
    df['Preço Contrato'] = df['Ano'].map(lambda x: dados_operacao[x]['contrato'])
    
    df['DU_Acumulado'] = df['indices'] * 21
    df['CDI_Anual_Interp'] = df['DU_Acumulado'].apply(lambda x: interpolar_flat_forward(x, curva_anbima))
    
    df['Taxa_Desconto_Mensal'] = (1 + (df['CDI_Anual_Interp'] + spread))**(1/12) - 1
    
    df['Fluxo Mercado'] = volume_mwm * df['Horas'] * df['Preço Mercado']
    df['Fluxo Contrato Original'] = volume_mwm * df['Horas'] * df['Preço Contrato']
    df['Fluxo Cliente Vende (VP)'] = df['Fluxo Mercado'] / ((1 + df['Taxa_Desconto_Mensal']) ** df['indices'])

    st.subheader("📊 Resultados Consolidados")
    res1, res2, res3 = st.columns(3)
    val_orig = df['Fluxo Contrato Original'].sum()
    val_merc = df['Fluxo Mercado'].sum()
    val_vp = df['Fluxo Cliente Vende (VP)'].sum()

    res1.metric("Contrato Original", f"R$ {formatar_moeda_abrev(val_orig)}")
    res2.metric("Cliente - Compra", f"R$ {formatar_moeda_abrev(val_merc)}")
    res3.metric("Cliente - Vende", f"R$ {formatar_moeda_abrev(val_vp)}")

    st.subheader("📅 Projeção Mensal")
    df_tab = df.rename(columns={'Taxa_Desconto_Mensal': 'Taxa Desconto (Mês)', 'Fluxo Cliente Vende (VP)': 'Cliente - Vende (VP)'})
    df_display = df_tab[['mês', 'Preço Mercado', 'Preço Contrato', 'Taxa Desconto (Mês)', 'Cliente - Vende (VP)']]
    
    st.dataframe(df_display.style.format({
        'Preço Mercado': 'R$ {:.2f}', 'Preço Contrato': 'R$ {:.2f}',
        'Taxa Desconto (Mês)': '{:.4%}', 'Cliente - Vende (VP)': 'R$ {:,.2f}'
    }), use_container_width=True)

    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Exportar para CSV", csv, "calculo_energia.csv", "text/csv", use_container_width=True)
else:
    st.write("---")
    st.caption("Aguardando comando...")