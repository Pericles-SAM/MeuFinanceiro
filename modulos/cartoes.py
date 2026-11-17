from datetime import date

import streamlit as st

from components.formatacao import formatar_moeda
from database.db import listar_categorias
from database.cartoes import (
    MAX_PARCELAS,
    adicionar_ajuste_fatura,
    adicionar_cartao_credito,
    alterar_status_cartao,
    calcular_datas_fatura,
    calcular_ciclo_compra,
    calcular_situacao_fatura,
    cancelar_compra,
    dividir_em_parcelas,
    editar_cartao_credito,
    editar_compra,
    editar_datas_fatura,
    estornar_ajuste_fatura,
    estornar_pagamento_fatura,
    listar_cartoes_credito,
    listar_compras,
    listar_faturas_mensais,
    listar_historico_compra,
    listar_itens_fatura,
    listar_pagamentos_fatura,
    listar_parcelas_compra,
    obter_compra,
    registrar_compra,
    registrar_pagamento_fatura,
    registrar_ajuste_no_ciclo,
    restaurar_compra,
    resumo_cartoes,
)


MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


def _inicializar_estado():
    valores = {
        "cartao_em_edicao": None,
        "compra_em_edicao": None,
        "compra_para_cancelar": None,
        "pagamento_para_excluir": None,
        "ajuste_para_excluir": None,
        "nonce_form_compra": 0,
        "mensagem_cartoes": None,
    }
    for chave, valor in valores.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor


def _mensagem_pendente():
    mensagem = st.session_state.pop("mensagem_cartoes", None)
    if mensagem:
        st.success(mensagem)


def _moeda_centavos(valor):
    return formatar_moeda(int(valor) / 100)


def _moeda_com_sinal(valor):
    valor = int(valor)
    if valor < 0:
        return f"- {formatar_moeda(abs(valor) / 100)}"
    return formatar_moeda(valor / 100)


def _data_br(data_iso):
    return date.fromisoformat(data_iso).strftime("%d/%m/%Y") if data_iso else "Não informada"


def _rotulo_cartao(cartao):
    return (
        f"{cartao[1]} · fecha dia {cartao[2]} · vence dia {cartao[3]}"
    )


def _ciclo_texto(ano, mes):
    return f"{MESES[int(mes) - 1]}/{ano}"


def _mostrar_resumo(cartoes, faturas):
    resumo = resumo_cartoes()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Cartões ativos", resumo["cartoes_ativos"])
    col2.metric("Saldo de faturas", _moeda_centavos(resumo["saldo_aberto_centavos"]))
    col3.metric("Faturas atrasadas", resumo["faturas_atrasadas"])
    col4.metric(
        "Comprometido em aberto",
        _moeda_centavos(resumo["comprometido_futuro_centavos"]),
    )

    st.divider()
    st.subheader("Próximas faturas")
    futuras = [
        f for f in faturas
        if date.fromisoformat(f[6]) >= date.today() and int(f[7]) - int(f[8]) > 0
    ]
    futuras.sort(key=lambda item: item[6])
    if not futuras:
        st.info("Não há faturas futuras com saldo em aberto.")
    else:
        for fatura in futuras[:5]:
            id_fatura, id_cartao, nome, ano, mes, fechamento, vencimento, total, pago = fatura
            _, saldo = calcular_situacao_fatura(total, pago, vencimento)
            with st.container(border=True):
                col_nome, col_venc, col_valor = st.columns([3, 2, 2])
                col_nome.write(f"**{nome} · {_ciclo_texto(ano, mes)}**")
                col_nome.caption(f"Fecha em {_data_br(fechamento)}")
                col_venc.caption("Vencimento")
                col_venc.write(_data_br(vencimento))
                col_valor.caption("Saldo a pagar")
                col_valor.write(f"**{_moeda_centavos(saldo)}**")


