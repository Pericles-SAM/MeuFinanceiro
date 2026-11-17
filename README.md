# Meu Financeiro

Aplicativo local de controle financeiro pessoal, desenvolvido como projeto de aprendizagem em **Desenvolvimento de Sistemas**. O objetivo é organizar despesas, compras no cartão de crédito, faturas, vencimentos e análises financeiras em uma interface simples e moderna.

> **Status:** em desenvolvimento. O projeto já possui módulos funcionais de Despesas, Cartões, Dashboard, Alertas e Relatórios. A preparação da versão estável 1.0 continua em andamento.

## Sobre o projeto

O Meu Financeiro foi pensado para separar claramente os gastos realizados fora do crédito das compras feitas no cartão:

- **Despesas:** gastos pagos ou a pagar por dinheiro, PIX, cartão de débito, boleto, transferência, débito automático e outros meios.
- **Cartões:** compras realizadas no crédito, parcelamentos e faturas mensais.
- **Início:** visão consolidada da situação financeira.
- **Relatórios:** análise de gastos por competência, vencimento ou pagamento.
- **Ajustes:** preferências e configurações do aplicativo.

O projeto prioriza uma estrutura modular, preservação do histórico e regras de cálculo que evitem contabilizar uma compra no cartão novamente quando a fatura é paga.

## Funcionalidades

### Despesas

- Cadastro, edição e consulta de despesas.
- Categorias personalizadas.
- Formas de pagamento: dinheiro, PIX, cartão de débito, boleto, transferência bancária, débito automático e outros.
- Registro da data da despesa, vencimento opcional, mês de referência e situação do pagamento.
- Filtros por período, categoria, forma de pagamento e situação.
- Arquivamento e restauração sem exclusão definitiva dos lançamentos.

### Cartões de crédito

- Cadastro de cartões com dias de fechamento e vencimento.
- Registro de compras à vista ou parceladas.
- Distribuição automática das parcelas nas faturas mensais.
- Suporte a compras parceladas em até 48 vezes.
- Divisão monetária em centavos para evitar diferenças de arredondamento.
- Consulta de compras, parcelas e histórico.
- Pagamentos totais e parciais de faturas.
- Registro de encargos, créditos, estornos e ajustes.
- Detalhamento das compras que compõem cada fatura.

### Dashboard

- Indicadores financeiros calculados a partir dos dados locais.
- Despesas do período, despesas pendentes, saldo de faturas e saídas pagas.
- Gráficos de despesas por categoria e evolução dos gastos.
- Resumo dos cartões.
- Acesso aos itens que compõem uma fatura a partir do resumo.
- Opção de baixar gráficos em PNG, conforme o componente de gráfico utilizado.

### Alertas

- Identificação de despesas e faturas atrasadas.
- Avisos de vencimentos de hoje, amanhã e dos próximos dias.
- Antecedência configurável.
- Consideração do saldo restante de faturas parcialmente pagas.

Os alertas são calculados quando o aplicativo é aberto ou atualizado. Nesta versão, não são enviadas notificações em segundo plano com o aplicativo fechado.

### Relatórios e análises

- Análise por mês de competência, vencimento ou pagamento.
- Seleção de meses específicos, inclusive não consecutivos.
- Comparação entre períodos.
- Médias e totais dos períodos selecionados.
- Análise por categoria e tabelas detalhadas.
- Exportação dos resultados em CSV.

## Tecnologias

- **Python** — regras de negócio e aplicação.
- **Streamlit** — interface web local.
- **SQLite** — armazenamento local dos dados.
- **React + TypeScript** — componentes visuais personalizados.
- **Node.js + npm** — desenvolvimento e compilação do frontend React.
- **uv** — gerenciamento/instalação do pacote Python do componente React durante o desenvolvimento.
- **Git e GitHub** — controle de versão.

Versões utilizadas no ambiente de desenvolvimento do projeto: Python 3.14.5, Streamlit 1.67.0, Node.js 24.16.0, npm 11.13.0 e uv 0.13.8. Outras versões compatíveis podem exigir ajustes.

## Estrutura do projeto

