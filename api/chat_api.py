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
from flask import Flask, request, jsonify, make_response
from dotenv import load_dotenv
from conversation_history import ConversationHistory
from feedback_system import record_feedback
# Importar la función de generación de respuesta
# Asumo que está en semantic_search.py basado en tu código original
from semantic_search import generate_chatbot_response, search_products
from flask_cors import CORS

# --- CONFIGURACIÓN DE LOGGING ---
# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s' # Añadido %(name)s para mejor identificación
)
logger = logging.getLogger(__name__) # Logger específico para este módulo

# --- CARGA DE VARIABLES DE ENTORNO ---
# Cargar variables de entorno
load_dotenv()

# --- CONFIGURACIÓN DE CORS ---
# Permitir múltiples dominios
allowed_origins = [
    "https://masamadremonterrey.com",
    "https://www.masamadremonterrey.com",
    "https://account.masamadremonterrey.com",
    "http://localhost:8080", # Para pruebas locales
    "http://127.0.0.1:8080", # Para pruebas locales
    "file://" # Para archivos HTML locales
]

app = Flask(__name__)
# Configuración avanzada de CORS
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

# --- ALMACENAMIENTO DE SESIONES ---
# Almacenamiento temporal de sesiones (en producción usa Redis o base de datos)
# Considerar usar collections.defaultdict para manejo más seguro de claves inexistentes
from collections import defaultdict
# sessions = {} # Original
sessions = defaultdict(lambda: None) # Mejora: Evita KeyError al acceder a sesiones inexistentes

# --- MANEJO DE HEADERS CORS ---
@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = make_response()
        # Flask-CORS debería manejar esto, pero asegurémonos
        # response.headers.add("Access-Control-Allow-Origin", "*") # Ya manejado por CORS(app)
        response.headers.add('Access-Control-Allow-Headers', "*")
        response.headers.add('Access-Control-Allow-Methods', "*")
        return response

@app.after_request
def after_request(response):
    # Asegurar que las respuestas tengan los headers necesarios
    # Puede ser útil para debugging o agregar headers personalizados si se requiere
    # response.headers.add('Custom-Header', 'chatbot-api') # Ejemplo
    return response

# --- ENDPOINTS DE LA API ---

@app.route('/api/chat/init', methods=['POST'])
def init_chat():
    """Inicializa una nueva sesión de chat"""
    try:
        data = request.json
        # Validar datos de entrada
        if not data:
            logger.warning("Solicitud POST /api/chat/init sin datos JSON")
            return jsonify({
                "status": "error",
                "message": "Datos JSON requeridos"
            }), 400

        user_id = data.get('user_id')
        if not user_id:
            # Generar un user_id si no se proporciona
            user_id = f"user_{int(datetime.now().timestamp() * 1000)}" # Más específico con milisegundos
            logger.info(f"Generando user_id para nueva sesión: {user_id}")

        # Verificar si la sesión ya existe (opcional, dependiendo de la lógica deseada)
        # Si se permite reiniciar sesión, simplemente se sobreescribe
        # Si no, se podría devolver un error o reutilizar la existente

        # Crear historial de conversación
        conversation_history = ConversationHistory(user_id=user_id)
        sessions[user_id] = conversation_history # Almacenar en el diccionario de sesiones

        welcome_message = "¡Hola! Soy tu asistente de panadería especializado en masa madre. ¿En qué puedo ayudarte hoy?"

        logger.info(f"✅ Sesión iniciada para el usuario: {user_id}")
        return jsonify({
            "status": "success",
            "user_id": user_id,
            "message": "Sesión de chat iniciada",
            "welcome_message": welcome_message
        })

    except Exception as e:
        logger.error(f"❌ Error crítico al iniciar sesión: {str(e)}", exc_info=True) # exc_info=True para stack trace
        return jsonify({
            "status": "error",
            "message": "Error interno del servidor al iniciar la sesión de chat"
        }), 500

