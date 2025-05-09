// --- Configuration ---
const params = new URLSearchParams(window.location.search);

const nome = params.get("nome");
const sala = params.get("sala");



console.log(nome); // "adler"
console.log(sala); // "8000"

const WS_URL = `ws://192.168.11.4:` + sala; // Replace with server IP if not local


// --- DOM Elements ---
const statusMessage = document.getElementById('status-message');
const countdownDisplay = document.getElementById('countdown');
const scoresList = document.getElementById('scores-list');
const blackCardElement = document.getElementById('black-card');
const blackCardTextElement = document.getElementById('black-card-text');
const whiteCardsContainer = document.getElementById('white-cards-container');
const submitButton = document.getElementById('submit-button');
const voteButton = document.getElementById('vote-button');
const gameOverMessageElement = document.getElementById('game-over-message');

// --- Game State ---
let gameState = 'connecting'; // 'connecting', 'waiting_for_players', 'starting_countdown', 'waiting_for_black_card', 'choosing_white_card', 'waiting_for_submissions', 'voting', 'waiting_for_vote_result', 'round_result', 'game_over', 'error'
let myWhiteCards = ["resposta 1", "resposta 2", "resposta 3", "resposta 4", "outra resposta", "mais uma resposta"]; // Hardcoded for now, server doesn't manage hands
let currentBlackCardText = '';
let selectableSubmittedCardsTexts = []; // Cards received from server for voting
let selectedWhiteCardText = null;
let selectedSubmittedCardText = null;
let allScores = {}; // {player_address: score}
let roundWinnerCard = '';
let roundWinnerAddress = '';
let myAddress = ''; // We might need to figure this out or get it from the server

// >> ADICIONADO: Flag para rastrear se este cliente já submeteu na rodada atual
let hasSubmittedThisRound = false;

// --- WebSocket Connection ---
let websocket;

function connectWebSocket() {
    gameState = 'connecting';
    updateUI();
    statusMessage.textContent = 'Connecting...';
    countdownDisplay.style.display = 'none'; // Hide countdown initially

    websocket = new WebSocket(WS_URL);

    websocket.onopen = () => {
        console.log('WebSocket connected');
        // Server should send initial state upon connection
        // No need to send anything immediately unless server requires it
        sendMessage({ action: 'nome', nome: nome })
    };

    websocket.onmessage = (event) => {
        const message = JSON.parse(event.data);
        console.log('Message from server:', message);
        handleMessage(message);
    };

    websocket.onerror = (error) => {
        console.error('WebSocket error:', error);
        gameState = 'error';
        statusMessage.textContent = `Connection Error: ${error.message || 'Unknown Error'}`;
        updateUI();
    };

    websocket.onclose = (event) => {
        console.log('WebSocket closed:', event);
        gameState = 'error';
        statusMessage.textContent = `Connection Closed: ${event.code} - ${event.reason || 'Unknown Reason'}`;
        updateUI();
        window.location.href = window.location.href 
        // Optional: Attempt to reconnect after a delay
        // setTimeout(connectWebSocket, 5000);
    };

    
}

function sendMessage(message) {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify(message));
        // console.log('Sent message:', message); // Debug sending
    } else {
        console.error('WebSocket is not open. Cannot send message:', message);
        statusMessage.textContent = 'Error: Not connected to server.';
        gameState = 'error'; // Indicate connection issue
        updateUI();
    }
}

