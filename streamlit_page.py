import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import re

st.set_page_config(page_title="Operação de Crédito", layout="centered")

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
    texto_limpo = texto.replace(".", "").replace(" ", "").replace("\n", "").replace("\t", "")
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

    df['Fluxo Mercado']   = volume_mwm * df['Horas'] * df['Preço Mercado']
    df['Fluxo Contrato']  = volume_mwm * df['Horas'] * df['Preço Contrato']

    # ── Visão Cliente ──
    df['Cliente_Paga_VP']   = df['Fluxo Mercado']
    df['Cliente_Recebe_VP'] = df['Fluxo Mercado'] / ((1 + df['Taxa_Desconto_Mensal']) ** df['indices'])
    df['Cliente_Resultado_VP'] = df['Cliente_Recebe_VP'] - df['Cliente_Paga_VP']

    # ── Visão Genial ──
    df['Genial_Recebe_VP'] = df['Fluxo Mercado']
    df['Genial_Paga_VP']   = df['Fluxo Mercado'] / ((1 + df['Taxa_Desconto_Mensal']) ** df['indices'])
    df['Genial_Resultado_VP'] = df['Genial_Recebe_VP'] - df['Genial_Paga_VP']

    # ── Peso mensal: Horas × Volume (denominador do preço médio ponderado) ──
    df['Peso_MWh'] = df['Horas'] * volume_mwm

    # Preço médio ponderado anual (VP / Σ MWh)
    resumo_anual = df.groupby('Ano').apply(lambda g: pd.Series({
        'MWh Total':               g['Peso_MWh'].sum(),
        'Cliente_Recebe_VP':       g['Cliente_Recebe_VP'].sum(),
        'Cliente_Paga_VP':         g['Cliente_Paga_VP'].sum(),
        'Genial_Recebe_VP':        g['Genial_Recebe_VP'].sum(),
        'Genial_Paga_VP':          g['Genial_Paga_VP'].sum(),
    })).reset_index()

    resumo_anual['Preço Venda Cliente (R$/MWh)']  = resumo_anual['Cliente_Recebe_VP'] / resumo_anual['MWh Total']
    resumo_anual['Preço Compra Cliente (R$/MWh)'] = resumo_anual['Cliente_Paga_VP']   / resumo_anual['MWh Total']
    resumo_anual['Preço Compra Genial (R$/MWh)']  = resumo_anual['Genial_Paga_VP']    / resumo_anual['MWh Total']
    resumo_anual['Preço Venda Genial (R$/MWh)']   = resumo_anual['Genial_Recebe_VP']  / resumo_anual['MWh Total']

    # Comparação: o que o cliente pagaria sem a operação (preço contrato nominal)
    df['Cliente_Pagaria_Sem_Op'] = df['Fluxo Contrato']
    df['Cliente_Ganho']          = df['Cliente_Recebe_VP'] - df['Cliente_Pagaria_Sem_Op']

    st.subheader("👤 Visão Cliente")
    st.caption("Cliente **vende** a preço de contrato e **compra** a preço de mercado.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pagaria sem operação", f"R$ {formatar_moeda_abrev(df['Cliente_Pagaria_Sem_Op'].sum())}")
    c2.metric("Recebe da Genial (VP)", f"R$ {formatar_moeda_abrev(df['Cliente_Recebe_VP'].sum())}")
    c3.metric("Paga (Mercado)",        f"R$ {formatar_moeda_abrev(df['Cliente_Paga_VP'].sum())}")
    ganho = df['Cliente_Ganho'].sum()
    delta_ganho = "✅ Favorável" if ganho >= 0 else "⚠️ Desfavorável"
    c4.metric("Ganho vs Sem Op (R$)", f"R$ {formatar_moeda_abrev(ganho)}", delta=delta_ganho)

    df_cliente = df[['mês', 'Preço Contrato', 'Preço Mercado', 'Taxa_Desconto_Mensal',
                     'Cliente_Pagaria_Sem_Op', 'Cliente_Recebe_VP', 'Cliente_Paga_VP', 'Cliente_Ganho']].rename(columns={
        'Preço Contrato':          'Preço Contrato (R$/MWh)',
        'Preço Mercado':           'Preço Mercado (R$/MWh)',
        'Taxa_Desconto_Mensal':    'Taxa Desconto (Mês)',
        'Cliente_Pagaria_Sem_Op':  'Pagaria Sem Operação (R$)',
        'Cliente_Recebe_VP':       'Recebe da Genial VP (R$)',
        'Cliente_Paga_VP':         'Paga Mercado (R$)',
        'Cliente_Ganho':           'Ganho vs Sem Operação (R$)',
    })
    st.dataframe(df_cliente.style.format({
        'Preço Contrato (R$/MWh)':   'R$ {:.2f}',
        'Preço Mercado (R$/MWh)':    'R$ {:.2f}',
        'Taxa Desconto (Mês)':       '{:.4%}',
        'Pagaria Sem Operação (R$)':       'R$ {:,.2f}',
        'Recebe da Genial VP (R$)':  'R$ {:,.2f}',
        'Paga Mercado (R$)':         'R$ {:,.2f}',
        'Ganho vs Sem Operação (R$)': 'R$ {:,.2f}',
    }), use_container_width=True)

    st.markdown("**📋 Preço Médio Ponderado Anual — Cliente**")
    st.caption("Preço efetivo em VP por MWh = Σ Fluxo VP anual / Σ (Horas × Volume)")
    df_preco_cliente = resumo_anual[['Ano', 'Preço Venda Cliente (R$/MWh)', 'Preço Compra Cliente (R$/MWh)']].rename(columns={
        'Preço Venda Cliente (R$/MWh)':  'Vende (Contrato) R$/MWh',
        'Preço Compra Cliente (R$/MWh)': 'Compra (Mercado) R$/MWh',
    })
    st.dataframe(df_preco_cliente.style.format({
        'Vende (Contrato) R$/MWh': 'R$ {:.2f}',
        'Compra (Mercado) R$/MWh': 'R$ {:.2f}',
    }), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("🏦 Visão Genial Investimentos")
    st.caption("Genial **compra** a preço de contrato e **vende** a preço de mercado.")

    g1, g2, g3 = st.columns(3)
    g1.metric("Recebe (Mercado) VP", f"R$ {formatar_moeda_abrev(df['Genial_Recebe_VP'].sum())}")
    g2.metric("Paga (Contrato) VP",  f"R$ {formatar_moeda_abrev(df['Genial_Paga_VP'].sum())}")
    resultado_genial = df['Genial_Resultado_VP'].sum()
    delta_genial = "✅ Favorável" if resultado_genial >= 0 else "⚠️ Desfavorável"
    g3.metric("Resultado Líquido VP", f"R$ {formatar_moeda_abrev(resultado_genial)}", delta=delta_genial)

    df_genial = df[['mês', 'Preço Mercado', 'Preço Contrato', 'Taxa_Desconto_Mensal',
                    'Genial_Recebe_VP', 'Genial_Paga_VP', 'Genial_Resultado_VP']].rename(columns={
        'Preço Mercado':        'Preço Mercado (R$/MWh)',
        'Preço Contrato':       'Preço Contrato (R$/MWh)',
        'Taxa_Desconto_Mensal': 'Taxa Desconto (Mês)',
        'Genial_Recebe_VP':     'Recebe VP (R$)',
        'Genial_Paga_VP':       'Paga VP (R$)',
        'Genial_Resultado_VP':  'Resultado VP (R$)',
    })
    st.dataframe(df_genial.style.format({
        'Preço Mercado (R$/MWh)':  'R$ {:.2f}',
        'Preço Contrato (R$/MWh)': 'R$ {:.2f}',
        'Taxa Desconto (Mês)':     '{:.4%}',
        'Recebe VP (R$)':          'R$ {:,.2f}',
        'Paga VP (R$)':            'R$ {:,.2f}',
        'Resultado VP (R$)':       'R$ {:,.2f}',
    }), use_container_width=True)

    st.markdown("**📋 Preço Médio Ponderado Anual — Genial Investimentos**")
    st.caption("Preço efetivo em VP por MWh = Σ Fluxo VP anual / Σ (Horas × Volume)")
    df_preco_genial = resumo_anual[['Ano', 'Preço Compra Genial (R$/MWh)', 'Preço Venda Genial (R$/MWh)']].rename(columns={
        'Preço Compra Genial (R$/MWh)': 'Compra (Contrato) R$/MWh',
        'Preço Venda Genial (R$/MWh)':  'Vende (Mercado) R$/MWh',
    })
    st.dataframe(df_preco_genial.style.format({
        'Compra (Contrato) R$/MWh': 'R$ {:.2f}',
        'Vende (Mercado) R$/MWh':   'R$ {:.2f}',
    }), use_container_width=True, hide_index=True)

    st.divider()

    # Export CSV completo
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Exportar para CSV", csv, "calculo_energia.csv", "text/csv", use_container_width=True)

else:
    st.write("---")
    st.caption("Aguardando comando...")