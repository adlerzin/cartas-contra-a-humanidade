# Cartas Contra a Humanidade Online

Um jogo de cartas multiplayer em tempo real, inspirado no popular "Cards Against Humanity", desenvolvido com **Python (WebSockets)** no backend e **HTML, CSS, JavaScript** no frontend. Jogue com seus amigos online e descubra as combinações de cartas mais hilárias e irreverentes!

---

## ✨ Funcionalidades

* 🎮 **Multiplayer em Tempo Real**: Jogue com múltiplos amigos em uma mesma sala, com atualizações instantâneas via WebSockets.
* 🏠 **Gerenciamento de Salas**: Crie ou entre em salas de jogo separadas, permitindo que vários grupos joguem simultaneamente.
* 🃏 **Lógica de Jogo Completa**:

  * Exibição de cartas pretas (perguntas/frases).
  * Distribuição de cartas brancas (respostas) para os jogadores.
  * Submissão de cartas brancas.
  * Modo de votação (showcase) para o Czar de Cartas escolher a melhor resposta.
  * Pontuação e acompanhamento dos resultados em tempo real.
  * Transição automática de rodadas.
* ⏳ **Contagem Regressiva**: Timer para início do jogo e das rodadas.
* 🏆 **Tela de Vitória**: Exibe o vencedor, pontuações finais e a carta vencedora da última rodada com efeitos visuais.
* 💻 **Interface Intuitiva**: Design limpo e responsivo, adaptável a diferentes tamanhos de tela.
* 🎉 **Efeitos Visuais**: Animações sutis e confetes na tela de vitória para uma experiência mais dinâmica.

---

## 🚀 Como Rodar o Projeto

### Pré-requisitos

* Python **3.8+**
* `pip` instalado

---

### 1️⃣ Clonar o Repositório

```bash
git clone https://github.com/adlerzin/cartas-contra-a-humanidade
cd cartas-contra-humanidade
```

---

### 2️⃣ Instalar Dependências do Backend

Dentro da pasta raiz do projeto (onde estão `app.py`, `rooms.py` e `cartas.py`):

```bash
pip install websockets
```

---

### 3️⃣ Iniciar o Servidor de Salas (`rooms.py`)

O servidor de salas gerencia a criação de salas e inicia as instâncias do jogo. Por padrão, ele roda na porta `4000`:

```bash
python3 rooms.py
```

Você deverá ver a mensagem:

```
Servidor de salas iniciado na porta 4000.
```

---

### 4️⃣ Configurar o Frontend

O frontend se conecta ao backend via WebSockets. É necessário ajustar a URL do WebSocket no arquivo `script.js`.

#### Jogando Localmente

* Abra `script.js` e localize a linha com o WebSocket.
* Substitua a URL pelo seu ambiente local:

```javascript
const WS_URL = `ws://localhost:4000`;
```

#### Testando o `app.py` isoladamente (opcional)

Se quiser rodar apenas o servidor principal de uma sala:

```bash
python3 app.py 8000
```

Nesse caso, ajuste o `WS_URL` no `script.js` para:

```javascript
const WS_URL = `ws://localhost:8000`;
```

---

### 5️⃣ Rodar o Frontend

Abra o arquivo `index.html` no navegador. Você pode simplesmente:

* Arrastar o arquivo para o navegador, ou
* Usar a opção "Abrir com" do navegador.

---

### 6️⃣ Conecte-se e Jogue!

* Na tela inicial, digite seu nome e a porta da sala ex.: (8765).
* Clique em **Entrar**.
* Divirta-se!

---

## 📌 Observação

Para jogar com amigos fora da sua rede local, é necessário expor o servidor para a internet. Uma alternativa simples é o uso do **ngrok**:

```bash
ngrok http 4000
```

E depois ajustar o `WS_URL` com o link gerado pelo ngrok.

---

## 📄 Licença

Projeto desenvolvido para fins de aprendizado e diversão. "Cards Against Humanity" é uma marca registrada de seus respectivos criadores. Este projeto não tem nenhuma afiliação oficial com eles.

---

## 🤝 Contribuições

Sinta-se à vontade para abrir issues, sugerir melhorias ou enviar pull requests!