// --- Message Handling ---
function handleMessage(message) {
    const action = message.action;

    switch (action) {
        case 'game_state_update':
            gameState = message.state;
            statusMessage.textContent = message.message;
            console.log(`Game state changed to: ${gameState}`); // Debugging
            updateUI(); // Update UI based on new state
            break;

        case 'countdown':
            countdownDisplay.textContent = message.seconds;
            countdownDisplay.style.display = 'block'; // Show countdown
            statusMessage.textContent = `Game starting in ${message.seconds} seconds...`;
            break;

        case 'next_round':
             console.log('Received next_round. Requesting black card...'); // Debugging
             // Reset client-side round state
             selectedWhiteCardText = null;
             selectedSubmittedCardText = null;
             roundWinnerCard = '';
             roundWinnerAddress = '';
             // >> ADICIONADO/AJUSTADO: Resetar a flag de submissão para a nova rodada
             hasSubmittedThisRound = false;

             // The server will send black_card message after this request
             sendMessage({ action: 'get_black_card' });
             // gameState = 'waiting_for_black_card'; // Pode manter o estado anterior ou ir para um intermediário
             // Mantemos o estado anterior até receber black_card ou game_state_update
             statusMessage.textContent = 'Waiting for the Black Card...';
             updateUI(); // Update UI to clear previous round elements
             break;

        case 'black_card':
            currentBlackCardText = message.card;
            gameState = 'choosing_white_card'; // Transição para choosing state
            statusMessage.textContent = 'Choose a white card.';
            updateUI();
            break;

        case 'white_card_submitted':
            // >>> CORREÇÃO AQUI <<<
            // Não mude o gameState para 'waiting_for_submissions' aqui.
            // Apenas atualize a mensagem de status ou um contador visual.
            console.log(`${message.count} cards submitted so far.`); // Debugging
            // statusMessage.textContent = `Submitted: ${message.count}. Waiting for others...`; // Opcional: pode adicionar contador na mensagem
            // Não chame updateUI() aqui se ele for mudar drasticamente a interface
            // A transição visual para esperar acontece localmente no cliente que submeteu.
            // Os outros clientes continuam no estado 'choosing_white_card'.
            break;

        case 'start_vote':
            selectableSubmittedCardsTexts = message.cards;
            selectedSubmittedCardText = null; // Clear previous selection
            // >>> CORREÇÃO/AJUSTE AQUI <<<
            // Agora sim, transicione para o estado de votação para TODOS os clientes.
            gameState = 'voting';
            statusMessage.textContent = 'Vote for the best white card.';
            updateUI();
            break;

        case 'round_result':
            roundWinnerCard = message.winner_card;
            roundWinnerAddress = message.winner_address; // Server now sends winner address
            // Server should send scores_update after round_result
            gameState = 'round_result'; // Transition to showing result
            statusMessage.textContent = `Round Winner: '${roundWinnerCard}' by ${roundWinnerAddress}!`;
            console.log(`Round Result: '${roundWinnerCard}' by ${roundWinnerAddress}`); // Debugging
            updateUI();
            // O server envia 'next_round' ou 'game_over' após um pequeno delay
            break;

        case 'scores_update':
            allScores = message.scores;
            updateScoresDisplay(); // Update scores list
            break;

        case 'game_over':
            const winner = message.winner;
            gameState = 'game_over';
            statusMessage.textContent = `GAME OVER! Winner: ${winner}`;
            gameOverMessageElement.textContent = `GAME OVER! Winner: ${winner}`;
            console.log(`Game Over! Winner: ${winner}`); // Debugging
            updateUI();
            // scores_update should have the final scores
            break;

        case 'connection_closed':
             // ... (tratamento existente) ...
             break;

        case 'connection_error':
             // ... (tratamento existente) ...
             break;

        case 'network_send_error':
             // ... (tratamento existente) ...
             break;
        
        case 'nova_mao':
            myWhiteCards = message.cartas

        default:
            console.warn(`Unknown action received: ${action}`, message);
            break;
    }
}

