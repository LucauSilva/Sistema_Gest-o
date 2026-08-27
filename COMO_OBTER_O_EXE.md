# Como obter o ENPCB.exe real do Windows (automático, na nuvem, grátis)

Este guia explica como usar o **GitHub Actions** — um serviço gratuito do
GitHub que disponibiliza computadores Windows na nuvem — para compilar
o `ENPCB.exe` **de verdade**, sem precisar de ter um computador Windows
à mão. Não é preciso saber programar; é só seguir os passos.

O ficheiro `.github/workflows/build-windows.yml` incluído neste pacote já
faz todo o trabalho técnico sozinho — só precisa de colocar o código
numa conta GitHub (gratuita) e o `.exe` fica pronto a descarregar em
cerca de 1 a 2 minutos.

---

## Passo 1 — Criar uma conta GitHub (se ainda não tiver)

1. Aceda a **https://github.com/signup**
2. Crie uma conta gratuita (só precisa de um e-mail)

---

## Passo 2 — Criar um novo repositório

1. Já com sessão iniciada, aceda a **https://github.com/new**
2. Em "Repository name", escreva por exemplo: `enpcb-sistema`
3. Pode deixar como **Private** (privado) — só a sua conta vê o código
4. **Não** marque nenhuma das opções extra (README, .gitignore, licença)
5. Clique em **Create repository**

---

## Passo 3 — Carregar os ficheiros deste pacote

Na página que aparece a seguir à criação do repositório:

1. Clique no link **"uploading an existing file"** (carregar ficheiro existente)
2. Arraste para lá **toda a pasta** deste pacote (`enpcb_sistema.py`, o
   ficheiro `LEIAME.md`, os `.bat`/`.sh`, e a pasta `.github` inteira —
   é importante que a pasta `.github/workflows/build-windows.yml` também
   seja enviada, é ela que faz a mágica)

   > **Dica:** se o seu navegador não deixar arrastar uma pasta inteira
   > de uma vez, pode arrastar os ficheiros individualmente — mas
   > certifique-se de que o caminho `.github/workflows/build-windows.yml`
   > fica exactamente assim depois de enviado (o GitHub cria as pastas
   > automaticamente a partir do nome do ficheiro que arrastar, ou pode
   > usar a opção "Add file → Create new file" e escrever esse caminho
   > completo no nome do ficheiro).

3. Em baixo, clique em **Commit changes** (pode deixar a mensagem como está)

---

## Passo 4 — Deixar o GitHub compilar o .exe

Assim que os ficheiros forem enviados, a compilação **arranca sozinha**
(porque o ficheiro `enpcb_sistema.py` foi alterado/enviado). Para
acompanhar:

1. No topo do repositório, clique no separador **Actions**
2. Verá uma entrada chamada **"Construir ENPCB.exe (Windows)"** a correr
   (um círculo amarelo a girar). Espere cerca de 1 a 2 minutos até ficar
   com um ✔ verde.

Se quiser voltar a correr manualmente mais tarde (por exemplo depois de
alterar o `enpcb_sistema.py`):
1. Separador **Actions**
2. Clique no workflow **"Construir ENPCB.exe (Windows)"** na lista à esquerda
3. Botão **Run workflow** → **Run workflow**

---

## Passo 5 — Descarregar o ENPCB.exe

1. Ainda no separador **Actions**, clique na execução que já terminou
   (✔ verde)
2. Em baixo, na secção **Artifacts**, verá **"ENPCB-Windows"**
3. Clique para descarregar — é um `.zip` que contém o `ENPCB.exe`
4. Extraia o `.zip` e já tem o executável real do Windows, pronto a usar
   em qualquer computador Windows, sem instalar nada e sem Internet.

---

## Opcional — criar uma "Release" oficial com o .exe anexado

Se preferir ter uma página fixa e permanente de download (em vez do
"Artifact" que expira ao fim de 90 dias), pode criar uma *tag* de versão:

1. No repositório, vá a **Releases** (barra lateral direita) → **Create a new release**
2. Em "Choose a tag", escreva `v1.0.0` e clique em **Create new tag**
3. Preencha um título (ex: "ENPCB v1.0.0") e clique em **Publish release**
4. O workflow corre novamente e, desta vez, **anexa automaticamente**
   o `ENPCB.exe` à própria página da Release — um link permanente que
   pode partilhar com qualquer pessoa da ENPCB.

---

## Sempre que alterar o sistema

Sempre que o Claude (ou outra pessoa) editar o `enpcb_sistema.py` e lhe
enviar uma versão nova, repita apenas o **Passo 3** (carregar o ficheiro
actualizado) — a compilação do novo `.exe` acontece automaticamente.

---

## Dúvidas frequentes

**"Preciso de saber programar para fazer isto?"**
Não. Estes passos são só de "arrastar ficheiros" e "clicar em botões"
na página do GitHub.

**"Isto custa alguma coisa?"**
Não, o GitHub Actions é gratuito para repositórios privados dentro de um
limite generoso de minutos por mês (muito acima do que este projecto
usa) — usar isto uma vez por semana durante anos não custaria nada.

**"O repositório privado é seguro?"**
Sim, só quem tiver a sua conta GitHub (ou pessoas que convide) consegue
ver o código e os ficheiros. Ainda assim, tal como referido no LEIAME
principal, não coloque dados reais de formandos dentro do código — a
base de dados (`enpcb.db`) nunca vai para o GitHub, fica sempre só no
computador onde a aplicação corre.
