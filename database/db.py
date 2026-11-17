import sqlite3
from datetime import date as data_calendario
from contextlib import contextmanager
from pathlib import Path


# ==========================================
# CONFIGURAÇÃO DO BANCO DE DADOS
# ==========================================

PASTA = Path(__file__).resolve().parent
BANCO = PASTA / "financeiro.db"


@contextmanager
def conectar():
    """Abre uma conexão SQLite e garante commit, rollback e fechamento."""
    BANCO.parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(BANCO, timeout=30)
    conexao.execute("PRAGMA foreign_keys = ON")

    try:
        yield conexao
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()


# ==========================================
# INICIALIZAÇÃO E MIGRAÇÃO DO BANCO
# ==========================================

def inicializar_banco():
    """Cria as tabelas e adiciona colunas ausentes em bancos antigos."""
    with conectar() as conexao:
        cursor = conexao.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                descricao TEXT NOT NULL,
                valor REAL NOT NULL,
                categoria TEXT NOT NULL,
                vencimento TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pendente',
                pago_em TEXT,
                criado_em TEXT DEFAULT (datetime('now', 'localtime')),
                referencia TEXT,
                arquivada INTEGER NOT NULL DEFAULT 0,
                forma_pagamento TEXT NOT NULL DEFAULT 'Não informado',
                data_despesa TEXT,
                tem_vencimento INTEGER NOT NULL DEFAULT 1
            )
        """)

        # Migração segura: preserva bancos criados por versões anteriores.
        colunas_contas = {
            coluna[1]
            for coluna in cursor.execute("PRAGMA table_info(contas)").fetchall()
        }

        migracoes_contas = {
            "pago_em": "ALTER TABLE contas ADD COLUMN pago_em TEXT",
            "criado_em": "ALTER TABLE contas ADD COLUMN criado_em TEXT",
            "referencia": "ALTER TABLE contas ADD COLUMN referencia TEXT",
            "arquivada": (
                "ALTER TABLE contas "
                "ADD COLUMN arquivada INTEGER NOT NULL DEFAULT 0"
            ),
            "forma_pagamento": (
                "ALTER TABLE contas "
                "ADD COLUMN forma_pagamento TEXT NOT NULL DEFAULT 'Não informado'"
            ),
            "data_despesa": "ALTER TABLE contas ADD COLUMN data_despesa TEXT",
            "tem_vencimento": (
                "ALTER TABLE contas "
                "ADD COLUMN tem_vencimento INTEGER NOT NULL DEFAULT 1"
            ),
        }

        for nome_coluna, comando in migracoes_contas.items():
            if nome_coluna not in colunas_contas:
                cursor.execute(comando)

        # Contas antigas passam a usar o mês do vencimento como referência inicial.
        cursor.execute("""
            UPDATE contas
            SET referencia = substr(vencimento, 1, 7)
            WHERE referencia IS NULL OR referencia = ''
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE COLLATE NOCASE
            )
        """)

        # Importa categorias já usadas antes da criação da tabela de categorias.
        cursor.execute("""
            INSERT OR IGNORE INTO categorias (nome)
            SELECT DISTINCT TRIM(categoria)
            FROM contas
            WHERE categoria IS NOT NULL AND TRIM(categoria) <> ''
        """)

        categorias_iniciais = [
            "Moradia",
            "Alimentação",
            "Transporte",
            "Saúde",
            "Educação",
            "Outros",
        ]

        cursor.executemany(
            "INSERT OR IGNORE INTO categorias (nome) VALUES (?)",
            [(categoria,) for categoria in categorias_iniciais],
        )

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cartoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                dia_fechamento INTEGER NOT NULL,
                dia_vencimento INTEGER NOT NULL,
                criado_em TEXT DEFAULT (datetime('now', 'localtime')),
                CHECK (dia_fechamento BETWEEN 1 AND 31),
                CHECK (dia_vencimento BETWEEN 1 AND 31)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS faturas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cartao_id INTEGER NOT NULL,
                valor REAL NOT NULL,
                vencimento TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pendente',
                pago_em TEXT,
                criado_em TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (cartao_id)
                    REFERENCES cartoes(id)
                    ON DELETE RESTRICT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS configuracoes (
                chave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_contas_vencimento
            ON contas(vencimento)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_contas_forma_pagamento
            ON contas(forma_pagamento)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_contas_data_despesa
            ON contas(data_despesa)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_faturas_vencimento
            ON faturas(vencimento)
        """)

        cursor.execute("""
            INSERT OR IGNORE INTO configuracoes (chave, valor)
            VALUES ('dias_alerta', '3')
        """)