// --- UI Update Logic ---
function updateUI() {
    // Hide/show elements based on the current game state
    // ... (mantém a lógica existente para esconder/mostrar elementos principais) ...
    blackCardElement.style.display = 'none';
    whiteCardsContainer.style.display = 'none';
    submitButton.style.display = 'none';
    voteButton.style.display = 'none';
    gameOverMessageElement.style.display = 'none';
    countdownDisplay.style.display = 'none';
    blackCardTextElement.textContent = ''; // Clear card text
    whiteCardsContainer.innerHTML = ''; // Clear white cards container content
    gameOverMessageElement.textContent = ''; // Clear game over message

    // Reinicia a capacidade de clicar nas cartas para a próxima exibição,
    // a lógica de estado controlará quando elas são exibidas e interativas.
    whiteCardsContainer.style.pointerEvents = 'auto';


    // Sempre display the status message
    // statusMessage.textContent is updated in handleMessage

    switch (gameState) {
        case 'connecting':
        case 'waiting_for_players':
        case 'error':
             // Only status message and scores are visible
             break;

        case 'starting_countdown':
             countdownDisplay.style.display = 'block';
             // statusMessage updated by 'countdown' messages
             break;

        case 'waiting_for_black_card':
             // Status message visible. Waiting for the server to send 'black_card'
             break;


        case 'choosing_white_card':
            blackCardElement.style.display = 'flex'; // Display black card
            blackCardTextElement.textContent = currentBlackCardText;
            whiteCardsContainer.style.display = 'flex'; // Display white cards container
            submitButton.style.display = 'block'; // Show submit button

            // >>> CORREÇÃO/AJUSTE AQUI <<<
            // O botão de submeter só é habilitado se uma carta for selecionada E o jogador ainda NÃO submeteu nesta rodada.
            submitButton.disabled = selectedWhiteCardText === null || hasSubmittedThisRound;

            displayWhiteCardsForChoosing(); // Desenha as cartas brancas para escolha
            break;

        // Removemos o estado 'waiting_for_submissions' como um estado GLOBAL do jogo.
        // Ele agora é mais um estado LOCAL da interface de UM cliente após ele ter submetido.
        // case 'waiting_for_submissions':
        //    // ... (esta lógica agora é tratada principalmente no handler do click do botão submit e na verificação hasSubmittedThisRound)
        //    break;


        case 'voting':
            blackCardElement.style.display = 'flex'; // Display black card
            blackCardTextElement.textContent = currentBlackCardText;
            whiteCardsContainer.style.display = 'flex'; // Display white cards container (para cartas de votação)
            voteButton.style.display = 'block'; // Show vote button

            // >>> AJUSTE AQUI <<<
            // O botão de votar só é habilitado se uma carta for selecionada para votar.
            // Não precisamos de uma flag 'hasVotedThisRound' aqui porque o estado muda para 'waiting_for_vote_result'
            // após votar, e o botão é desabilitado no handler do click.
            voteButton.disabled = selectedSubmittedCardText === null;

            displaySubmittedCardsForVoting(); // Desenha as cartas submetidas para votação
            break;

        case 'waiting_for_vote_result':
            blackCardElement.style.display = 'flex'; // Display black card
            blackCardTextElement.textContent = currentBlackCardText;
            // Status message indica que está esperando resultados
            // A interface pode mostrar as cartas votáveis (desabilitadas) ou apenas a carta preta.
            // displaySubmittedCardsForVoting(); // Opcional: manter cartas votáveis visíveis, mas desabilitar cliques
             whiteCardsContainer.innerHTML = ''; // Limpa as cartas votáveis enquanto espera resultado
             whiteCardsContainer.style.display = 'flex'; // Mantém o container visível para talvez uma mensagem
             whiteCardsContainer.textContent = "Waiting for other players to vote...";


            break;


        case 'round_result':
            blackCardElement.style.display = 'flex'; // Display black card
            blackCardTextElement.textContent = currentBlackCardText;
            // Mostra a carta vencedora
            if (roundWinnerCard) {
                 // Poderíamos adicionar um elemento específico para a carta vencedora aqui
                 whiteCardsContainer.style.display = 'flex'; // Usar o container para mostrar a carta vencedora
                 whiteCardsContainer.innerHTML = ''; // Limpa conteúdo anterior
                 const winnerCardElement = document.createElement('div');
                 winnerCardElement.classList.add('card', 'white-card'); // Usar estilo de carta branca
                 winnerCardElement.style.backgroundColor = 'lightgreen'; // Cor de vencedor
                 winnerCardElement.style.borderColor = 'darkgreen';
                 winnerCardElement.innerHTML = `<div class="card-content"><p>${roundWinnerCard}</p></div>`;
                 // Ajustar tamanho para ser mais proeminente que as cartas de escolha/votação
                 winnerCardElement.style.width = '200px';
                 winnerCardElement.style.height = '150px';
                 winnerCardElement.style.cursor = 'default'; // Não é clicável
                 winnerCardElement.style.pointerEvents = 'none'; // Desabilita qualquer evento de clique

                 whiteCardsContainer.appendChild(winnerCardElement);
            } else {
                 whiteCardsContainer.style.display = 'none'; // Oculta container se não houver vencedor (ex: sem votos)
            }

            break;

        case 'game_over':
            gameOverMessageElement.style.display = 'block'; // Show game over message
            blackCardElement.style.display = 'none';
            whiteCardsContainer.style.display = 'none';
            // Scores list is already visible
            break;

        default:
            // Fallback or error state display
            break;
    }
}