def _formulario_cartao_novo():
    with st.expander("＋ Cadastrar cartão", expanded=False):
        with st.form("form_novo_cartao_credito", clear_on_submit=True):
            nome = st.text_input("Nome do cartão", placeholder="Ex.: Cartão principal", key="novo_cartao_nome")
            col1, col2 = st.columns(2)
            with col1:
                fechamento = st.number_input(
                    "Dia de fechamento", min_value=1, max_value=31, value=10, step=1,
                    help="Dia em que a fatura normalmente fecha.", key="novo_cartao_fechamento"
                )
            with col2:
                vencimento = st.number_input(
                    "Dia de vencimento", min_value=1, max_value=31, value=17, step=1,
                    help="Dia em que a fatura normalmente vence.", key="novo_cartao_vencimento"
                )
            regra = st.radio(
                "Compra realizada exatamente no dia do fechamento entra em qual fatura?",
                options=["proxima", "atual"],
                format_func=lambda x: "Próxima fatura" if x == "proxima" else "Fatura que está fechando",
                horizontal=True,
                help="Os bancos podem processar compras no dia do fechamento de formas diferentes. Você pode ajustar esta regra por cartão.",
                key="novo_cartao_regra_fechamento",
            )
            salvar = st.form_submit_button(
                "Cadastrar cartão", use_container_width=True, type="primary"
            )
        if salvar:
            try:
                adicionar_cartao_credito(nome, int(fechamento), int(vencimento), regra)
                st.session_state["mensagem_cartoes"] = "Cartão cadastrado com sucesso!"
                st.rerun()
            except ValueError as erro:
                st.error(str(erro))


def _formulario_edicao_cartao(cartao):
    id_cartao, nome_atual, fechamento_atual, vencimento_atual, regra_atual, ativo = cartao
    with st.form(f"form_editar_cartao_{id_cartao}"):
        st.markdown(f"**Editando {nome_atual}**")
        nome = st.text_input("Nome", value=nome_atual, key=f"nome_cartao_edicao_{id_cartao}")
        col1, col2 = st.columns(2)
        with col1:
            fechamento = st.number_input(
                "Dia de fechamento", min_value=1, max_value=31,
                value=int(fechamento_atual), step=1, key=f"fechamento_cartao_edicao_{id_cartao}",
            )
        with col2:
            vencimento = st.number_input(
                "Dia de vencimento", min_value=1, max_value=31,
                value=int(vencimento_atual), step=1, key=f"vencimento_cartao_edicao_{id_cartao}",
            )
        regra = st.radio(
            "Compra no dia do fechamento",
            options=["proxima", "atual"],
            index=0 if regra_atual == "proxima" else 1,
            format_func=lambda x: "Próxima fatura" if x == "proxima" else "Fatura que está fechando",
            horizontal=True,
            key=f"regra_cartao_edicao_{id_cartao}",
        )
        salvar = st.form_submit_button("Salvar alterações", type="primary", use_container_width=True)
        cancelar = st.form_submit_button("Cancelar", use_container_width=True)
    if salvar:
        try:
            editar_cartao_credito(id_cartao, nome, int(fechamento), int(vencimento), regra)
            st.session_state["cartao_em_edicao"] = None
            st.session_state["mensagem_cartoes"] = (
                "Cartão atualizado. As compras já registradas mantiveram seus ciclos e vencimentos originais."
            )
            st.rerun()
        except ValueError as erro:
            st.error(str(erro))
    if cancelar:
        st.session_state["cartao_em_edicao"] = None
        st.rerun()


def _aba_cartoes(cartoes):
    st.subheader("Meus cartões")
    _formulario_cartao_novo()
    if not cartoes:
        st.info("Nenhum cartão cadastrado ainda.")
        return

    for cartao in cartoes:
        id_cartao, nome, fechamento, vencimento, regra, ativo = cartao
        with st.container(border=True):
            col_info, col_regra, col_acao = st.columns([3, 2, 2], vertical_alignment="center")
            with col_info:
                st.markdown(f"**💳 {nome}**")
                st.caption(f"Fechamento dia {fechamento} · Vencimento dia {vencimento}")
            with col_regra:
                st.caption("Compra no dia do fechamento")
                st.write("Próxima fatura" if regra == "proxima" else "Fatura atual")
            with col_acao:
                if ativo:
                    if st.button("Editar", key=f"editar_cartao_{id_cartao}", use_container_width=True):
                        st.session_state["cartao_em_edicao"] = id_cartao
                        st.rerun()
                    if st.button("Arquivar", key=f"arquivar_cartao_{id_cartao}", use_container_width=True):
                        alterar_status_cartao(id_cartao, False)
                        st.session_state["mensagem_cartoes"] = "Cartão arquivado. O histórico foi preservado."
                        st.rerun()
                else:
                    st.caption("Cartão arquivado")
                    if st.button("Reativar", key=f"reativar_cartao_{id_cartao}", use_container_width=True):
                        alterar_status_cartao(id_cartao, True)
                        st.session_state["mensagem_cartoes"] = "Cartão reativado."
                        st.rerun()
            if st.session_state.get("cartao_em_edicao") == id_cartao:
                _formulario_edicao_cartao(cartao)