# ==========================================
# CATEGORIAS
# ==========================================

def adicionar_categoria(nome):
    nome = nome.strip()
    if not nome:
        raise ValueError("O nome da categoria não pode ficar vazio.")

    with conectar() as conexao:
        cursor = conexao.execute(
            "INSERT OR IGNORE INTO categorias (nome) VALUES (?)",
            (nome,),
        )
        return cursor.rowcount > 0


def listar_categorias():
    with conectar() as conexao:
        resultado = conexao.execute(
            "SELECT nome FROM categorias ORDER BY nome"
        ).fetchall()
        return [linha[0] for linha in resultado]


# ==========================================
# DESPESAS — FORMAS DE PAGAMENTO E CONSULTAS
# ==========================================

FORMAS_PAGAMENTO = (
    "Dinheiro",
    "PIX",
    "Cartão de débito",
    "Boleto",
    "Transferência bancária",
    "Débito automático",
    "Outro",
)

FORMAS_PAGAMENTO_HISTORICAS = ("Não informado",)


def _validar_data_iso(valor, rotulo, obrigatoria=True):
    if not valor:
        if obrigatoria:
            raise ValueError(f"Informe {rotulo}.")
        return None
    try:
        data_calendario.fromisoformat(str(valor)[:10])
    except ValueError as erro:
        raise ValueError(f"{rotulo.capitalize()} inválida. Use uma data válida.") from erro
    return str(valor)[:10]


def _validar_referencia(referencia):
    try:
        ano, mes = map(int, referencia.split("-"))
        if ano < 1900 or not 1 <= mes <= 12:
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        raise ValueError("O mês de referência deve estar no formato AAAA-MM.")
    return f"{ano:04d}-{mes:02d}"


def _validar_despesa(descricao, valor, categoria, forma_pagamento):
    descricao = (descricao or "").strip()
    categoria = (categoria or "").strip()
    forma_pagamento = (forma_pagamento or "").strip()

    if not descricao:
        raise ValueError("Informe a descrição da despesa.")
    if valor <= 0:
        raise ValueError("O valor deve ser maior que zero.")
    if not categoria:
        raise ValueError("Selecione uma categoria.")
    if forma_pagamento not in FORMAS_PAGAMENTO + FORMAS_PAGAMENTO_HISTORICAS:
        raise ValueError("Selecione uma forma de pagamento válida.")
    return descricao, categoria, forma_pagamento


