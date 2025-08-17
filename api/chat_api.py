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
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from conversation_history import ConversationHistory
from feedback_system import record_feedback
from semantic_search import generate_chatbot_response, search_products
from flask_cors import CORS

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()

# Permitir múltiples dominios
allowed_origins = [
    "https://masamadremonterrey.com",
    "https://www.masamadremonterrey.com",
    "file://",
    "https://account.masamadremonterrey.com/"
]

app = Flask(__name__)

# Configuración avanzada de CORS
# O para permitir todos los orígenes (solo para desarrollo)
# CORS(app)

CORS(app, resources={
    r"/api/*": {
        "origins": allowed_origins,
        "methods": ["GET", "POST", "OPTIONS", "PUT", "DELETE"],
        "allow_headers": [
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            "Accept",
            "Origin"
        ],
        "supports_credentials": True,
        "max_age": 3600  # Cache de preflight requests
    }
})

# Almacenamiento temporal de sesiones (en producción usa Redis o base de datos)
sessions = {}

# Intercepta todas las solicitudes OPTIONS
@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = make_response()
        # Ajusta estos valores según tu configuración de CORS
        response.headers.add("Access-Control-Allow-Origin",0) # O usa tu lista específica
        response.headers.add('Access-Control-Allow-Headers', "*")
        response.headers.add('Access-Control-Allow-Methods', "*")
        response.headers.add('Access-Control-Max-Age', "3600")
        return response

# Agrega headers CORS a todas las respuestas
@app.after_request
def after_request(response):
    # Asegúrate de que estos valores coincidan con tu configuración de CORS
    response.headers.add('Access-Control-Allow-Origin',0) # O usa tu lista específica
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,X-Requested-With,Accept,Origin')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response


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
        # Log detallado de la solicitud
        data = request.json
        logger.info(f"📩 Mensaje recibido: {json.dumps(data)}")
        
        user_id = data.get('user_id')
        message = data.get('message', '').strip()
        
        # Diagnóstico detallado
        if not user_id:
            logger.error("❌ Error: user_id no proporcionado en la solicitud")
            return jsonify({
                "status": "error",
                "message": "user_id es requerido"
            }), 400
        
        if user_id not in sessions:
            logger.error(f"❌ Error: Sesión no encontrada para user_id: {user_id}")
            # Para diagnóstico, listar todas las sesiones
            logger.info(f"📊 Sesiones activas: {list(sessions.keys())}")
            return jsonify({
                "status": "error",
                "message": "Sesión no válida. Por favor, inicia una nueva sesión."
            }), 400
        
        if not message:
            logger.error("❌ Error: Mensaje vacío recibido")
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