def _preview_parcelamento(cartao, data_compra, valor, quantidade):
    valores = dividir_em_parcelas(valor, quantidade)
    ano, mes = calcular_ciclo_compra(data_compra, cartao[2], cartao[4])
    previa = []
    for indice, valor_centavos in enumerate(valores, start=1):
        indice_mes = (ano * 12 + (mes - 1)) + indice - 1
        ano_fatura = indice_mes // 12
        mes_fatura = indice_mes % 12 + 1
        fechamento, vencimento = calcular_datas_fatura(
            ano_fatura, mes_fatura, cartao[2], cartao[3]
        )
        previa.append((indice, valor_centavos, ano_fatura, mes_fatura, fechamento, vencimento))
    return previa


def _formulario_compra(cartoes_ativos):
    if not cartoes_ativos:
        st.info("Cadastre ou reative um cartão antes de registrar compras.")
        return

    nonce = st.session_state["nonce_form_compra"]
    prefixo = f"nova_compra_{nonce}"
    opcoes = {c[0]: _rotulo_cartao(c) for c in cartoes_ativos}
    st.subheader("Registrar compra")
    st.caption("A compra será distribuída automaticamente nas faturas conforme o fechamento do cartão.")

    col1, col2 = st.columns([2, 1])
    with col1:
        cartao_id = st.selectbox("Cartão utilizado", list(opcoes), format_func=lambda x: opcoes[x], key=f"{prefixo}_cartao")
        descricao = st.text_input("Descrição da compra", placeholder="Ex.: Notebook, supermercado, assinatura", key=f"{prefixo}_descricao")
        categorias = ["Sem categoria"] + listar_categorias()
        categoria = st.selectbox("Categoria (opcional)", categorias, key=f"{prefixo}_categoria")
        observacao = st.text_area("Observações (opcional)", key=f"{prefixo}_obs", height=70)
    with col2:
        data_compra = st.date_input("Data da compra", value=date.today(), format="DD/MM/YYYY", key=f"{prefixo}_data")
        valor_total = st.number_input("Valor total (R$)", min_value=0.01, value=100.00, step=10.00, format="%.2f", key=f"{prefixo}_valor")
        quantidade = st.selectbox("Quantidade de parcelas", options=list(range(1, MAX_PARCELAS + 1)), index=0, format_func=lambda x: "À vista (1x)" if x == 1 else f"{x} vezes", key=f"{prefixo}_parcelas")

    cartao_selecionado = next(c for c in cartoes_ativos if c[0] == cartao_id)
    try:
        previa = _preview_parcelamento(cartao_selecionado, data_compra, valor_total, quantidade)
        primeira = previa[0]
        st.markdown("#### Prévia do lançamento")
        st.write(
            f"**{quantidade}x** · Primeira parcela: **{_moeda_centavos(previa[0][1])}** "
            f"· Total: **{_moeda_centavos(sum(x[1] for x in previa))}**"
        )
        if len({x[1] for x in previa}) > 1:
            st.caption("A diferença de centavos foi distribuída nas primeiras parcelas para fechar exatamente o valor total.")
        with st.container(border=True):
            for item in previa[:6]:
                numero, cents, ano, mes, fechamento, vencimento = item
                col_parcela, col_ciclo, col_valor = st.columns([1, 2, 1])
                col_parcela.write(f"{numero}/{quantidade}")
                col_ciclo.caption(f"{_ciclo_texto(ano, mes)} · vence {_data_br(vencimento)}")
                col_valor.write(_moeda_centavos(cents))
            if len(previa) > 6:
                st.caption(f"... e mais {len(previa) - 6} parcela(s) nos meses seguintes.")
        regra_texto = "A compra no dia do fechamento será lançada na próxima fatura." if cartao_selecionado[4] == "proxima" else "A compra no dia do fechamento será lançada na fatura atual."
        st.caption(f"Regra deste cartão: {regra_texto} Compras após o fechamento passam para o ciclo seguinte.")
    except ValueError as erro:
        st.warning(str(erro))
        previa = None

    if st.button("Registrar compra e gerar parcelas", key=f"{prefixo}_salvar", type="primary", use_container_width=True, disabled=not previa):
        try:
            id_compra = registrar_compra(
                cartao_id, descricao, data_compra, valor_total, quantidade,
                None if categoria == "Sem categoria" else categoria, observacao,
            )
            st.session_state["nonce_form_compra"] += 1
            st.session_state["mensagem_cartoes"] = f"Compra registrada! As {quantidade} parcela(s) foram distribuídas nas faturas."
            st.rerun()
        except ValueError as erro:
            st.error(str(erro))