```text
MeuFinanceiro/
├── app.py
├── components/
│   ├── estilos.py
│   ├── formatacao.py
│   ├── navegacao.py
│   └── react/
│       └── meu-financeiro-count-up/
│           ├── example.py
│           └── meu_financeiro_count_up/
│               └── frontend/
├── database/
│   ├── alertas.py
│   ├── cartoes.py
│   ├── dashboard.py
│   ├── db.py
│   └── relatorios.py
├── modulos/
│   ├── ajustes.py
│   ├── cartoes.py
│   ├── despesas.py
│   ├── inicio.py
│   ├── relatorios.py
│   └── rotas.py
├── styles/
│   └── main.css
├── tests/
└── .streamlit/
    └── config.toml
```

As páginas ficam separadas em `modulos/`; as consultas e regras de persistência ficam em `database/`; elementos compartilhados ficam em `components/`. O `app.py` inicializa a aplicação e direciona a navegação.

## Executar localmente

### Requisitos

- Python instalado.
- Git.
- Para desenvolver o componente React: Node.js, npm e uv.

### 1. Clonar o repositório

```powershell
git clone https://github.com/Pericles-SAM/MeuFinanceiro.git
cd MeuFinanceiro
```

### 2. Criar e ativar o ambiente virtual (PowerShell)

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

### 3. Instalar as dependências Python

```powershell
python -m pip install --upgrade pip
pip install streamlit==1.67.0 pandas
```

### 4. Iniciar o aplicativo

Na raiz do projeto:

```powershell
streamlit run app.py
```

O Streamlit disponibilizará o endereço local, normalmente `http://localhost:8501`.

Na primeira execução, a aplicação inicializa a estrutura do SQLite. Um clone novo começa com um banco local novo; os dados pessoais do banco de outra instalação não são baixados do GitHub.

## Desenvolver o componente React

O componente Count Up possui uma demonstração isolada para desenvolvimento. A versão atual valida a comunicação entre Python e React; sua integração aos indicadores principais do Dashboard ainda pode evoluir.

Com o ambiente virtual ativado, a partir da raiz do projeto:

```powershell
cd components/react/meu-financeiro-count-up
uv pip install -e .
cd meu_financeiro_count_up/frontend
npm ci
```

Para recompilar o frontend em modo de desenvolvimento, mantenha este comando em um terminal:

```powershell
npm run dev
```

Em outro terminal, com o ambiente virtual ativado:

```powershell
cd components/react/meu-financeiro-count-up
streamlit run example.py
```

Para gerar uma compilação de produção do frontend:

```powershell
cd components/react/meu-financeiro-count-up/meu_financeiro_count_up/frontend
npm run build
```

## Executar os testes

O projeto utiliza testes automatizados com `unittest`. Na raiz do repositório, com o ambiente virtual ativado:

```powershell
python -m unittest discover -s tests -v
```

Os testes utilizam bancos temporários para verificar regras e operações sem depender dos dados financeiros pessoais da instalação local.

## Dados e privacidade

- O banco local é armazenado em `database/financeiro.db`.
- Arquivos SQLite (`*.db`, `*.sqlite` e `*.sqlite3`), ambientes virtuais, `node_modules` e arquivos de segredos são ignorados pelo Git por meio do `.gitignore`.
- Faça backups regulares do arquivo do banco em um local seguro, separado do repositório.
- O GitHub armazena o código-fonte e os arquivos necessários ao desenvolvimento, não os lançamentos financeiros locais.

## Roadmap

- [x] Estrutura modular da aplicação.
- [x] Identidade visual Soft Blue e temas claro/escuro.
- [x] Cadastro e gerenciamento de despesas.
- [x] Cartões, compras parceladas e faturas mensais.
- [x] Dashboard com dados reais.
- [x] Alertas financeiros.
- [x] Relatórios e análises.
- [x] Demonstração isolada do componente React Count Up.
- [ ] Revisão e conclusão das configurações.
- [ ] Backup e restauração pela interface.
- [ ] Revisão integrada de segurança, consistência e experiência de uso.
- [ ] Integração seletiva de componentes React ao Dashboard.
- [ ] Preparação e validação da versão 1.0.

## Objetivo de aprendizagem

O Meu Financeiro também é um projeto prático de aprendizagem em Desenvolvimento de Sistemas. Seu desenvolvimento busca aplicar organização modular, funções, persistência de dados, modelagem relacional, interfaces, integração entre Python e React, testes e controle de versão.

O princípio do projeto é evoluir com cuidado: **manter uma aplicação simples de utilizar, organizada por dentro e preparada para receber melhorias sem comprometer a qualidade do código.**

---

Desenvolvido como projeto pessoal de estudo por **Pericles-SAM**.
