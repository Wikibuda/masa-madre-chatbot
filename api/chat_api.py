#!/usr/bin/env python3
"""
API para el Chatbot de Masa Madre Monterrey
- Proporciona endpoints para el widget de chat
"""

import sys
import os
# Añadir el directorio lib al PYTHONPATH
sys.path.append(os.path.join(os.path.dirname(__file__), '../lib'))

import json
import logging
import flask_cors
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from conversation_history import ConversationHistory
from feedback_system import record_feedback
from semantic_search import generate_chatbot_response, search_products
from flask_cors import CORS


app = Flask(__name__)
CORS(app)  # Permitir todos los orígenes

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)

# Almacenamiento temporal de sesiones (en producción usa Redis o base de datos)
sessions = {}

@app.route('/api/chat/init', methods=['POST'])
def init_chat():
    """Inicializa una nueva sesión de chat"""
    try:
        data = request.json
        user_id = data.get('user_id', f"user_{int(datetime.now().timestamp())}")
        
        # Crear historial de conversación
        conversation_history = ConversationHistory(user_id=user_id)
        sessions[user_id] = conversation_history
        
        logger.info(f"✅ Sesión iniciada para el usuario: {user_id}")
        return jsonify({
            "status": "success",
            "user_id": user_id,
            "message": "Sesión de chat iniciada",
            "welcome_message": "¡Hola! Soy tu asistente de panadería especializado en masa madre. ¿En qué puedo ayudarte hoy?"
        })
    
    except Exception as e:
        logger.error(f"❌ Error al iniciar sesión: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Error al iniciar la sesión de chat"
        }), 500

@app.route('/api/chat/message', methods=['POST'])
def handle_message():
    """Procesa un mensaje del usuario"""
    try:
        data = request.json
        user_id = data.get('user_id')
        message = data.get('message', '').strip()
        
        if not user_id or user_id not in sessions:
            return jsonify({
                "status": "error",
                "message": "Sesión no válida. Por favor, inicia una nueva sesión."
            }), 400
        
        if not message:
            return jsonify({
                "status": "error",
                "message": "El mensaje no puede estar vacío"
            }), 400
        
        # Obtener historial de conversación
        conversation_history = sessions[user_id]
        
        # Generar respuesta
        chatbot_response = generate_chatbot_response(
            query=message,
            user_id=user_id,
            conversation_history=conversation_history
        )
        
        # Preparar respuesta para el frontend
        response_data = {
            "status": "success",
            "response": chatbot_response['response'],
            "sources": chatbot_response['sources'],
            "user_id": user_id
        }
        
        logger.info(f"✅ Mensaje procesado para el usuario {user_id}")
        return jsonify(response_data)
    
    except Exception as e:
        logger.error(f"❌ Error al procesar mensaje: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Error al procesar tu mensaje"
        }), 500

@app.route('/api/chat/feedback', methods=['POST'])
def handle_feedback():
    """Registra retroalimentación del usuario"""
    try:
        data = request.json
        user_id = data.get('user_id')
        rating = data.get('rating')
        comment = data.get('comment', '')
        
        if not user_id or user_id not in sessions:
            return jsonify({
                "status": "error",
                "message": "Sesión no válida"
            }), 400
        
        if not isinstance(rating, int) or not (1 <= rating <= 5):
            return jsonify({
                "status": "error",
                "message": "Calificación inválida. Debe ser un número entre 1 y 5."
            }), 400
        
        # Obtener la última consulta y respuesta
        conversation_history = sessions[user_id]
        full_history = conversation_history.get_full_history()
        
        if not full_history:
            return jsonify({
                "status": "error",
                "message": "No hay historial de conversación para calificar"
            }), 400
        
        last_exchange = full_history[-1]
        
        # Registrar retroalimentación
        record_feedback(
            query=last_exchange['query'],
            response=last_exchange['response'],
            provider="claude",
            rating=rating,
            user_comment=comment,
            session_id=user_id
        )
        
        logger.info(f"✅ Retroalimentación registrada para el usuario {user_id}: {rating}/5")
        return jsonify({
            "status": "success",
            "message": "¡Gracias por tu retroalimentación!"
        })
    
    except Exception as e:
        logger.error(f"❌ Error al registrar retroalimentación: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Error al registrar tu retroalimentación"
        }), 500

@app.route('/api/chat/support', methods=['POST'])
def request_support():
    """Solicita soporte humano"""
    try:
        data = request.json
        user_id = data.get('user_id')
        contact_info = data.get('contact_info', '')
        
        if not user_id or user_id not in sessions:
            return jsonify({
                "status": "error",
                "message": "Sesión no válida"
            }), 400
        
        if not contact_info:
            return jsonify({
                "status": "error",
                "message": "Se requiere información de contacto"
            }), 400
        
        # Obtener historial completo
        conversation_history = sessions[user_id]
        full_history = conversation_history.get_full_history()
        
        if not full_history:
            return jsonify({
                "status": "error",
                "message": "No hay historial de conversación"
            }), 400
        
        # Crear ticket de soporte
        from support_system import create_support_ticket
        create_support_ticket(
            query=full_history[-1]['query'],
            response=full_history[-1]['response'],
            conversation_history=full_history,
            contact_info=contact_info,
            priority="media",
            reason="Solicitud de soporte humano desde el widget de chat"
        )
        
        logger.info(f"✅ Ticket de soporte creado para el usuario {user_id}")
        return jsonify({
            "status": "success",
            "message": "Ticket de soporte creado. Un representante se contactará contigo pronto."
        })
    
    except Exception as e:
        logger.error(f"❌ Error al crear ticket de soporte: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Error al crear tu ticket de soporte"
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Endpoint para verificar el estado del servicio"""
    return jsonify({
        "status": "healthy",
        "service": "masa-madre-chatbot-api",
        "timestamp": datetime.now().isoformat()
    })

if __name__ == "__main__":
    port = int(os.getenv('PORT', 5000))
    logger.info(f"🚀 Iniciando API del chatbot en el puerto {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