def _formulario_edicao_compra(id_compra, cartoes):
    compra = obter_compra(id_compra)
    if not compra:
        st.warning("Compra não encontrada.")
        st.session_state["compra_em_edicao"] = None
        return
    (id_compra, cartao_atual, descricao_atual, categoria_atual, data_atual,
     total_centavos, parcelas_atual, observacao_atual, ativa) = compra
    opcoes_cartao = {c[0]: _rotulo_cartao(c) for c in cartoes if c[5] == 1}
    if cartao_atual not in opcoes_cartao:
        st.warning("O cartão desta compra está arquivado. Reative-o para alterar a compra.")
        return
    categorias = ["Sem categoria"] + listar_categorias()
    with st.form(f"form_editar_compra_{id_compra}"):
        st.markdown(f"**Editando: {descricao_atual}**")
        cartao_id = st.selectbox("Cartão", list(opcoes_cartao), index=list(opcoes_cartao).index(cartao_atual), format_func=lambda x: opcoes_cartao[x])
        descricao = st.text_input("Descrição", value=descricao_atual)
        categoria = st.selectbox("Categoria", categorias, index=categorias.index(categoria_atual or "Sem categoria"))
        col1, col2, col3 = st.columns(3)
        with col1:
            data_compra = st.date_input("Data da compra", value=date.fromisoformat(data_atual), format="DD/MM/YYYY")
        with col2:
            valor = st.number_input("Valor total (R$)", min_value=0.01, value=total_centavos / 100, step=10.00, format="%.2f")
        with col3:
            quantidade = st.selectbox("Parcelas", list(range(1, MAX_PARCELAS + 1)), index=int(parcelas_atual) - 1)
        observacao = st.text_area("Observações", value=observacao_atual or "")
        salvar = st.form_submit_button("Salvar alterações", type="primary", use_container_width=True)
        cancelar = st.form_submit_button("Cancelar", use_container_width=True)
    if salvar:
        try:
            editar_compra(
                id_compra, cartao_id, descricao, data_compra, valor, quantidade,
                None if categoria == "Sem categoria" else categoria, observacao,
            )
            st.session_state["compra_em_edicao"] = None
            st.session_state["mensagem_cartoes"] = "Compra atualizada e parcelas recalculadas."
            st.rerun()
        except ValueError as erro:
            st.error(str(erro))
    if cancelar:
        st.session_state["compra_em_edicao"] = None
        st.rerun()


