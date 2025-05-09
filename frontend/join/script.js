const nameEntry = document.getElementById("nameEntry");
const roomEntry = document.getElementById("roomEntry");

function clicarNome() {
    let sala = roomEntry.value;
    let nome = nameEntry.value;

    const socket = new WebSocket('ws://localhost:4000');

    socket.onopen = function() {
        const msg = {
            type: "join",
            nome: nome,
            sala: sala
        };
        socket.send(JSON.stringify(msg));
    };

    socket.onerror = function(event) {
        console.error("Erro na conexão:", event);
    };

    socket.onmessage = function(event) {
        console.log("Mensagem recebida:", event.data);
    };

    socket.onclose = function(event) {
        console.warn("Conexão fechada:", event);
    };

    const baseUrl = `${window.location.protocol}//${window.location.host}`;
    const novaUrl = `${baseUrl}/frontend/index.html?nome=${encodeURIComponent(nome)}&sala=${encodeURIComponent(sala)}`;

    setTimeout(window.location.href = novaUrl, 1000)
}

function getRandomInt(min, max) {
    min = Math.ceil(min);
    max = Math.floor(max);
    return Math.floor(Math.random() * (max - min + 1)) + min;
}

function criarSala() {
    let sala = getRandomInt(1000,34600)
    let nome = nameEntry.value;

    const socket = new WebSocket('ws://localhost:4000');

    socket.onopen = function() {
        const msg = {
            type: "join",
            nome: nome,
            sala: sala
        };
        socket.send(JSON.stringify(msg));
    };

    socket.onerror = function(event) {
        console.error("Erro na conexão:", event);
    };

    socket.onmessage = function(event) {
        console.log("Mensagem recebida:", event.data);
    };

    socket.onclose = function(event) {
        console.warn("Conexão fechada:", event);
    };

    const baseUrl = `${window.location.protocol}//${window.location.host}`;
    const novaUrl = `${baseUrl}/frontend/index.html?nome=${encodeURIComponent(nome)}&sala=${encodeURIComponent(sala)}`;

    setTimeout(window.location.href = novaUrl, 1000)
}

// Adiciona o container para os elementos do formulário
document.addEventListener('DOMContentLoaded', function() {
    // Seleciona todos os elementos relevantes
    const labels = document.querySelectorAll('label');
    const inputs = document.querySelectorAll('input');
    const button = document.querySelector('button');
    
    // Cria o container
    // const formContainer = document.createElement('div');
    formContainer.className = 'form-container';
    
    // Move os elementos para dentro do container
    labels.forEach(label => {
      const input = document.getElementById(label.getAttribute('for'));
      const br = label.nextElementSibling;
      
      formContainer.appendChild(label);
      formContainer.appendChild(input);
      if (br && br.tagName === 'BR') {
        br.remove();
      }
    });
    
    formContainer.appendChild(button);
    
    // Insere o container após o título
    const h2 = document.querySelector('h2');
    h2.after(formContainer);
  });