// --- Display Card Functions (No major changes needed here) ---
// displayWhiteCardsForChoosing() - Pequeno ajuste para verificar hasSubmittedThisRound antes de adicionar listeners/selecionar
// displaySubmittedCardsForVoting() - Sem grandes mudanças

function displayWhiteCardsForChoosing() {
    whiteCardsContainer.innerHTML = ''; // Clear previous cards
    myWhiteCards.forEach(cardText => {
        const cardElement = document.createElement('div');
        cardElement.classList.add('card', 'white-card');
        cardElement.innerHTML = `<div class="card-content"><p>${cardText}</p></div>`;
        cardElement.dataset.cardText = cardText; // Store text for easy access

        // >>> AJUSTE AQUI <<<
        // Adicionar listener de clique APENAS se o jogador ainda não submeteu
        if (!hasSubmittedThisRound) {
             cardElement.addEventListener('click', () => {
                 // Deselect previously selected card
                 if (selectedWhiteCardText) {
                     const prevSelected = whiteCardsContainer.querySelector(`.white-card.selected`);
                     if (prevSelected) {
                         prevSelected.classList.remove('selected');
                     }
                 }
                 // Select the clicked card
                 cardElement.classList.add('selected');
                 selectedWhiteCardText = cardText;
                 submitButton.disabled = false; // Enable submit button
                 console.log("Selected white card:", cardText); // Debugging
             });

             // Add selected class if it was previously selected (e.g., after a UI refresh)
             if (cardText === selectedWhiteCardText) {
                  cardElement.classList.add('selected');
             }
        } else {
            // Se já submeteu, tornar a carta não clicável
             cardElement.style.pointerEvents = 'none';
             cardElement.style.opacity = '0.7'; // Opcional: tornar a carta submetida um pouco transparente
             // Se esta for a carta que ele submeteu, destacá-la
             if (cardText === selectedWhiteCardText) { // selectedWhiteCardText mantém o valor da carta submetida localmente
                  cardElement.classList.add('selected'); // Mantém a seleção visual da carta submetida
                  cardElement.style.borderColor = 'yellow'; // Exemplo de destaque
                  cardElement.style.opacity = '1'; // Remover opacidade se for a selecionada
             }
        }


        whiteCardsContainer.appendChild(cardElement);
    });
    // Ensure button state matches selection when cards are displayed
    // Também verifica se já submeteu
    submitButton.disabled = selectedWhiteCardText === null || hasSubmittedThisRound;
}