# --- BLOQUE DE LÓGICA DE DETECCIÓN DE DIFICULTADES (SEPARADO) ---
# Esta sección contiene la lógica que antes causaba problemas al detectar dificultades.
# Se ha comentado o reestructurado para evitar que interfiera con el flujo normal.
# Si se desea mantener esta funcionalidad, se debe implementar de forma más robusta
# y no como parte del flujo principal de manejo de mensajes.
#
# Ejemplo de cómo podría verse esta lógica separada (conceptual):
# def detectar_dificultades_usuario(user_id, conversation_history):
#     # Lógica para analizar el historial y detectar patrones de dificultad
#     # Esta función NO debería interrumpir el flujo normal de mensajes
#     # sino que podría registrar métricas o activar alertas internas.
#     pass
# --- FIN BLOQUE DE DETECCIÓN DE DIFICULTADES ---

@app.route('/api/chat/message', methods=['POST'])
def handle_message():
    """Procesa un mensaje del usuario"""
    try:
        # Log detallado de la solicitud
        data = request.json
        logger.info(f"📩 Mensaje recibido: {json.dumps(data) if data else 'Sin datos'}")

        # Validación de datos de entrada
        if not data:
            logger.error("❌ Error: Solicitud sin datos JSON")
            return jsonify({
                "status": "error",
                "message": "Datos JSON requeridos"
            }), 400

        user_id = data.get('user_id')
        message = data.get('message', '').strip()

        # Diagnóstico detallado de validación
        if not user_id:
            logger.error("❌ Error: user_id no proporcionado en la solicitud")
            return jsonify({
                "status": "error",
                "message": "user_id es requerido"
            }), 400

        # Acceder a la sesión con manejo de errores mejorado
        # conversation_history = sessions[user_id] # Original - Puede causar KeyError
        conversation_history = sessions.get(user_id) # Mejora: Usar .get()
        if not conversation_history:
            logger.error(f"❌ Error: Sesión no encontrada para user_id: {user_id}")
            # Para diagnóstico, listar todas las sesiones (con cuidado en producción)
            logger.debug(f"📊 Sesiones activas (primeras 10): {list(sessions.keys())[:10]}")
            return jsonify({
                "status": "error",
                "message": "Sesión no válida. Por favor, inicia una nueva sesión.",
                "requires_new_session": True # Indicador para el frontend
            }), 400

        if not message:
            logger.warning("⚠️ Advertencia: Mensaje vacío recibido")
            # En lugar de error, podríamos devolver una respuesta amigable
            return jsonify({
                "status": "success", # Mantener status success para fluidez
                "response": "Parece que enviaste un mensaje vacío. ¿En qué puedo ayudarte?",
                "sources": [],
                "user_id": user_id
            })

        # --- GENERACIÓN DE RESPUESTA CON MANEJO DE ERRORES ---
        chatbot_response = None
        try:
            logger.info(f"🤖 Generando respuesta para user_id: {user_id}, mensaje: '{message[:50]}...'")
            chatbot_response = generate_chatbot_response(
                query=message,
                user_id=user_id,
                conversation_history=conversation_history
            )
            logger.info(f"✅ Respuesta generada exitosamente para {user_id}")
        except Exception as generation_error:
            logger.error(f"❌ Error crítico en generate_chatbot_response para {user_id}: {str(generation_error)}", exc_info=True)
            # --- DEGRADACIÓN ELEGANTE ---
            # En lugar de romper todo, devolvemos una respuesta de error estructurada
            # que el frontend puede manejar específicamente.
            return jsonify({
                "status": "success", # Mantener "success" para que el frontend lo procese como mensaje normal
                "response": (
                    "Lo siento, estoy teniendo dificultades técnicas temporales para procesar tu consulta. "
                    "Por favor, inténtalo de nuevo en un momento. "
                    "Si el problema persiste, puedes escribir 'soporte' para contactar con un agente humano."
                ),
                "sources": [],
                "user_id": user_id,
                "error_flag": True, # Bandera para que el frontend sepa que fue un error interno
                "error_type": "generation_error"
            })

        # --- PREPARACIÓN DE LA RESPUESTA ---
        # Validar la estructura de la respuesta de generate_chatbot_response
        if not isinstance(chatbot_response, dict):
            logger.error(f"❌ generate_chatbot_response devolvió un tipo inesperado: {type(chatbot_response)}")
            return jsonify({
                "status": "success",
                "response": (
                    "Ups, parece que tuve un pequeño problema interno al formular mi respuesta. "
                    "¿Podrías repetir tu pregunta? Estoy aquí para ayudarte."
                ),
                "sources": [],
                "user_id": user_id,
                "error_flag": True,
                "error_type": "response_format_error"
            })

        # Extraer componentes con valores por defecto
        response_text = chatbot_response.get('response', 'Lo siento, no tengo una respuesta para esa consulta.')
        sources_list = chatbot_response.get('sources', [])

        # Validar tipos
        if not isinstance(response_text, str):
            logger.warning(f"⚠️ 'response' no es string, es {type(response_text)}. Convirtiendo.")
            response_text = str(response_text)
        if not isinstance(sources_list, list):
            logger.warning(f"⚠️ 'sources' no es lista, es {type(sources_list)}. Convirtiendo.")
            sources_list = list(sources_list) if hasattr(sources_list, '__iter__') else []

        # Preparar respuesta para el frontend
        response_data = {
            "status": "success",
            "response": response_text,
            "sources": sources_list,
            "user_id": user_id
        }

        logger.info(f"📤 Mensaje procesado y respuesta enviada para el usuario {user_id}")
        return jsonify(response_data)

    except Exception as e:
        # Error crítico no relacionado con la generación de respuesta
        logger.critical(f"❌ Error crítico no manejado en /api/chat/message: {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": "Error interno del servidor al procesar tu mensaje"
        }), 500