def adicionar_despesa(
    descricao, valor, categoria, forma_pagamento, data_despesa,
    tem_vencimento=False, vencimento=None, referencia=None,
    status="Pendente", data_pagamento=None,
):
    """Registra uma despesa fora do crédito, preservando datas distintas.

    Quando não há vencimento, a coluna legada `vencimento` recebe a data da
    despesa para manter compatibilidade, enquanto `tem_vencimento=0` deixa
    claro que não existe uma data de vencimento real.
    """
    descricao, categoria, forma_pagamento = _validar_despesa(
        descricao, valor, categoria, forma_pagamento
    )

    if status not in ("Pago", "Pendente"):
        raise ValueError("A situação deve ser Pago ou Pendente.")
    if not data_despesa:
        raise ValueError("Informe a data da despesa.")
    if tem_vencimento and not vencimento:
        raise ValueError("Informe a data de vencimento.")

    data_despesa = _validar_data_iso(data_despesa, "a data da despesa")
    vencimento = _validar_data_iso(
        vencimento, "a data de vencimento", obrigatoria=bool(tem_vencimento)
    )
    vencimento_armazenado = vencimento if tem_vencimento else data_despesa
    referencia = _validar_referencia(referencia or data_despesa[:7])

    if status == "Pago":
        data_pagamento = _validar_data_iso(
            data_pagamento or data_despesa, "a data do pagamento"
        )
    else:
        data_pagamento = None

    with conectar() as conexao:
        cursor = conexao.execute("""
            INSERT INTO contas (
                descricao, valor, categoria, vencimento, referencia, status,
                pago_em, forma_pagamento, data_despesa, tem_vencimento
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            descricao, float(valor), categoria, vencimento_armazenado,
            referencia, status, data_pagamento, forma_pagamento,
            data_despesa, int(bool(tem_vencimento)),
        ))
        return cursor.lastrowid


def editar_despesa(
    id_despesa, descricao, valor, categoria, forma_pagamento,
    data_despesa, tem_vencimento=False, vencimento=None, referencia=None,
):
    """Atualiza os dados descritivos sem alterar o estado do pagamento."""
    descricao, categoria, forma_pagamento = _validar_despesa(
        descricao, valor, categoria, forma_pagamento
    )
    if not data_despesa:
        raise ValueError("Informe a data da despesa.")
    if tem_vencimento and not vencimento:
        raise ValueError("Informe a data de vencimento.")

    data_despesa = _validar_data_iso(data_despesa, "a data da despesa")
    vencimento = _validar_data_iso(
        vencimento, "a data de vencimento", obrigatoria=bool(tem_vencimento)
    )
    vencimento_armazenado = vencimento if tem_vencimento else data_despesa
    referencia = _validar_referencia(referencia or data_despesa[:7])

    with conectar() as conexao:
        cursor = conexao.execute("""
            UPDATE contas
            SET descricao = ?, valor = ?, categoria = ?,
                forma_pagamento = ?, data_despesa = ?,
                tem_vencimento = ?, vencimento = ?, referencia = ?
            WHERE id = ? AND arquivada = 0
        """, (
            descricao, float(valor), categoria, forma_pagamento,
            data_despesa, int(bool(tem_vencimento)), vencimento_armazenado,
            referencia, id_despesa,
        ))
        return cursor.rowcount > 0


def listar_despesas(
    arquivada=False, forma_pagamento=None, categoria=None, status=None,
    referencia=None,
):
    """Lista despesas com filtros opcionais; retorna colunas em ordem fixa."""
    sql = """
        SELECT id, descricao, valor, categoria, forma_pagamento,
               data_despesa, tem_vencimento, vencimento, referencia,
               status, pago_em, arquivada
        FROM contas
        WHERE arquivada = ?
    """
    parametros = [int(bool(arquivada))]

    if forma_pagamento and forma_pagamento != "Todas":
        sql += " AND forma_pagamento = ?"
        parametros.append(forma_pagamento)
    if categoria and categoria != "Todas":
        sql += " AND categoria = ?"
        parametros.append(categoria)
    if status and status != "Todas":
        sql += " AND status = ?"
        parametros.append(status)
    if referencia and referencia != "Todas":
        sql += " AND referencia = ?"
        parametros.append(referencia)

    if arquivada:
        sql += " ORDER BY COALESCE(data_despesa, vencimento) DESC, id DESC"
    else:
        sql += " ORDER BY CASE WHEN tem_vencimento = 1 THEN vencimento END ASC, id ASC"

    with conectar() as conexao:
        return conexao.execute(sql, parametros).fetchall()


def obter_despesa(id_despesa):
    with conectar() as conexao:
        return conexao.execute("""
            SELECT id, descricao, valor, categoria, forma_pagamento,
                   data_despesa, tem_vencimento, vencimento, referencia,
                   status, pago_em, arquivada
            FROM contas WHERE id = ?
        """, (id_despesa,)).fetchone()


# ==========================================
# CONTAS
# ==========================================

def adicionar_conta(descricao, valor, categoria, vencimento, referencia=None):
    descricao = descricao.strip()
    if not descricao:
        raise ValueError("Informe a descrição da conta.")
    if valor <= 0:
        raise ValueError("O valor deve ser maior que zero.")
    if not categoria or not categoria.strip():
        raise ValueError("Selecione uma categoria.")

    if referencia is None:
        referencia = vencimento[:7]

    with conectar() as conexao:
        cursor = conexao.execute("""
            INSERT INTO contas
                (descricao, valor, categoria, vencimento, referencia)
            VALUES (?, ?, ?, ?, ?)
        """, (descricao, valor, categoria.strip(), vencimento, referencia))
        return cursor.lastrowid


def listar_contas():
    with conectar() as conexao:
        return conexao.execute("""
            SELECT id, descricao, valor, categoria, vencimento, status
            FROM contas
            WHERE arquivada = 0
            ORDER BY vencimento ASC, id ASC
        """).fetchall()


def obter_conta(id_conta):
    """Retorna colunas em ordem fixa, sem depender de SELECT *."""
    with conectar() as conexao:
        return conexao.execute("""
            SELECT id, descricao, valor, categoria, vencimento, status,
                   pago_em, criado_em, referencia, arquivada
            FROM contas
            WHERE id = ?
        """, (id_conta,)).fetchone()


def editar_conta(
    id_conta, descricao, valor, categoria, vencimento, referencia=None
):
    descricao = descricao.strip()
    if not descricao:
        raise ValueError("Informe a descrição da conta.")
    if valor <= 0:
        raise ValueError("O valor deve ser maior que zero.")
    if not categoria or not categoria.strip():
        raise ValueError("Selecione uma categoria.")

    if referencia is None:
        referencia = vencimento[:7]

    with conectar() as conexao:
        cursor = conexao.execute("""
            UPDATE contas
            SET descricao = ?,
                valor = ?,
                categoria = ?,
                vencimento = ?,
                referencia = ?
            WHERE id = ? AND arquivada = 0
        """, (
            descricao,
            valor,
            categoria.strip(),
            vencimento,
            referencia,
            id_conta,
        ))
        return cursor.rowcount > 0


def marcar_como_paga(id_conta, data_pagamento=None):
    """Marca uma despesa como paga; aceita data manual ou usa a data atual."""
    data_pagamento = str(data_pagamento)[:10] if data_pagamento else None
    with conectar() as conexao:
        if data_pagamento:
            cursor = conexao.execute("""
                UPDATE contas SET status = 'Pago', pago_em = ?
                WHERE id = ? AND arquivada = 0
            """, (data_pagamento, id_conta))
        else:
            cursor = conexao.execute("""
                UPDATE contas
                SET status = 'Pago', pago_em = datetime('now', 'localtime')
                WHERE id = ? AND arquivada = 0
            """, (id_conta,))
        return cursor.rowcount > 0


def marcar_como_pendente(id_conta):
    with conectar() as conexao:
        cursor = conexao.execute("""
            UPDATE contas
            SET status = 'Pendente',
                pago_em = NULL
            WHERE id = ? AND arquivada = 0
        """, (id_conta,))
        return cursor.rowcount > 0


def arquivar_conta(id_conta):
    """Arquiva a conta sem apagar seu histórico financeiro."""
    with conectar() as conexao:
        cursor = conexao.execute(
            "UPDATE contas SET arquivada = 1 WHERE id = ? AND arquivada = 0",
            (id_conta,),
        )
        return cursor.rowcount > 0


def restaurar_conta(id_conta):
    with conectar() as conexao:
        cursor = conexao.execute(
            "UPDATE contas SET arquivada = 0 WHERE id = ? AND arquivada = 1",
            (id_conta,),
        )
        return cursor.rowcount > 0


def listar_contas_arquivadas():
    with conectar() as conexao:
        return conexao.execute("""
            SELECT id, descricao, valor, categoria, vencimento, status
            FROM contas
            WHERE arquivada = 1
            ORDER BY vencimento DESC, id DESC
        """).fetchall()


# ==========================================
# CARTÕES DE CRÉDITO
# ==========================================

def adicionar_cartao(nome, dia_fechamento, dia_vencimento):
    nome = nome.strip()
    if not nome:
        raise ValueError("Informe o nome do cartão.")
    if not 1 <= dia_fechamento <= 31:
        raise ValueError("Dia de fechamento inválido.")
    if not 1 <= dia_vencimento <= 31:
        raise ValueError("Dia de vencimento inválido.")

    with conectar() as conexao:
        cursor = conexao.execute("""
            INSERT INTO cartoes (nome, dia_fechamento, dia_vencimento)
            VALUES (?, ?, ?)
        """, (nome, dia_fechamento, dia_vencimento))
        return cursor.lastrowid


def listar_cartoes():
    with conectar() as conexao:
        return conexao.execute("""
            SELECT id, nome, dia_fechamento, dia_vencimento
            FROM cartoes
            ORDER BY nome
        """).fetchall()


def editar_cartao(id_cartao, nome, dia_fechamento, dia_vencimento):
    nome = nome.strip()
    if not nome:
        raise ValueError("Informe o nome do cartão.")
    if not 1 <= dia_fechamento <= 31:
        raise ValueError("Dia de fechamento inválido.")
    if not 1 <= dia_vencimento <= 31:
        raise ValueError("Dia de vencimento inválido.")

    with conectar() as conexao:
        cursor = conexao.execute("""
            UPDATE cartoes
            SET nome = ?, dia_fechamento = ?, dia_vencimento = ?
            WHERE id = ?
        """, (nome, dia_fechamento, dia_vencimento, id_cartao))
        return cursor.rowcount > 0


def excluir_cartao(id_cartao):
    """Remove cartão somente se não houver faturas vinculadas."""
    with conectar() as conexao:
        cursor = conexao.execute(
            "DELETE FROM cartoes WHERE id = ?",
            (id_cartao,),
        )
        return cursor.rowcount > 0


# ==========================================
# FATURAS
# ==========================================

def adicionar_fatura(cartao_id, valor, vencimento):
    if valor <= 0:
        raise ValueError("O valor da fatura deve ser positivo.")

    with conectar() as conexao:
        cursor = conexao.execute("""
            INSERT INTO faturas (cartao_id, valor, vencimento)
            VALUES (?, ?, ?)
        """, (cartao_id, valor, vencimento))
        return cursor.lastrowid


def listar_faturas():
    with conectar() as conexao:
        return conexao.execute("""
            SELECT f.id, c.nome, f.cartao_id, f.valor,
                   f.vencimento, f.status, f.pago_em
            FROM faturas AS f
            INNER JOIN cartoes AS c ON f.cartao_id = c.id
            ORDER BY f.vencimento ASC, f.id ASC
        """).fetchall()


def editar_fatura(id_fatura, cartao_id, valor, vencimento):
    if valor <= 0:
        raise ValueError("O valor da fatura deve ser positivo.")

    with conectar() as conexao:
        cursor = conexao.execute("""
            UPDATE faturas
            SET cartao_id = ?, valor = ?, vencimento = ?
            WHERE id = ?
        """, (cartao_id, valor, vencimento, id_fatura))
        return cursor.rowcount > 0


def excluir_fatura(id_fatura):
    with conectar() as conexao:
        cursor = conexao.execute(
            "DELETE FROM faturas WHERE id = ?",
            (id_fatura,),
        )
        return cursor.rowcount > 0


def marcar_fatura_como_paga(id_fatura):
    with conectar() as conexao:
        cursor = conexao.execute("""
            UPDATE faturas
            SET status = 'Pago',
                pago_em = datetime('now', 'localtime')
            WHERE id = ?
        """, (id_fatura,))
        return cursor.rowcount > 0


def marcar_fatura_como_pendente(id_fatura):
    with conectar() as conexao:
        cursor = conexao.execute("""
            UPDATE faturas
            SET status = 'Pendente', pago_em = NULL
            WHERE id = ?
        """, (id_fatura,))
        return cursor.rowcount > 0


# ==========================================
# CONFIGURAÇÕES
# ==========================================

def obter_configuracao(chave, padrao=None):
    with conectar() as conexao:
        resultado = conexao.execute(
            "SELECT valor FROM configuracoes WHERE chave = ?",
            (chave,),
        ).fetchone()
        return resultado[0] if resultado else padrao


def salvar_configuracao(chave, valor):
    with conectar() as conexao:
        conexao.execute("""
            INSERT INTO configuracoes (chave, valor)
            VALUES (?, ?)
            ON CONFLICT(chave)
            DO UPDATE SET valor = excluded.valor
        """, (chave, str(valor)))


if __name__ == "__main__":
    inicializar_banco()
    print("Banco de dados inicializado com sucesso!")