def _aba_compras(cartoes):
    cartoes_ativos = [c for c in cartoes if c[5] == 1]
    _formulario_compra(cartoes_ativos)
    st.divider()
    st.subheader("Compras registradas")
    compras = listar_compras(incluir_canceladas=True)
    if not compras:
        st.info("Nenhuma compra registrada ainda.")
        return

    filtro_opcoes = {None: "Todos os cartões"}
    filtro_opcoes.update({c[0]: c[1] for c in cartoes})
    filtro = st.selectbox("Filtrar por cartão", list(filtro_opcoes), format_func=lambda x: filtro_opcoes[x], key="filtro_compras_cartao")
    if filtro is not None:
        compras = [c for c in compras if c[1] == filtro]

    for compra in compras:
        (id_compra, id_cartao, nome_cartao, descricao, categoria, data_compra,
         total_centavos, quantidade, observacao, ativa, total_parcelado, versao_atual) = compra
        with st.container(border=True):
            col_desc, col_valor, col_acoes = st.columns([3, 1.5, 2.5], vertical_alignment="center")
            with col_desc:
                st.write(f"**{descricao}**")
                st.caption(f"{nome_cartao} · {_data_br(data_compra)} · {categoria or 'Sem categoria'}")
                if not ativa:
                    st.caption("Compra cancelada — preservada no histórico")
            with col_valor:
                st.caption("Valor total")
                st.write(f"**{_moeda_centavos(total_centavos)}**")
                st.caption("À vista" if quantidade == 1 else f"{quantidade} parcelas")
            with col_acoes:
                if ativa:
                    if st.button("Editar", key=f"editar_compra_{id_compra}", use_container_width=True):
                        st.session_state["compra_em_edicao"] = id_compra
                        st.rerun()
                    if st.button("Cancelar compra", key=f"cancelar_compra_{id_compra}", use_container_width=True):
                        st.session_state["compra_para_cancelar"] = id_compra
                        st.rerun()
                else:
                    cartao_ativo = next((c[5] for c in cartoes if c[0] == id_cartao), 0)
                    if st.button(
                        "Restaurar compra", key=f"restaurar_compra_{id_compra}",
                        use_container_width=True, disabled=cartao_ativo != 1,
                    ):
                        try:
                            restaurar_compra(id_compra)
                            st.session_state["mensagem_cartoes"] = "Compra restaurada e parcelas reativadas."
                            st.rerun()
                        except ValueError as erro:
                            st.error(str(erro))
                    if cartao_ativo != 1:
                        st.caption("Reative o cartão para restaurar esta compra.")
            parcelas = listar_parcelas_compra(id_compra)
            parcelas_versao_atual = [p for p in parcelas if p[11] == versao_atual]
            parcelas_anteriores = [p for p in parcelas if p[11] != versao_atual]
            with st.expander(f"Ver distribuição das parcelas · compra #{id_compra}", expanded=False):
                if parcelas_versao_atual:
                    st.caption("Última distribuição" if ativa else "Última distribuição (compra cancelada)")
                    for p in parcelas_versao_atual:
                        _, numero, total, cents, ano, mes, fechamento, vencimento, id_fatura, ativa_parcela, motivo, versao = p
                        st.write(
                            f"**{numero}/{total}** · {_ciclo_texto(ano, mes)} · "
                            f"vence {_data_br(vencimento)} · {_moeda_centavos(cents)}"
                            + (" · Ativa" if ativa_parcela else " · Cancelada")
                        )
                if parcelas_anteriores:
                    st.caption("Distribuições anteriores (após edição)")
                    for p in parcelas_anteriores:
                        _, numero, total, cents, ano, mes, fechamento, vencimento, id_fatura, ativa_parcela, motivo, versao = p
                        st.caption(
                            f"Versão {versao} · {numero}/{total} · {_ciclo_texto(ano, mes)} · "
                            f"{_moeda_centavos(cents)} · {motivo or 'Substituída'}"
                        )
                if not parcelas:
                    st.caption("Não há parcelas registradas para esta compra.")
                historico = listar_historico_compra(id_compra)
                if historico:
                    st.divider()
                    st.caption("Histórico de alterações da compra")
                    for versao in historico:
                        _, id_cartao_hist, desc_hist, cat_hist, data_hist, total_hist, qtd_hist, obs_hist, alterado, motivo_hist = versao
                        st.caption(
                            f"{_data_br(data_hist)} · {desc_hist} · {_moeda_centavos(total_hist)} · "
                            f"{qtd_hist} parcela(s) · revisada em {alterado}"
                        )
            if st.session_state.get("compra_em_edicao") == id_compra:
                _formulario_edicao_compra(id_compra, cartoes)
            if st.session_state.get("compra_para_cancelar") == id_compra:
                st.warning("A compra será retirada dos totais das faturas, mas permanecerá no histórico. Continuar?")
                confirmar, voltar = st.columns(2)
                with confirmar:
                    if st.button("Confirmar cancelamento", key=f"confirmar_cancelar_compra_{id_compra}", type="primary", use_container_width=True):
                        try:
                            cancelar_compra(id_compra)
                            st.session_state["compra_para_cancelar"] = None
                            st.session_state["mensagem_cartoes"] = "Compra cancelada. O registro foi preservado no histórico."
                            st.rerun()
                        except ValueError as erro:
                            st.error(str(erro))
                with voltar:
                    if st.button("Voltar", key=f"voltar_cancelar_compra_{id_compra}", use_container_width=True):
                        st.session_state["compra_para_cancelar"] = None
                        st.rerun()


