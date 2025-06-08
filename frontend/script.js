// --- Configuration ---
const params = new URLSearchParams(window.location.search)

const nome = params.get("nome")
const sala = params.get("sala")

console.log(nome) // "adler"
console.log(sala) // "8000"

const WS_URL = `ws://127.0.0.1:` + sala // Replace with server IP if not local

// --- DOM Elements ---
const statusMessage = document.getElementById("status-message")
const countdownDisplay = document.getElementById("countdown")
const scoresList = document.getElementById("scores-list")
const blackCardElement = document.getElementById("black-card")
const blackCardTextElement = document.getElementById("black-card-text")
const whiteCardsContainer = document.getElementById("white-cards-container")
const submitButton = document.getElementById("submit-button")
const voteButton = document.getElementById("vote-button")
const gameOverMessageElement = document.getElementById("game-over-message")

// Novos elementos para o showcase
const showcaseOverlay = document.getElementById("card-showcase-overlay")
const showcaseCard = document.getElementById("showcase-card")
const showcaseCardText = document.getElementById("showcase-card-text")
const currentCardNumber = document.getElementById("current-card-number")
const totalCardsNumber = document.getElementById("total-cards-number")
const prevCardBtn = document.getElementById("prev-card-btn")
const nextCardBtn = document.getElementById("next-card-btn")
const startVotingBtn = document.getElementById("start-voting-btn")
const progressBar = document.getElementById("progress-bar")

// --- Game State ---
let gameState = "connecting"
let myWhiteCards = ["resposta 1", "resposta 2", "resposta 3", "resposta 4", "outra resposta", "mais uma resposta"]
let currentBlackCardText = ""
let selectableSubmittedCardsTexts = []
let selectedWhiteCardText = null
let selectedSubmittedCardText = null
let allScores = {}
let roundWinnerCard = ""
let roundWinnerAddress = ""
const myAddress = ""
let hasSubmittedThisRound = false

// Variáveis para o showcase
let showcaseCards = []
let currentShowcaseIndex = 0
let isShowcaseActive = false
const showcaseTimer = null
let timerCountdown = null

// Declaring jogadorNome variable
let jogadorNome

// --- WebSocket Connection ---
let websocket

function connectWebSocket() {
  gameState = "connecting"
  updateUI()
  statusMessage.textContent = "Connecting..."
  countdownDisplay.style.display = "none"

  websocket = new WebSocket(WS_URL)

  websocket.onopen = () => {
    console.log("WebSocket connected")
    jogadorNome = nome
    setTimeout(() => sendMessage({ action: "nome", nome: jogadorNome }), 1000)
  }

  websocket.onmessage = (event) => {
    const message = JSON.parse(event.data)
    console.log("Message from server:", message)
    handleMessage(message)
  }

  websocket.onerror = (error) => {
    console.error("WebSocket error:", error)
    gameState = "error"
    statusMessage.textContent = `Connection Error: ${error.message || "Unknown Error"}`
    updateUI()
  }

  websocket.onclose = (event) => {
    console.log("WebSocket closed:", event)
    gameState = "error"
    statusMessage.textContent = `Connection Closed: ${event.code} - ${event.reason || "Unknown Reason"}`
    updateUI()
    window.location.href = window.location.href
  }
}

function sendMessage(message) {
  if (websocket && websocket.readyState === WebSocket.OPEN) {
    websocket.send(JSON.stringify(message))
  } else {
    console.error("WebSocket is not open. Cannot send message:", message)
    statusMessage.textContent = "Error: Not connected to server."
    gameState = "error"
    updateUI()
  }
}

// --- Showcase Functions ---
function startCardShowcase(cards) {
  showcaseCards = [...cards]
  currentShowcaseIndex = 0
  isShowcaseActive = true

  // Configurar elementos do showcase
  totalCardsNumber.textContent = showcaseCards.length

  // Mostrar carta preta
  const showcaseBlackCard = document.getElementById("showcase-black-card")
  const showcaseBlackCardText = document.getElementById("showcase-black-card-text")
  showcaseBlackCardText.textContent = currentBlackCardText

  updateShowcaseCard()
  updateProgressBar()

  // Mostrar overlay
  showcaseOverlay.style.display = "flex"

  // Iniciar timer automático
  startAutoTimer()
}

