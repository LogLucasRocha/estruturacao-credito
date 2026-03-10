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
    
    contrato_genial = st.toggle("Contrato Genial", value=False, help="Ativo = contrato Genial | Inativo = contrato externo")

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

    # Inicializa session_state para intervalos
    if 'intervalos' not in st.session_state:
        st.session_state.intervalos = {}
    for ano in anos:
        if ano not in st.session_state.intervalos:
            st.session_state.intervalos[ano] = [{"inicio": f"01/{ano}", "fim": f"12/{ano}", "mercado": 150.0, "contrato": 130.0}]

    # Limpa anos que não estão mais no range
    for ano in list(st.session_state.intervalos.keys()):
        if ano not in anos:
            del st.session_state.intervalos[ano]

    dados_operacao_intervalos = {}
    for ano in anos:
        st.write(f"**Ano {ano}**")
        intervalos_ano = st.session_state.intervalos[ano]

        for i, intervalo in enumerate(intervalos_ano):
            cols = st.columns([1.5, 1.5, 1.5, 1.5, 0.5])
            with cols[0]:
                intervalo['inicio'] = st.text_input("Início", value=intervalo['inicio'], key=f"ini_{ano}_{i}", placeholder="mm/aaaa")
            with cols[1]:
                intervalo['fim'] = st.text_input("Fim", value=intervalo['fim'], key=f"fim_{ano}_{i}", placeholder="mm/aaaa")
            with cols[2]:
                intervalo['mercado'] = st.number_input("Mercado (R$/MWh)", value=intervalo['mercado'], key=f"m_{ano}_{i}")
            with cols[3]:
                intervalo['contrato'] = st.number_input("Contrato (R$/MWh)", value=intervalo['contrato'], key=f"c_{ano}_{i}")
            with cols[4]:
                st.write("")
                st.write("")
                if len(intervalos_ano) > 1:
                    if st.button("🗑️", key=f"del_{ano}_{i}"):
                        st.session_state.intervalos[ano].pop(i)
                        st.rerun()

        if st.button(f"➕ Adicionar intervalo em {ano}", key=f"add_{ano}"):
            st.session_state.intervalos[ano].append({"inicio": f"01/{ano}", "fim": f"12/{ano}", "mercado": 150.0, "contrato": 130.0})
            st.rerun()

        dados_operacao_intervalos[ano] = intervalos_ano
        st.divider()

st.divider()

