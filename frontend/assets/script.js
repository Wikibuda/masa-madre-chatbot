<script>
  document.addEventListener('DOMContentLoaded', function() {
    const chatbot = {
      header: document.getElementById('chatbot-header'),
      body: document.getElementById('chatbot-body'),
      messages: document.getElementById('chatbot-messages'),
      input: document.getElementById('chatbot-input'),
      sendButton: document.getElementById('chatbot-send'),
      footer: document.getElementById('chatbot-footer'),
      feedbackButtons: document.querySelectorAll('.feedback-btn'),
      
      // Estado
      userId: null,
      isChatOpen: false,
      isProcessing: false,
      lastResponse: null,
      
      // Inicializar
      init: function() {
        this.setupEventListeners();
        this.loadUserId();
        this.checkAPIStatus();
      },
      
      // Configurar listeners
      setupEventListeners: function() {
        // Toggle chat
        this.header.addEventListener('click', () => {
          this.toggleChat();
        });
        
        // Enviar mensaje
        this.sendButton.addEventListener('click', () => {
          this.sendMessage();
        });
        
        this.input.addEventListener('keypress', (e) => {
          if (e.key === 'Enter') {
            this.sendMessage();
          }
        });
        
        // Feedback
        document.querySelectorAll('.feedback-btn').forEach(btn => {
          btn.addEventListener('click', (e) => {
            const rating = parseInt(e.target.getAttribute('data-rating'));
            this.submitFeedback(rating);
          });
        });
      },
      
      // Cargar o crear user ID
      loadUserId: function() {
        let userId = localStorage.getItem('masaMadreChatUserId');
        if (!userId) {
          userId = 'web_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
          localStorage.setItem('masaMadreChatUserId', userId);
        }
        this.userId = userId;
      },
      
      // Verificar estado de la API
      checkAPIStatus: function() {
        fetch('/api/health')
          .then(response => response.json())
          .then(data => {
            if (data.status === 'healthy') {
              document.getElementById('chatbot-status').style.backgroundColor = '#4CAF50';
            } else {
              document.getElementById('chatbot-status').style.backgroundColor = '#ff9800';
            }
          })
          .catch(() => {
            document.getElementById('chatbot-status').style.backgroundColor = '#f44336';
          });
      },
      
      // Toggle chat
      toggleChat: function() {
        this.isChatOpen = !this.isChatOpen;
        this.body.style.display = this.isChatOpen ? 'flex' : 'none';
        
        if (this.isChatOpen && !this.userId) {
          this.initializeChatSession();
        }
      },
      
      // Inicializar sesión de chat
      initializeChatSession: function() {
        fetch('/api/chat/init', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ user_id: this.userId })
        })
        .then(response => response.json())
        .then(data => {
          if (data.status === 'success') {
            this.addMessage(data.welcome_message, 'bot');
          } else {
            this.addMessage('Lo siento, estoy teniendo problemas para iniciar la sesión de chat. Por favor, inténtalo de nuevo más tarde.', 'bot');
          }
        })
        .catch(error => {
          console.error('Error initializing chat:', error);
          this.addMessage('No se pudo conectar con el servicio de chat. Por favor, inténtalo de nuevo más tarde.', 'bot');
        });
      },
      
      // Enviar mensaje
      sendMessage: function() {
        const message = this.input.value.trim();
        if (!message || this.isProcessing) return;
        
        // Mostrar mensaje del usuario
        this.addMessage(message, 'user');
        this.input.value = '';
        
        // Mostrar loading
        const loadingId = 'loading_' + Date.now();
        this.addLoadingIndicator(loadingId);
        
        this.isProcessing = true;
        
        // Enviar al backend
        fetch('/api/chat/message', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            user_id: this.userId,
            message: message
          })
        })
        .then(response => {
          // Remover loading
          this.removeElement(loadingId);
          
          if (!response.ok) {
            throw new Error('Network response was not ok');
          }
          return response.json();
        })
        .then(data => {
          if (data.status === 'success') {
            // Guardar última respuesta para retroalimentación
            this.lastResponse = {
              query: message,
              response: data.response
            };
            
            // Mostrar respuesta
            this.addMessage(data.response, 'bot');
            
            // Mostrar fuentes si existen
            if (data.sources && data.sources.length > 0) {
              let sourcesHTML = '<div class="product-suggestion" style="margin-top: 8px; padding: 8px; border-radius: 8px; background-color: #f9f9f9;">';
              sourcesHTML += '<strong>Productos relacionados:</strong><br>';
              
              data.sources.slice(0, 2).forEach(source => {
                sourcesHTML += `<div class="product-title">${source.title}</div>`;
                sourcesHTML += `<div class="product-price">${source.price} - ${source.availability}</div>`;
                if (source.url) {
                  sourcesHTML += `<a href="${source.url}" target="_blank" style="color: #8B4513; text-decoration: none; font-size: 0.9em;">Ver producto</a>`;
                }
                sourcesHTML += '<br>';
              });
              
              sourcesHTML += '</div>';
              
              const sourcesDiv = document.createElement('div');
              sourcesDiv.className = 'message bot';
              sourcesDiv.innerHTML = sourcesHTML;
              this.messages.appendChild(sourcesDiv);
              this.scrollToBottom();
            }
            
            // Mostrar footer de retroalimentación
            this.footer.style.display = 'block';
          } else {
            this.addMessage('Lo siento, estoy teniendo problemas para procesar tu consulta. Por favor, inténtalo de nuevo más tarde.', 'bot');
          }
        })
        .catch(error => {
          console.error('Error sending message:', error);
          // Remover loading
          this.removeElement(loadingId);
          this.addMessage('Hubo un error al procesar tu mensaje. Por favor, inténtalo de nuevo.', 'bot');
        })
        .finally(() => {
          this.isProcessing = false;
        });
      },
      
      // Agregar mensaje
      addMessage: function(text, sender) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}`;
        messageDiv.textContent = text;
        this.messages.appendChild(messageDiv);
        this.scrollToBottom();
      },
      
      // Agregar indicador de loading
      addLoadingIndicator: function(id) {
        const loadingDiv = document.createElement('div');
        loadingDiv.id = id;
        loadingDiv.className = 'message bot';
        loadingDiv.style.opacity = '0.7';
        loadingDiv.innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div> Procesando tu consulta...';
        this.messages.appendChild(loadingDiv);
        this.scrollToBottom();
      },
      
      // Remover elemento
      removeElement: function(id) {
        const element = document.getElementById(id);
        if (element) {
          element.remove();
        }
      },
      
      // Desplazar al fondo
      scrollToBottom: function() {
        this.messages.scrollTop = this.messages.scrollHeight;
      },
      
      // Enviar retroalimentación
      submitFeedback: function(rating) {
        if (!this.lastResponse) return;
        
        fetch('/api/chat/feedback', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            user_id: this.userId,
            rating: rating,
            comment: ''
          })
        })
        .then(response => response.json())
        .then(data => {
          if (data.status === 'success') {
            this.addMessage('¡Gracias por tu retroalimentación!', 'bot');
            this.footer.style.display = 'none';
          }
        })
        .catch(error => {
          console.error('Error submitting feedback:', error);
        });
      },
      
      // Solicitar soporte humano
      requestSupport: function(contactInfo) {
        fetch('/api/chat/support', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            user_id: this.userId,
            contact_info: contactInfo
          })
        })
        .then(response => response.json())
        .then(data => {
          if (data.status === 'success') {
            this.addMessage('✅ Ticket de soporte creado. Un representante se contactará contigo pronto.', 'bot');
          }
        })
        .catch(error => {
          console.error('Error requesting support:', error);
          this.addMessage('Hubo un problema al crear tu ticket de soporte. Por favor, contacta directamente a soporte@masamadremonterrey.com', 'bot');
        });
      }
    };
    
    // Inicializar el chatbot
    chatbot.init();
  });
</script>