function updateShowcaseCard() {
  if (showcaseCards.length === 0) return

  const currentCard = showcaseCards[currentShowcaseIndex]
  showcaseCardText.textContent = currentCard
  currentCardNumber.textContent = currentShowcaseIndex + 1

  // Remover classes de animação anteriores
  showcaseCard.classList.remove("slide-in", "slide-out")

  // Forçar reflow para garantir que a animação seja aplicada
  showcaseCard.offsetHeight

  // Adicionar animação de entrada
  showcaseCard.classList.add("slide-in")
  setTimeout(() => {
    showcaseCard.classList.remove("slide-in")
  }, 500)
}

function updateProgressBar() {
  const progress = ((currentShowcaseIndex + 1) / showcaseCards.length) * 100
  progressBar.style.width = `${progress}%`
}

function startAutoTimer() {
  let timeLeft = 5
  const timerCountdownElement = document.getElementById("timer-countdown")
  const timerBar = document.getElementById("timer-bar")

  // Resetar animação da barra de timer
  timerBar.style.animation = "none"
  timerBar.offsetHeight // Forçar reflow
  timerBar.style.animation = "timerCountdown 5s linear"

  // Atualizar contador
  timerCountdownElement.textContent = timeLeft

  timerCountdown = setInterval(() => {
    timeLeft--
    timerCountdownElement.textContent = timeLeft

    if (timeLeft <= 0) {
      clearInterval(timerCountdown)
      navigateToNextCard()
    }
  }, 1000)
}

function navigateToNextCard() {
  // Limpar timers
  if (timerCountdown) {
    clearInterval(timerCountdown)
    timerCountdown = null
  }

  // Animação de saída
  showcaseCard.classList.add("slide-out")

  setTimeout(() => {
    currentShowcaseIndex++

    if (currentShowcaseIndex >= showcaseCards.length) {
      // Acabaram as cartas, iniciar votação
      endShowcase()
      return
    }

    // Mostrar próxima carta
    updateShowcaseCard()
    updateProgressBar()

    // Reiniciar timer
    startAutoTimer()
  }, 500)
}

function endShowcase() {
  isShowcaseActive = false

  // Limpar timers
  if (timerCountdown) {
    clearInterval(timerCountdown)
    timerCountdown = null
  }

  // Esconder overlay
  showcaseOverlay.style.display = "none"

  // Iniciar votação normal
  gameState = "voting"
  statusMessage.textContent = "Vote for the best white card."
  updateUI()
}

// --- Message Handling ---
function handleMessage(message) {
  const action = message.action

  switch (action) {
    case "game_state_update":
      gameState = message.state
      statusMessage.textContent = message.message
      console.log(`Game state changed to: ${gameState}`)
      updateUI()
      break

    case "countdown":
      countdownDisplay.textContent = message.seconds
      countdownDisplay.style.display = "block"
      statusMessage.textContent = `Game starting in ${message.seconds} seconds...`
      break

    case "next_round":
      console.log("Received next_round. Requesting black card...")
      selectedWhiteCardText = null
      selectedSubmittedCardText = null
      roundWinnerCard = ""
      roundWinnerAddress = ""
      hasSubmittedThisRound = false

      sendMessage({ action: "get_black_card" })
      statusMessage.textContent = "Waiting for the Black Card..."
      updateUI()
      break

    case "black_card":
      currentBlackCardText = message.card
      gameState = "choosing_white_card"
      statusMessage.textContent = "Choose a white card."
      updateUI()
      break

    case "white_card_submitted":
      console.log(`${message.count} cards submitted so far.`)
      break

    case "start_vote":
      selectableSubmittedCardsTexts = message.cards
      selectedSubmittedCardText = null

      // Iniciar showcase em vez de ir direto para votação
      if (selectableSubmittedCardsTexts.length > 0) {
        statusMessage.textContent = "Reviewing submitted cards..."
        startCardShowcase(selectableSubmittedCardsTexts)
      } else {
        // Fallback se não houver cartas
        gameState = "voting"
        statusMessage.textContent = "Vote for the best white card."
        updateUI()
      }
      break

    case "round_result":
      roundWinnerCard = message.winner_card
      roundWinnerAddress = message.winner_address
      gameState = "round_result"
      statusMessage.textContent = `Round Winner: '${roundWinnerCard}' by ${roundWinnerAddress}!`
      console.log(`Round Result: '${roundWinnerCard}' by ${roundWinnerAddress}`)
      updateUI()
      break

    case "scores_update":
      allScores = message.scores
      updateScoresDisplay()
      break

    case "game_over":
      const winner = message.winner
      gameState = "game_over"
      statusMessage.textContent = `GAME OVER! Winner: ${winner}`
      gameOverMessageElement.textContent = `GAME OVER! Winner: ${winner}`
      console.log(`Game Over! Winner: ${winner}`)
      updateUI()
      break

    case "nova_mao":
      myWhiteCards = message.cartas
      break

    case "get_nome":
      sendMessage({ action: "nome", nome: jogadorNome })
      break

    default:
      console.warn(`Unknown action received: ${action}`, message)
      break
  }
}