@app.route('/api/chat/feedback', methods=['POST'])
def handle_feedback():
    """Registra retroalimentación del usuario"""
    try:
        data = request.json
        logger.info(f"📊 Feedback recibido: {json.dumps(data) if data else 'Sin datos'}")

        # Validación de datos
        if not data:
            return jsonify({
                "status": "error",
                "message": "Datos JSON requeridos"
            }), 400

        user_id = data.get('user_id')
        rating = data.get('rating')
        comment = data.get('comment', '')

        # Validaciones
        if not user_id or sessions.get(user_id) is None: # Mejora: usar .get()
            logger.warning(f"⚠️ Feedback rechazado: Sesión no válida para user_id {user_id}")
            return jsonify({
                "status": "error",
                "message": "Sesión no válida"
            }), 400

        if rating is None:
            logger.warning(f"⚠️ Feedback rechazado: Rating no proporcionado para {user_id}")
            return jsonify({
                "status": "error",
                "message": "Calificación (rating) es requerida"
            }), 400

        if not isinstance(rating, int) or not (1 <= rating <= 5):
            logger.warning(f"⚠️ Feedback rechazado: Rating inválido {rating} para {user_id}")
            return jsonify({
                "status": "error",
                "message": "Calificación inválida. Debe ser un número entero entre 1 y 5."
            }), 400

        # Obtener la última consulta y respuesta
        conversation_history = sessions[user_id]
        full_history = conversation_history.get_full_history()

        if not full_history:
            logger.warning(f"⚠️ Feedback rechazado: No hay historial para {user_id}")
            return jsonify({
                "status": "error",
                "message": "No hay historial de conversación para calificar"
            }), 400

        last_exchange = full_history[-1]

        # Registrar retroalimentación (asumiendo que esta función maneja sus propios errores)
        try:
            record_feedback(
                query=last_exchange['query'],
                response=last_exchange['response'],
                provider="claude", # Asumiendo que Claude es el proveedor, ajustar si es diferente
                rating=rating,
                user_comment=comment,
                session_id=user_id
            )
            logger.info(f"✅ Retroalimentación registrada para el usuario {user_id}: {rating}/5")
            return jsonify({
                "status": "success",
                "message": "¡Gracias por tu retroalimentación!"
            })
        except Exception as feedback_error:
            logger.error(f"❌ Error al registrar retroalimentación para {user_id}: {str(feedback_error)}", exc_info=True)
            # Aunque falle el registro, podemos considerar el feedback como "recibido"
            # o devolver un error. Depende de la política de la aplicación.
            # Opción 1: Devolver error
            # return jsonify({
            #     "status": "error",
            #     "message": "Error al guardar tu retroalimentación. Lo estamos investigando."
            # }), 500
            # Opción 2: Aceptar feedback pero loguear error (más robusto)
            logger.warning(f"⚠️ Feedback aceptado pero no guardado para {user_id} debido a error interno.")
            return jsonify({
                "status": "success",
                "message": "¡Gracias por tu retroalimentación! (Nota: Hubo un pequeño problema guardándola, pero la hemos recibido)."
            })


    except Exception as e:
        logger.critical(f"❌ Error crítico no manejado en /api/chat/feedback: {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": "Error interno del servidor al registrar tu retroalimentación"
        }), 500

