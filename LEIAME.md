# ENPCB — Sistema Integrado de Gestão de Formação
### Versão Python — aplicação de secretária, instalável e 100% offline

Escola Nacional de Protecção Civil e Bombeiros — Angola

---

## O que é

Esta é a versão **Python** do sistema de gestão académica da ENPCB — uma
aplicação de computador (não uma página web) que corre inteiramente no seu
PC, **sem precisar de ligação à Internet** em nenhum momento, e que guarda
todos os dados no seu próprio computador (numa base de dados local SQLite).

Foi escrita apenas com a biblioteca padrão do Python (`tkinter` para os
ecrãs, `sqlite3` para a base de dados) — não depende de nenhum serviço
externo nem de bibliotecas adicionais para funcionar.

**Funcionalidades incluídas:**
- Ecrã de acesso com utilizador/senha
- Cadastro e consulta de Formandos, Instrutores, Cursos, Disciplinas, Turmas
- Gestão de Matrículas (com número de processo automático)
- Mini-Pautas de notas (Avaliação Contínua + Exame Final)
- Registo de Presenças por sessão (alimenta a assiduidade automaticamente)
- Cálculo automático de média, assiduidade e situação final
- Emissão de Certificados com numeração automática (ex: `ENPCB/2026/0001`),
  gerados como um documento pronto a imprimir
- Relatórios e exportação para CSV (compatível com Excel)
- Pesquisa global
- Cópia de segurança (exportar/restaurar toda a base de dados em `.json`)
- Gestão de Utilizadores e Permissões

---

## Como experimentar imediatamente (sem instalar nada)

Se já tiver Python instalado no seu computador (a maioria dos Windows,
Mac e Linux recentes já o têm, ou pode instalar em
https://www.python.org/downloads/ — marque a opção **"Add Python to PATH"**
durante a instalação no Windows):

1. Abra uma janela de comando (Terminal / Prompt de Comando) nesta pasta
2. Corra:
   ```
   python enpcb_sistema.py
   ```
   (em Linux/Mac pode ser necessário `python3` em vez de `python`)
3. A aplicação abre. No primeiro arranque, entre com:
   - **Utilizador:** `admin`
   - **Senha:** `admin`

> Em Linux, se aparecer um erro sobre "tkinter", instale com:
> `sudo apt install python3-tk`

---

## Como criar um instalável / executável autónomo

Há duas formas de obter um `.exe` de Windows pronto a usar:

### Opção A — Automática, na nuvem, sem precisar de um Windows (recomendado)
Veja o ficheiro **`COMO_OBTER_O_EXE.md`** incluído neste pacote — um guia
passo a passo (com capturas de ecrã descritas em texto) para usar o
GitHub Actions, um serviço gratuito que compila o `ENPCB.exe` automaticamente
numa máquina Windows na nuvem, mesmo que você só tenha Mac/Linux à mão.
Não é preciso saber programar.

### Opção B — Manual, num computador Windows
Se já tiver acesso a um computador Windows, faça duplo-clique em
**`instalar_windows.bat`**. No final, o executável fica em `dist\ENPCB.exe`.

### Linux / macOS
No terminal, dentro desta pasta:
```
./instalar_linux_mac.sh
```
No final, o executável fica em `dist/ENPCB`.

Depois disso, pode copiar esse único ficheiro para onde quiser — já não
precisa da pasta com o código nem de Internet para o correr.

---

## Onde ficam os dados

Os dados ficam guardados no seu computador, em:

- **Windows:** `C:\Users\O_SEU_UTILIZADOR\ENPCB\dados\enpcb.db`
- **macOS/Linux:** `~/ENPCB/dados/enpcb.db`

Os certificados emitidos (documentos HTML prontos a imprimir) ficam em
`ENPCB/dados/certificados/` na mesma pasta.

**Recomendação importante:** use regularmente a opção **Backup** dentro
da aplicação para exportar uma cópia de segurança (`.json`) para uma
pen USB, disco externo ou pasta na nuvem da sua preferência. Isto é a
única forma de recuperar os dados caso o computador tenha um problema.

---

## Acesso e Utilizadores

O ecrã de acesso serve para organizar quem usa o sistema e para os
"perfis" (Administrador, Secretário Pedagógico, Instrutor, Consulta),
mas **não é uma segurança de nível empresarial**: como tudo corre
localmente no mesmo computador, as senhas ficam guardadas na mesma
base de dados local, tal como os restantes dados. Para uso por uma
só secretária/computador isto é perfeitamente adequado; se precisar
de vários computadores a aceder aos mesmos dados em rede, ou de
segurança mais forte, essa é uma reformulação diferente (com servidor),
fora do âmbito desta versão local.

Pode gerir utilizadores em **Utilizadores e Permissões** dentro da
aplicação (é recomendável alterar a senha `admin` predefinida no
primeiro uso).

---

## Regras de cálculo (podem ser ajustadas a pedido)

- **Média por disciplina** = (Avaliação Contínua + Exame Final) / 2
- **Assiduidade** = percentagem de presenças nas sessões lançadas em
  "Presenças", para aquela turma e disciplina
- **Situação por disciplina:**
  - `Aprovado` — média ≥ 10 e assiduidade ≥ 75%
  - `Reprovado` — média < 10 (com assiduidade ≥ 75%)
  - `Excluído por Faltas` — assiduidade < 75%
- **Situação final do formando** = Aprovado apenas se aprovado em
  **todas** as disciplinas do curso da sua turma

Se a ENPCB usar uma fórmula de ponderação diferente (ex: pesos distintos
entre avaliação contínua e exame, ou um limite de faltas diferente),
esta lógica está isolada nas funções `calc_nota()` e
`matricula_situacao()` no ficheiro `enpcb_sistema.py`, prontas a ajustar.

---

## Estrutura do ficheiro

Tudo está num único ficheiro `enpcb_sistema.py` para simplificar a
instalação, organizado em secções claramente comentadas:
1. Base de dados (esquema SQLite)
2. Cálculos pedagógicos
3. Definição das entidades (para os formulários e tabelas)
4. Interface gráfica (ecrã de acesso, painel, cada módulo)

---

## Suporte

Este sistema foi construído à medida pelo Claude (Anthropic) a pedido do
utilizador. Não existe uma equipa de suporte formal — para alterações,
correções ou novas funcionalidades, volte à conversa onde este sistema
foi criado e descreva o que precisa.