// --- UI Update Logic ---
function updateUI() {
  blackCardElement.style.display = "none"
  whiteCardsContainer.style.display = "none"
  submitButton.style.display = "none"
  voteButton.style.display = "none"
  gameOverMessageElement.style.display = "none"
  countdownDisplay.style.display = "none"
  blackCardTextElement.textContent = ""
  whiteCardsContainer.innerHTML = ""
  gameOverMessageElement.textContent = ""

  whiteCardsContainer.style.pointerEvents = "auto"

  switch (gameState) {
    case "connecting":
    case "waiting_for_players":
    case "error":
      break

    case "starting_countdown":
      countdownDisplay.style.display = "block"
      break

    case "waiting_for_black_card":
      break

    case "choosing_white_card":
      blackCardElement.style.display = "flex"
      blackCardTextElement.textContent = currentBlackCardText
      whiteCardsContainer.style.display = "flex"
      submitButton.style.display = "block"

      submitButton.disabled = selectedWhiteCardText === null || hasSubmittedThisRound

      displayWhiteCardsForChoosing()
      break

    case "voting":
      blackCardElement.style.display = "flex"
      blackCardTextElement.textContent = currentBlackCardText
      whiteCardsContainer.style.display = "flex"
      voteButton.style.display = "block"

      voteButton.disabled = selectedSubmittedCardText === null

      displaySubmittedCardsForVoting()
      break

    case "waiting_for_vote_result":
      blackCardElement.style.display = "flex"
      blackCardTextElement.textContent = currentBlackCardText
      whiteCardsContainer.innerHTML = ""
      whiteCardsContainer.style.display = "flex"
      whiteCardsContainer.textContent = "Waiting for other players to vote..."
      break

    case "round_result":
      blackCardElement.style.display = "flex"
      blackCardTextElement.textContent = currentBlackCardText
      if (roundWinnerCard) {
        whiteCardsContainer.style.display = "flex"
        whiteCardsContainer.innerHTML = ""
        const winnerCardElement = document.createElement("div")
        winnerCardElement.classList.add("card", "white-card")
        winnerCardElement.style.backgroundColor = "lightgreen"
        winnerCardElement.style.borderColor = "darkgreen"
        winnerCardElement.innerHTML = `<div class="card-content"><p>${roundWinnerCard}</p></div>`
        winnerCardElement.style.width = "200px"
        winnerCardElement.style.height = "150px"
        winnerCardElement.style.cursor = "default"
        winnerCardElement.style.pointerEvents = "none"

        whiteCardsContainer.appendChild(winnerCardElement)
      } else {
        whiteCardsContainer.style.display = "none"
      }
      break

    case "game_over":
      gameOverMessageElement.style.display = "block"
      blackCardElement.style.display = "none"
      whiteCardsContainer.style.display = "none"
      break

    default:
      break
  }
}