function displaySubmittedCardsForVoting() {
    whiteCardsContainer.innerHTML = ''; // Clear previous cards
    // Certifica-se de que selectableSubmittedCardsTexts é um array
    const cardsToDisplay = Array.isArray(selectableSubmittedCardsTexts) ? selectableSubmittedCardsTexts : [];

    cardsToDisplay.forEach(cardText => {
        const cardElement = document.createElement('div');
        cardElement.classList.add('card', 'white-card'); // Use white-card class for styling
        cardElement.innerHTML = `<div class="card-content"><p>${cardText}</p></div>`; // Display the text
        cardElement.dataset.cardText = cardText; // Store text for easy access

        // Add click listener
        cardElement.addEventListener('click', () => {
             // Deselect previously selected card
            if (selectedSubmittedCardText) {
                const prevSelected = whiteCardsContainer.querySelector(`.white-card.selected`);
                if (prevSelected) {
                    prevSelected.classList.remove('selected');
                }
            }
            // Select the clicked card
            cardElement.classList.add('selected');
            selectedSubmittedCardText = cardText;
            voteButton.disabled = false; // Enable vote button
            console.log("Selected submitted card for voting:", cardText); // Debugging
        });

         // Add selected class if it was previously selected
        if (cardText === selectedSubmittedCardText) {
             cardElement.classList.add('selected');
        }

        whiteCardsContainer.appendChild(cardElement);
    });
     // Ensure button state matches selection when cards are displayed
    voteButton.disabled = selectedSubmittedCardText === null;
}



function updateScoresDisplay() {
    scoresList.innerHTML = ''; // Clear current list
    const sortedScores = Object.entries(allScores).sort(([, scoreA], [, scoreB]) => scoreB - scoreA);

    if (sortedScores.length === 0) {
        // scoresList.innerHTML = '<li>No scores yet.</li>';
        return; // Hide the scores area or show a message if list is empty
    }

    sortedScores.forEach(([address, score]) => {
        const listItem = document.createElement('li');
        // Simplify address for display if needed
        const displayAddress = address.split(':')[0]; // Use IP part
        listItem.textContent = `${displayAddress}: ${score}`;
        scoresList.appendChild(listItem);
    });
}


// --- Button Event Listeners ---
submitButton.addEventListener('click', () => {
    // >>> AJUSTE AQUI <<<
    // Verifica se o jogador ainda não submeteu antes de enviar
    if (!hasSubmittedThisRound && selectedWhiteCardText && gameState === 'choosing_white_card') {
        sendMessage({action: 'submit_white_card', card: selectedWhiteCardText});
        // Marca a flag LOCAL imediatamente após enviar
        hasSubmittedThisRound = true;
        // Desabilita o botão e as cartas localmente
        submitButton.disabled = true;
        whiteCardsContainer.querySelectorAll('.white-card').forEach(card => {
             card.style.pointerEvents = 'none'; // Desabilita clicks
             // Opcional: destacar a carta submetida mesmo depois de desabilitar
             if (card.dataset.cardText === selectedWhiteCardText) {
                 card.style.borderColor = 'yellow'; // Exemplo
                 card.style.opacity = '1';
             } else {
                 card.style.opacity = '0.7'; // Exemplo: escurecer as outras
             }
        });

        statusMessage.textContent = 'Card submitted. Waiting for others...'; // Update status
        // Não mude o gameState para 'waiting_for_submissions' aqui.
        // O server envia 'start_vote' quando for a hora de mudar de estado.
    }
});

voteButton.addEventListener('click', () => {
    if (selectedSubmittedCardText && gameState === 'voting') {
        sendMessage({ action: 'vote', card: selectedSubmittedCardText });
        voteButton.disabled = true; // Disable button after voting
        // Desabilita clicks nas cartas votáveis após votar
         whiteCardsContainer.querySelectorAll('.white-card').forEach(card => {
             card.style.pointerEvents = 'none'; // Desabilita clicks
             // Opcional: destacar a carta votada
             if (card.dataset.cardText === selectedSubmittedCardText) {
                  card.style.borderColor = 'green'; // Exemplo
                  card.style.opacity = '1';
             } else {
                  card.style.opacity = '0.7'; // Exemplo: escurecer as outras
             }
         });

         // >>> AJUSTE AQUI <<<
         // Muda o estado local para waiting_for_vote_result para indicar que este cliente já votou
         // e está esperando o resultado do server.
         gameState = 'waiting_for_vote_result';
         statusMessage.textContent = 'Vote submitted. Waiting for results...'; // Update status
         updateUI(); // Atualiza a interface para refletir o estado de espera (pode limpar cartas, etc.)

    }
});

// --- Initialization ---
connectWebSocket(); // Start the connection when the page loads