def _mostrar_detalhes_fatura(fatura, expanded=False):
    id_fatura, id_cartao, nome, ano, mes, fechamento, vencimento, total, pago = fatura
    situacao, saldo = calcular_situacao_fatura(total, pago, vencimento)
    itens = listar_itens_fatura(id_fatura)
    with st.expander(
        f"Detalhes, itens e pagamentos · {nome} · {_ciclo_texto(ano, mes)}",
        expanded=expanded,
    ):
        st.caption(f"Fechamento: {_data_br(fechamento)} · Vencimento: {_data_br(vencimento)}")
        mostrar_ajuste_datas = st.checkbox(
            "Ajustar datas desta fatura", key=f"mostrar_ajuste_datas_{id_fatura}"
        )
        if mostrar_ajuste_datas:
            with st.form(f"form_datas_fatura_{id_fatura}"):
                col_fech, col_venc = st.columns(2)
                with col_fech:
                    novo_fechamento = st.date_input(
                        "Data de fechamento", value=date.fromisoformat(fechamento),
                        format="DD/MM/YYYY", key=f"novo_fechamento_{id_fatura}"
                    )
                with col_venc:
                    novo_vencimento = st.date_input(
                        "Data de vencimento", value=date.fromisoformat(vencimento),
                        format="DD/MM/YYYY", key=f"novo_vencimento_{id_fatura}"
                    )
                salvar_datas = st.form_submit_button("Salvar datas desta fatura", use_container_width=True)
            if salvar_datas:
                try:
                    editar_datas_fatura(id_fatura, novo_fechamento, novo_vencimento)
                    st.session_state["mensagem_cartoes"] = "Datas desta fatura atualizadas. As regras gerais do cartão não foram alteradas."
                    st.rerun()
                except ValueError as erro:
                    st.error(str(erro))
        st.markdown("**Itens da fatura**")
        if not itens:
            st.info("Esta fatura ainda não possui itens.")
        for item in itens:
            tipo, descricao, categoria, valor, numero, total_parcelas, id_compra, id_item, ativo = item
            col_desc, col_valor = st.columns([3, 1])
            with col_desc:
                if tipo == "Parcela":
                    st.write(f"{descricao} · parcela {numero}/{total_parcelas}")
                    if categoria:
                        st.caption(categoria)
                else:
                    st.write(f"{descricao} · {tipo}")
                if not ativo:
                    st.caption("Lançamento estornado/cancelado — mantido no histórico")
            with col_valor:
                st.write(_moeda_com_sinal(valor))
            if tipo in {"Encargo", "Crédito"} and ativo:
                if st.button("Estornar ajuste", key=f"estornar_ajuste_{id_item}"):
                    st.session_state["ajuste_para_excluir"] = id_item
                    st.rerun()
                if st.session_state.get("ajuste_para_excluir") == id_item:
                    st.warning("Confirma estornar este ajuste? O registro ficará preservado no histórico.")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Confirmar estorno", key=f"confirma_ajuste_{id_item}", type="primary"):
                            estornar_ajuste_fatura(id_item, "Estorno solicitado pelo usuário")
                            st.session_state["ajuste_para_excluir"] = None
                            st.rerun()
                    with c2:
                        if st.button("Cancelar", key=f"cancela_ajuste_{id_item}"):
                            st.session_state["ajuste_para_excluir"] = None
                            st.rerun()

        st.divider()
        col_total, col_pago, col_saldo = st.columns(3)
        col_total.metric("Total da fatura", _moeda_com_sinal(total))
        col_pago.metric("Total pago", _moeda_centavos(pago))
        rotulo_saldo = "Crédito disponível" if situacao == "Crédito disponível" else "Saldo restante"
        col_saldo.metric(rotulo_saldo, _moeda_centavos(saldo))

        st.markdown("**Registrar pagamento**")
        saldo_para_pagamento = max(int(total) - int(pago), 0)
        if saldo_para_pagamento > 0:
            with st.form(f"form_pagamento_fatura_{id_fatura}_{saldo_para_pagamento}", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    valor_pagamento = st.number_input("Valor pago (R$)", min_value=0.01, max_value=saldo_para_pagamento / 100, value=saldo_para_pagamento / 100, step=10.00, format="%.2f", key=f"valor_pagamento_{id_fatura}_{saldo_para_pagamento}")
                with col2:
                    data_pagamento = st.date_input("Data do pagamento", value=date.today(), format="DD/MM/YYYY", key=f"data_pagamento_{id_fatura}")
                observacao = st.text_input("Observação (opcional)", key=f"obs_pagamento_{id_fatura}")
                salvar_pagamento = st.form_submit_button("Registrar pagamento", type="primary", use_container_width=True)
            if salvar_pagamento:
                try:
                    registrar_pagamento_fatura(id_fatura, valor_pagamento, data_pagamento, observacao)
                    st.session_state["mensagem_cartoes"] = "Pagamento registrado. O saldo da fatura foi atualizado."
                    st.rerun()
                except ValueError as erro:
                    st.error(str(erro))
        else:
            st.success("Esta fatura não possui saldo a pagar.")

        st.markdown("**Histórico de pagamentos**")
        pagamentos = listar_pagamentos_fatura(id_fatura)
        if pagamentos:
            for pagamento in pagamentos:
                id_pagamento, valor_pago, data_pago, obs, estornado, motivo_estorno = pagamento
                c1, c2, c3 = st.columns([2, 2, 1])
                c1.write(_moeda_centavos(valor_pago))
                c2.caption(f"{_data_br(data_pago)} · {obs or 'Sem observação'}")
                with c3:
                    if estornado:
                        st.caption("Estornado")
                    elif st.button("Estornar", key=f"estornar_pagamento_{id_pagamento}"):
                        st.session_state["pagamento_para_excluir"] = id_pagamento
                        st.rerun()
                if st.session_state.get("pagamento_para_excluir") == id_pagamento and not estornado:
                    st.warning("Confirma estornar este pagamento? O registro ficará preservado e o saldo será recalculado.")
                    x1, x2 = st.columns(2)
                    with x1:
                        if st.button("Confirmar estorno", key=f"confirmar_pagamento_{id_pagamento}", type="primary"):
                            estornar_pagamento_fatura(id_pagamento, "Estorno solicitado pelo usuário")
                            st.session_state["pagamento_para_excluir"] = None
                            st.rerun()
                    with x2:
                        if st.button("Cancelar", key=f"cancelar_pagamento_{id_pagamento}"):
                            st.session_state["pagamento_para_excluir"] = None
                            st.rerun()
                if estornado and motivo_estorno:
                    st.caption(f"Motivo do estorno: {motivo_estorno}")

        st.divider()
        st.markdown("**Ajustes, encargos e créditos**")
        with st.form(f"form_ajuste_fatura_{id_fatura}", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                tipo_ajuste = st.selectbox("Tipo", ["Encargo", "Crédito"], key=f"tipo_ajuste_{id_fatura}")
            with col2:
                valor_ajuste = st.number_input("Valor (R$)", min_value=0.01, value=0.01, step=1.00, format="%.2f", key=f"valor_ajuste_{id_fatura}")
            descricao_ajuste = st.text_input("Descrição", placeholder="Ex.: Juros, anuidade, estorno, cashback", key=f"desc_ajuste_{id_fatura}")
            salvar_ajuste = st.form_submit_button("Adicionar ajuste", use_container_width=True)
        if salvar_ajuste:
            try:
                adicionar_ajuste_fatura(id_fatura, tipo_ajuste, descricao_ajuste, valor_ajuste)
                st.session_state["mensagem_cartoes"] = "Ajuste adicionado à fatura."
                st.rerun()
            except ValueError as erro:
                st.error(str(erro))


def _aba_faturas(cartoes):
    st.subheader("Faturas mensais")
    faturas = listar_faturas_mensais()
    if not faturas:
        st.info("As faturas serão criadas automaticamente ao registrar compras. Você também pode lançar um encargo ou crédito em um ciclo futuro.")

    destaque_id = st.session_state.get("fatura_dashboard_selecionada")
    fatura_destacada = next((f for f in faturas if f[0] == destaque_id), None)

    if fatura_destacada:
        st.info(
            f"Você abriu esta fatura pelo Dashboard: **{fatura_destacada[2]} · "
            f"{_ciclo_texto(fatura_destacada[3], fatura_destacada[4])}**. "
            "Os detalhes e os itens estão expandidos abaixo."
        )
        if st.button("Limpar fatura destacada", key="limpar_fatura_dashboard"):
            st.session_state["fatura_dashboard_selecionada"] = None
            st.rerun()
    elif destaque_id is not None:
        st.session_state["fatura_dashboard_selecionada"] = None
        destaque_id = None

    opcoes_cartoes = {None: "Todos os cartões"}
    opcoes_cartoes.update({c[0]: c[1] for c in cartoes})
    cartao_filtro = st.selectbox(
        "Cartão", list(opcoes_cartoes),
        format_func=lambda x: opcoes_cartoes[x],
        key="filtro_faturas_cartao",
    )
    anos = sorted({int(f[3]) for f in faturas}, reverse=True)
    opcoes_anos = [None] + anos
    ano_filtro = st.selectbox(
        "Ano", opcoes_anos,
        format_func=lambda x: "Todos os anos" if x is None else str(x),
        key="filtro_faturas_ano",
    )
    opcoes_meses = [None] + list(range(1, 13))
    mes_filtro = st.selectbox(
        "Mês", opcoes_meses,
        format_func=lambda x: "Todos os meses" if x is None else MESES[x - 1],
        key="filtro_faturas_mes",
    )
    filtradas = [
        f for f in faturas
        if (cartao_filtro is None or f[1] == cartao_filtro)
        and (ano_filtro is None or f[3] == ano_filtro)
        and (mes_filtro is None or f[4] == mes_filtro)
    ]

    cartoes_para_ajuste = list(cartoes)
    if cartoes_para_ajuste:
        with st.expander("＋ Lançar encargo ou crédito em um mês", expanded=False):
            opcoes_cartao_ajuste = {c[0]: _rotulo_cartao(c) for c in cartoes_para_ajuste}
            hoje = date.today()
            anos_ajuste = list(range(hoje.year - 2, hoje.year + 6))
            with st.form("form_ajuste_ciclo_avulso", clear_on_submit=True):
                cartao_ajuste = st.selectbox(
                    "Cartão", list(opcoes_cartao_ajuste),
                    format_func=lambda x: opcoes_cartao_ajuste[x],
                    key="cartao_ajuste_ciclo",
                )
                col_mes, col_ano = st.columns(2)
                with col_mes:
                    mes_ajuste = st.selectbox(
                        "Mês da fatura", list(range(1, 13)),
                        index=hoje.month - 1,
                        format_func=lambda x: MESES[x - 1],
                        key="mes_ajuste_ciclo",
                    )
                with col_ano:
                    ano_ajuste = st.selectbox(
                        "Ano", anos_ajuste,
                        index=anos_ajuste.index(hoje.year),
                        key="ano_ajuste_ciclo",
                    )
                col_tipo, col_valor = st.columns(2)
                with col_tipo:
                    tipo_ajuste = st.selectbox("Tipo", ["Encargo", "Crédito"], key="tipo_ajuste_ciclo")
                with col_valor:
                    valor_ajuste = st.number_input(
                        "Valor (R$)", min_value=0.01, value=0.01,
                        step=1.00, format="%.2f", key="valor_ajuste_ciclo",
                    )
                descricao_ajuste = st.text_input(
                    "Descrição", placeholder="Ex.: Anuidade, juros, estorno ou cashback",
                    key="descricao_ajuste_ciclo",
                )
                salvar_ajuste = st.form_submit_button(
                    "Adicionar ao ciclo", type="primary", use_container_width=True
                )
            if salvar_ajuste:
                try:
                    registrar_ajuste_no_ciclo(
                        cartao_ajuste, ano_ajuste, mes_ajuste,
                        tipo_ajuste, descricao_ajuste, valor_ajuste,
                    )
                    st.session_state["mensagem_cartoes"] = (
                        f"{tipo_ajuste} registrado na fatura de {_ciclo_texto(ano_ajuste, mes_ajuste)}."
                    )
                    st.rerun()
                except ValueError as erro:
                    st.error(str(erro))

    for fatura in filtradas:
        id_fatura, id_cartao, nome, ano, mes, fechamento, vencimento, total, pago = fatura
        situacao, saldo = calcular_situacao_fatura(total, pago, vencimento)
        with st.container(border=True):
            col_nome, col_venc, col_total, col_status = st.columns([2.5, 1.5, 1.5, 1.2])
            col_nome.write(f"**{nome} · {_ciclo_texto(ano, mes)}**")
            col_nome.caption(f"Fechamento {_data_br(fechamento)}")
            col_venc.caption("Vencimento")
            col_venc.write(_data_br(vencimento))
            col_total.caption("Total")
            col_total.write(f"**{_moeda_com_sinal(total)}**")
            col_status.caption("Situação")
            if situacao == "Paga":
                col_status.success("Paga")
            elif situacao == "Atrasada":
                col_status.error("Atrasada")
            elif situacao == "Parcial atrasada":
                col_status.error("Parcial atrasada")
            elif situacao == "Parcial":
                col_status.warning("Parcial")
            elif situacao == "Sem saldo":
                col_status.info("Sem saldo")
            elif situacao == "Crédito disponível":
                col_status.info("Crédito")
            else:
                col_status.warning("Pendente")
            _mostrar_detalhes_fatura(fatura, expanded=(id_fatura == destaque_id))


def mostrar_cartoes():
    """Interface de compras, parcelamentos, cartões e faturas mensais."""
    _inicializar_estado()
    st.title("💳 Cartões de crédito")
    st.caption("Registre compras uma única vez. O sistema distribui as parcelas nas faturas corretas.")
    _mensagem_pendente()

    cartoes = listar_cartoes_credito(ativos=None)
    faturas = listar_faturas_mensais()

    secao = st.segmented_control(
        "Área de cartões",
        options=["Visão geral", "Compras", "Faturas", "Cartões"],
        default="Visão geral",
        key="secao_cartoes",
        label_visibility="collapsed",
        width="stretch",
    )

    if secao == "Visão geral":
        _mostrar_resumo(cartoes, faturas)
    elif secao == "Compras":
        _aba_compras(cartoes)
    elif secao == "Faturas":
        _aba_faturas(cartoes)
    elif secao == "Cartões":
        _aba_cartoes(cartoes)