if st.button("🚀 Gerar Análise", use_container_width=True):

    # Valida se algum início de intervalo é anterior à data atual
    erros_intervalo = []
    for ano, intervalos in st.session_state.intervalos.items():
        for i, intervalo in enumerate(intervalos):
            try:
                ini = datetime.strptime(intervalo['inicio'], "%m/%Y")
                if ini < hoje:
                    erros_intervalo.append(f"Ano {ano}, intervalo {i+1}: início {intervalo['inicio']} é anterior ao mês atual ({hoje.strftime('%m/%Y')})")
            except:
                erros_intervalo.append(f"Ano {ano}, intervalo {i+1}: data de início inválida ({intervalo['inicio']})")

    if erros_intervalo:
        for erro in erros_intervalo:
            st.error(f"❌ {erro}")
        st.stop()
    datas = pd.date_range(start=data_inicio, end=data_fim, freq='MS')
    df = pd.DataFrame({'Data_Obj': datas})
    df['mês'] = df['Data_Obj'].dt.strftime('%m/%Y')
    df['Ano'] = df['Data_Obj'].dt.year
    df['indices'] = range(1, len(df) + 1)
    df['Horas'] = df['Data_Obj'].dt.days_in_month * 24

    # Mapeia preço de mercado e contrato por mês com base nos intervalos
    def get_preco_por_mes(data_obj, campo):
        ano = data_obj.year
        for intervalo in st.session_state.intervalos.get(ano, []):
            try:
                ini = datetime.strptime(intervalo['inicio'], "%m/%Y")
                fim = datetime.strptime(intervalo['fim'], "%m/%Y")
                if ini <= data_obj <= fim:
                    return intervalo[campo]
            except:
                pass
        # Fallback: primeiro intervalo do ano
        intervalos_ano = st.session_state.intervalos.get(ano, [])
        return intervalos_ano[0][campo] if intervalos_ano else 0.0

    df['Preço Mercado']  = df['Data_Obj'].apply(lambda d: get_preco_por_mes(d, 'mercado'))
    df['Preço Contrato'] = df['Data_Obj'].apply(lambda d: get_preco_por_mes(d, 'contrato'))

    # Para o resumo_anual de preço input, usamos o primeiro intervalo de cada ano como referência
    dados_operacao = {ano: {"contrato": st.session_state.intervalos[ano][0]['contrato']} for ano in anos}
    
    df['DU_Acumulado'] = df['indices'] * 21
    df['CDI_Anual_Interp'] = df['DU_Acumulado'].apply(lambda x: interpolar_flat_forward(x, curva_anbima))
    df['Taxa_Desconto_Mensal'] = ((1 + df['CDI_Anual_Interp']) * (1 + spread))**(1/12) - 1

    df['Fator_Desconto'] = ((1 + df['CDI_Anual_Interp']) * (1 + spread)) ** (df['DU_Acumulado'] / 252)

    df['Fluxo Mercado']  = volume_mwm * df['Horas'] * df['Preço Mercado']
    df['Fluxo Contrato'] = volume_mwm * df['Horas'] * df['Preço Contrato']

    # ── Visão Cliente ──
    df['Cliente_Paga_VP']      = df['Fluxo Mercado']
    df['Cliente_Recebe_VP']    = df['Fluxo Mercado'] / df['Fator_Desconto']
    df['Cliente_Resultado_VP'] = df['Cliente_Recebe_VP'] - df['Cliente_Paga_VP']

    # ── Visão Genial ──
    df['Genial_Recebe_VP']    = df['Fluxo Mercado']
    df['Genial_Paga_VP']      = df['Fluxo Mercado'] / df['Fator_Desconto']
    df['Genial_Resultado_VP'] = df['Genial_Recebe_VP'] - df['Genial_Paga_VP']

    # ── Peso mensal ──
    df['Peso_MWh'] = df['Horas'] * volume_mwm

    resumo_anual = df.groupby('Ano').apply(lambda g: pd.Series({
        'MWh Total':         g['Peso_MWh'].sum(),
        'Cliente_Recebe_VP': g['Cliente_Recebe_VP'].sum(),
        'Cliente_Paga_VP':   g['Cliente_Paga_VP'].sum(),
        'Genial_Recebe_VP':  g['Genial_Recebe_VP'].sum(),
        'Genial_Paga_VP':    g['Genial_Paga_VP'].sum(),
    })).reset_index()

    resumo_anual['Preço Venda Cliente (R$/MWh)']  = resumo_anual['Cliente_Recebe_VP'] / resumo_anual['MWh Total']
    resumo_anual['Preço Compra Cliente (R$/MWh)'] = resumo_anual['Cliente_Paga_VP']   / resumo_anual['MWh Total']
    resumo_anual['Preço Compra Genial (R$/MWh)']  = resumo_anual['Genial_Paga_VP']    / resumo_anual['MWh Total']
    resumo_anual['Preço Venda Genial (R$/MWh)']   = resumo_anual['Genial_Recebe_VP']  / resumo_anual['MWh Total']
    resumo_anual['Preço Contrato Input (R$/MWh)'] = resumo_anual['Ano'].map(lambda x: dados_operacao[x]['contrato'])
    # ── Fluxo final do cliente ──
    pagamento_unico = df['Cliente_Recebe_VP'].sum()  # Genial paga tudo de uma vez no mês 1

    df['Cliente_Contrato_Antigo'] = df['Fluxo Contrato']   # paga contrato antigo todo mês
    df['Cliente_Novo_Contrato']   = df['Fluxo Mercado']    # paga novo contrato (mercado) todo mês

    # Mês 1: recebe pagamento único - contrato antigo - novo contrato
    # Demais meses: - contrato antigo - novo contrato
    df['Cliente_Fluxo_Final'] = - df['Cliente_Contrato_Antigo'] - df['Cliente_Novo_Contrato']
    df.loc[df.index[0], 'Cliente_Fluxo_Final'] = (
        pagamento_unico
        - df.loc[df.index[0], 'Cliente_Contrato_Antigo']
        - df.loc[df.index[0], 'Cliente_Novo_Contrato']
    )

    # ════════════════════════════════════════════════
    # SEÇÃO 1 — VISÃO CLIENTE
    # ════════════════════════════════════════════════
    st.subheader("👤 Visão Cliente")
    st.caption("A Genial paga ao cliente o valor presente de toda a operação em uma única parcela no primeiro mês.")

    if contrato_genial:
        st.info("""
**🏦 Contrato Genial**

A operação funciona da seguinte forma:
- A Genial **aditiva o contrato original** para preços de mercado
- O cliente **vende um contrato à Genial** ao preço de venda calculado
- O pagamento ao cliente ocorre de forma **integral e antecipada em M+0** (pagamento único à vista)
        """)
    else:
        st.info("""
**📄 Contrato Externo**

A operação funciona da seguinte forma:
- O cliente **cede seu contrato de compra** de energia à Genial
- O cliente **vende um contrato à Genial** ao preço de venda calculado
- O pagamento ao cliente ocorre de forma **integral e antecipada em M+0** (pagamento único à vista)
- A partir daí, o cliente passa a **comprar energia da Genial a preços de mercado**, com liquidação registrada mensalmente
        """)

    c1, c2, c3 = st.columns(3)
    c1.metric("Contrato Original (total)", f"R$ {formatar_moeda_abrev(-df['Cliente_Contrato_Antigo'].sum())}")
    c2.metric("Recebe da Genial (único)",  f"R$ {formatar_moeda_abrev(pagamento_unico)}")
    c3.metric("Novo Contrato (total)",     f"R$ {formatar_moeda_abrev(-df['Cliente_Novo_Contrato'].sum())}")

    st.markdown("**📅 Fluxo Mensal do Cliente**")
    df_cliente = df[['mês', 'Cliente_Contrato_Antigo', 'Cliente_Novo_Contrato', 'Cliente_Fluxo_Final']].copy()
    df_cliente['Cliente_Contrato_Antigo'] = -df_cliente['Cliente_Contrato_Antigo']
    df_cliente['Cliente_Novo_Contrato']   = -df_cliente['Cliente_Novo_Contrato']
    df_cliente = df_cliente.rename(columns={
        'Cliente_Contrato_Antigo': 'Contrato Antigo (R$)',
        'Cliente_Novo_Contrato':   'Novo Contrato (R$)',
        'Cliente_Fluxo_Final':     'Fluxo Final (R$)',
    })

    def colorir_fluxo(val):
        cor = "#2ecc71" if val >= 0 else "#e74c3c"
        return f"color: {cor}; font-weight: bold;"

    st.dataframe(df_cliente.style
        .format({
            'Contrato Antigo (R$)': 'R$ {:,.2f}',
            'Novo Contrato (R$)':   'R$ {:,.2f}',
            'Fluxo Final (R$)':     'R$ {:,.2f}',
        })
        .applymap(colorir_fluxo, subset=['Fluxo Final (R$)']),
    use_container_width=True)

    st.markdown("**📋 Preço de Venda do Contrato — Cliente**")
    st.caption("Preço médio ponderado anual pelo qual o cliente vende o contrato à Genial (R$/MWh)")
    df_preco_venda_cliente = resumo_anual[['Ano', 'Preço Contrato Input (R$/MWh)', 'Preço Venda Cliente (R$/MWh)']].rename(columns={
        'Preço Contrato Input (R$/MWh)': 'Preço Pago no Contrato (R$/MWh)',
        'Preço Venda Cliente (R$/MWh)':  'Preço de Venda à Genial (R$/MWh)',
    })
    st.dataframe(df_preco_venda_cliente.style.format({
        'Preço Pago no Contrato (R$/MWh)':   'R$ {:.2f}',
        'Preço de Venda à Genial (R$/MWh)':  'R$ {:.2f}',
    }), use_container_width=True, hide_index=True)

    st.divider()

    # ════════════════════════════════════════════════
    # SEÇÃO 2 — VISÃO GENIAL INVESTIMENTOS
    # ════════════════════════════════════════════════
    st.subheader("🏦 Visão Genial Investimentos")
    st.caption("Genial **compra** a preço de contrato e **vende** a preço de mercado.")

    lucro_genial = df['Genial_Resultado_VP'].sum()
    g1, g2, g3 = st.columns(3)
    g1.metric("Fluxo Futuro",         f"R$ {formatar_moeda_abrev(df['Genial_Recebe_VP'].sum())}")
    g2.metric("Desembolso na Cabeça", f"R$ {formatar_moeda_abrev(-df['Genial_Paga_VP'].sum())}")
    g3.metric("Resultado Líquido",    f"R$ {formatar_moeda_abrev(lucro_genial)}")

    df_genial = df[['mês', 'Genial_Recebe_VP']].rename(columns={
        'Genial_Recebe_VP': 'Recebe por Mês (R$)',
    })
    st.dataframe(df_genial.style.format({
        'Recebe por Mês (R$)': 'R$ {:,.2f}',
    }), use_container_width=True)

    st.markdown("**📋 Preço de Compra do Contrato — Genial**")
    st.caption("Preço médio ponderado anual pelo qual a Genial compra o contrato do cliente (R$/MWh)")
    df_preco_compra_genial = resumo_anual[['Ano', 'Preço Compra Genial (R$/MWh)']].rename(columns={
        'Preço Compra Genial (R$/MWh)': 'Preço de Compra (R$/MWh)',
    })
    st.dataframe(df_preco_compra_genial.style.format({
        'Preço de Compra (R$/MWh)': 'R$ {:.2f}',
    }), use_container_width=True, hide_index=True)

    st.divider()

    # Export CSV completo
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Exportar para CSV", csv, "calculo_energia.csv", "text/csv", use_container_width=True)

else:
    st.write("---")
    st.caption("Aguardando comando...")