// --- Display Card Functions ---
function displayWhiteCardsForChoosing() {
  whiteCardsContainer.innerHTML = ""
  myWhiteCards.forEach((cardText) => {
    const cardElement = document.createElement("div")
    cardElement.classList.add("card", "white-card")
    cardElement.innerHTML = `<div class="card-content"><p>${cardText}</p></div>`
    cardElement.dataset.cardText = cardText

    if (!hasSubmittedThisRound) {
      cardElement.addEventListener("click", () => {
        if (selectedWhiteCardText) {
          const prevSelected = whiteCardsContainer.querySelector(`.white-card.selected`)
          if (prevSelected) {
            prevSelected.classList.remove("selected")
          }
        }
        cardElement.classList.add("selected")
        selectedWhiteCardText = cardText
        submitButton.disabled = false
        console.log("Selected white card:", cardText)
      })

      if (cardText === selectedWhiteCardText) {
        cardElement.classList.add("selected")
      }
    } else {
      cardElement.style.pointerEvents = "none"
      cardElement.style.opacity = "0.7"
      if (cardText === selectedWhiteCardText) {
        cardElement.classList.add("selected")
        cardElement.style.borderColor = "yellow"
        cardElement.style.opacity = "1"
      } else {
        cardElement.style.opacity = "0.7"
      }
    }

    whiteCardsContainer.appendChild(cardElement)
  })
  submitButton.disabled = selectedWhiteCardText === null || hasSubmittedThisRound
}

function displaySubmittedCardsForVoting() {
  whiteCardsContainer.innerHTML = ""
  const cardsToDisplay = Array.isArray(selectableSubmittedCardsTexts) ? selectableSubmittedCardsTexts : []

  cardsToDisplay.forEach((cardText) => {
    const cardElement = document.createElement("div")
    cardElement.classList.add("card", "white-card")
    cardElement.innerHTML = `<div class="card-content"><p>${cardText}</p></div>`
    cardElement.dataset.cardText = cardText

    cardElement.addEventListener("click", () => {
      if (selectedSubmittedCardText) {
        const prevSelected = whiteCardsContainer.querySelector(`.white-card.selected`)
        if (prevSelected) {
          prevSelected.classList.remove("selected")
        }
      }
      cardElement.classList.add("selected")
      selectedSubmittedCardText = cardText
      voteButton.disabled = false
      console.log("Selected submitted card for voting:", cardText)
    })

    if (cardText === selectedSubmittedCardText) {
      cardElement.classList.add("selected")
    }

    whiteCardsContainer.appendChild(cardElement)
  })
  voteButton.disabled = selectedSubmittedCardText === null
}

function updateScoresDisplay() {
  scoresList.innerHTML = ""
  const sortedScores = Object.entries(allScores).sort(([, scoreA], [, scoreB]) => scoreB - scoreA)

  if (sortedScores.length === 0) {
    return
  }

  sortedScores.forEach(([address, score]) => {
    const listItem = document.createElement("li")
    const displayAddress = address.split(":")[0]
    listItem.textContent = `${displayAddress}: ${score}`
    scoresList.appendChild(listItem)
  })
}

// --- Button Event Listeners ---
submitButton.addEventListener("click", () => {
  if (!hasSubmittedThisRound && selectedWhiteCardText && gameState === "choosing_white_card") {
    sendMessage({ action: "submit_white_card", card: selectedWhiteCardText })
    hasSubmittedThisRound = true
    submitButton.disabled = true
    whiteCardsContainer.querySelectorAll(".white-card").forEach((card) => {
      card.style.pointerEvents = "none"
      if (card.dataset.cardText === selectedWhiteCardText) {
        card.style.borderColor = "yellow"
        card.style.opacity = "1"
      } else {
        card.style.opacity = "0.7"
      }
    })

    statusMessage.textContent = "Card submitted. Waiting for others..."
  }
})

voteButton.addEventListener("click", () => {
  if (selectedSubmittedCardText && gameState === "voting") {
    sendMessage({ action: "vote", card: selectedSubmittedCardText })
    voteButton.disabled = true
    whiteCardsContainer.querySelectorAll(".white-card").forEach((card) => {
      card.style.pointerEvents = "none"
      if (card.dataset.cardText === selectedSubmittedCardText) {
        card.style.borderColor = "green"
        card.style.opacity = "1"
      } else {
        card.style.opacity = "0.7"
      }
    })

    gameState = "waiting_for_vote_result"
    statusMessage.textContent = "Vote submitted. Waiting for results..."
    updateUI()
  }
})

// --- Initialization ---
connectWebSocket()