@app.route('/api/chat/support', methods=['POST'])
def request_support():
    """Solicita soporte humano"""
    try:
        data = request.json
        logger.info(f"🆘 Solicitud de soporte recibida: {json.dumps(data) if data else 'Sin datos'}")

        # Validación de datos
        if not data:
            return jsonify({
                "status": "error",
                "message": "Datos JSON requeridos"
            }), 400

        user_id = data.get('user_id')
        contact_info = data.get('contact_info', '').strip() # .strip() para eliminar espacios

        # Validaciones
        if not user_id or sessions.get(user_id) is None: # Mejora: usar .get()
            logger.warning(f"⚠️ Solicitud de soporte rechazada: Sesión no válida para {user_id}")
            return jsonify({
                "status": "error",
                "message": "Sesión no válida. Por favor, inicia una nueva sesión de chat."
            }), 400

        if not contact_info:
            logger.warning(f"⚠️ Solicitud de soporte rechazada: Información de contacto faltante para {user_id}")
            return jsonify({
                "status": "error",
                "message": "Se requiere información de contacto (correo o teléfono)"
            }), 400

        # Obtener historial completo
        conversation_history = sessions[user_id]
        full_history = conversation_history.get_full_history()

        if not full_history:
            logger.warning(f"⚠️ Solicitud de soporte: Historial vacío para {user_id}")
            # No necesariamente un error, podría ser la primera interacción
            # Decidir si se permite o no soporte sin historial
            full_history = [] # Proceder con historial vacío

        # Importar y llamar a la función de creación de ticket
        # Mover el import al interior del try para manejar errores de importación
        try:
            from support_system import create_support_ticket
        except ImportError as import_error:
            logger.critical(f"❌ Módulo support_system no encontrado: {str(import_error)}")
            return jsonify({
                "status": "error",
                "message": "Servicio de soporte no disponible temporalmente"
            }), 500

        # Preparar datos para el ticket
        last_query = ""
        last_response = ""
        if full_history:
            last_exchange = full_history[-1]
            last_query = last_exchange.get('query', 'No disponible')
            last_response = last_exchange.get('response', 'No disponible')

        # Crear ticket de soporte
        try:
            ticket_id = create_support_ticket(
                query=last_query,
                response=last_response,
                conversation_history=full_history,
                contact_info=contact_info,
                priority="media", # Considerar hacer esto configurable o basado en contexto
                reason="Solicitud de soporte humano desde el widget de chat"
            )
            logger.info(f"✅ Ticket de soporte creado para el usuario {user_id} con ID: {ticket_id}")
            return jsonify({
                "status": "success",
                "message": "Ticket de soporte creado. Un representante se contactará contigo pronto.",
                "ticket_id": ticket_id # Opcional: devolver el ID del ticket
            })

        except Exception as ticket_error:
            logger.error(f"❌ Error al crear ticket de soporte para {user_id}: {str(ticket_error)}", exc_info=True)
            return jsonify({
                "status": "error",
                "message": "Error al crear tu ticket de soporte. Por favor, inténtalo de nuevo o contacta directamente a soporte@masamadremonterrey.com"
            }), 500

    except Exception as e:
        logger.critical(f"❌ Error crítico no manejado en /api/chat/support: {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": "Error interno del servidor al procesar tu solicitud de soporte"
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Endpoint para verificar el estado del servicio"""
    logger.debug("🔍 Solicitud de health check recibida")
    return jsonify({
        "status": "healthy",
        "service": "masa-madre-chatbot-api",
        "timestamp": datetime.now().isoformat()
    })

# --- PUNTO DE ENTRADA ---
if __name__ == "__main__":
    port = int(os.getenv('PORT', 5000))
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() in ('true', '1', 't')
    logger.info(f"🚀 Iniciando API del chatbot en el puerto {port} (Debug: {debug_mode})")
    app.run(host='0.0.0.0', port=port, debug=debug_mode) # Usar variable de entorno para debug

