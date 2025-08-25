#!/usr/bin/env python3
"""
API para el Chatbot de Masa Madre Monterrey
- Proporciona endpoints para el widget de chat
- Incluye integración con tiendas Shopify
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../lib'))

import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from flask_cors import CORS
from collections import defaultdict

# Importar módulos locales
from conversation_history import ConversationHistory
from feedback_system import record_feedback
from semantic_search import generate_chatbot_response, search_products

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("chat_api.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()

# --- CONFIGURACIÓN DE LA APLICACIÓN FLASK ---
app = Flask(__name__)

# Configurar CORS
CORS(app, resources={
    r"/api/*": {
        "origins": [
            "https://masamadremonterrey.com",
            "https://www.masamadremonterrey.com",
            "https://account.masamadremonterrey.com",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "*.myshopify.com",
            "*.ngrok.io",
            "*"
        ]
    }
})

# --- ALMACENAMIENTO DE SESIONES ---
sessions = defaultdict(lambda: None)

# --- ALMACENAMIENTO PARA SHOPIFY ---
# Configuraciones por tienda
shop_configs = defaultdict(lambda: {
    "enabled": True,
    "primaryColor": "#8B4513",
    "welcomeMessage": "¡Hola! ¿En qué puedo ayudarte con nuestros productos de panadería?",
    "supportEmail": "",
    "categories": ["Panes", "Pasteles", "Masa Madre", "Ingredientes"],
    "lastSyncAt": None
})

# Productos por tienda
shop_products = defaultdict(list)

# --- MIDDLEWARE PARA VALIDAR TIENDAS SHOPIFY ---
def validate_shopify_store():
    """Middleware para validar que la request viene de una tienda Shopify válida"""
    shop = request.headers.get('X-Shop-Domain') or request.json.get('shop') if request.json else None
    
    if not shop or not shop.endswith('.myshopify.com'):
        return None
    
    return shop

# --- ENDPOINTS ORIGINALES DEL CHATBOT ---

@app.route('/api/health', methods=['GET'])
def health_check():
    """Endpoint para verificar el estado del servicio"""
    logger.debug("Solicitud de health check recibida")
    return jsonify({
        "status": "healthy",
        "service": "masa-madre-chatbot-api",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/api/chat/init', methods=['POST'])
def init_chat():
    """Inicializa una nueva sesión de chat"""
    try:
        data = request.json
        logger.info(f"Datos de inicialización recibidos: {json.dumps(data) if data else 'Sin datos'}")

        if not data:
            logger.error("Error: Solicitud sin datos JSON")
            return jsonify({
                "status": "error",
                "message": "Datos JSON requeridos"
            }), 400

        user_id = data.get('user_id')
        if not user_id:
            user_id = f"user_{int(datetime.now().timestamp() * 1000)}"
            logger.info(f"Generando user_id para nueva sesión: {user_id}")

        # Crear historial de conversación
        conversation_history = ConversationHistory(user_id=user_id)
        sessions[user_id] = conversation_history

        welcome_message = "¡Hola! Bienvenido a Masa Madre Monterrey.\n\nSoy tu asistente virtual y estoy aquí para ayudarte con todo lo relacionado con nuestros panes artesanales de masa madre. ¿En qué puedo ayudarte hoy?"

        logger.info(f"Sesión iniciada para el usuario: {user_id}")
        return jsonify({
            "status": "success",
            "user_id": user_id,
            "message": "Sesión de chat iniciada",
            "welcome_message": welcome_message
        })

    except Exception as e:
        logger.critical(f"Error crítico al iniciar sesión: {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": "Error interno del servidor al iniciar la sesión de chat"
        }), 500

@app.route('/api/chat/message', methods=['POST'])
def handle_message():
    """Procesa un mensaje del usuario"""
    try:
        data = request.json
        logger.info(f"Mensaje recibido: {json.dumps(data) if data else 'Sin datos'}")

        if not data: 
            logger.error("Error: Solicitud sin datos JSON")
            return jsonify({
                "status": "error",
                "message": "Datos JSON requeridos"
            }), 400

        user_id = data.get('user_id')
        message = data.get('message', '').strip()

        if not user_id:
            logger.error("Error: user_id no proporcionado en la solicitud")
            return jsonify({
                "status": "error",
                "message": "user_id es requerido"
            }), 400

        conversation_history = sessions.get(user_id)
        if not conversation_history:
            logger.error(f"Error: Sesión no encontrada para user_id: {user_id}")
            return jsonify({
                "status": "error",
                "message": "Sesión no válida. Por favor, inicia una nueva sesión.",
                "requires_new_session": True
            }), 400

        if not message:
            logger.warning("Advertencia: Mensaje vacío recibido")
            return jsonify({
                "status": "success",
                "response": "Parece que enviaste un mensaje vacío. ¿En qué puedo ayudarte?",
                "sources": [],
                "user_id": user_id
            })

        # Detección de intención de soporte humano
        support_keywords = [
            "humano", "agente", "representante", "persona", "soporte", 
            "hablar con alguien", "quiero hablar", "contactar", "conectar",
            "asesor", "ayuda humana", "humano por favor", "humano ahora"
        ]
        
        lower_message = message.lower()
        is_human_request = any(keyword in lower_message for keyword in support_keywords)

        # Generar respuesta
        try:
            logger.info(f"Generando respuesta para user_id: {user_id}, mensaje: '{message[:50]}...'")
            chatbot_response = generate_chatbot_response(
                query=message,
                user_id=user_id,
                conversation_history=conversation_history,
                detected_human_intent=is_human_request
            )
            logger.info(f"Respuesta generada exitosamente para {user_id}")
        except Exception as generation_error:
            logger.error(f"Error crítico en generate_chatbot_response para {user_id}: {str(generation_error)}", exc_info=True)
            return jsonify({
                "status": "success",
                "response": (
                    "Lo siento, estoy teniendo dificultades técnicas temporales para procesar tu consulta. "
                    "Por favor, inténtalo de nuevo en un momento. "
                    "Si el problema persiste, puedes escribir 'soporte' para contactar con un agente humano."
                ),
                "sources": [],
                "user_id": user_id,
                "error_flag": True,
                "error_type": "generation_error"
            })

        if not isinstance(chatbot_response, dict):
            logger.error(f"generate_chatbot_response devolvió un tipo inesperado: {type(chatbot_response)}")
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

        response_text = chatbot_response.get('response', 'Lo siento, no tengo una respuesta para esa consulta.')
        sources_list = chatbot_response.get('sources', [])

        if not isinstance(response_text, str):
            response_text = str(response_text)
        if not isinstance(sources_list, list):
            sources_list = list(sources_list) if hasattr(sources_list, '__iter__') else []

        backend_detected_intent = "intent_to_handoff" if is_human_request else "general"

        response_data = {
            "status": "success",
            "response": response_text,
            "sources": sources_list,
            "user_id": user_id,
            "detected_intent": backend_detected_intent
        }

        logger.info(f"Mensaje procesado y respuesta enviada para el usuario {user_id} (Intent: {backend_detected_intent})")
        return jsonify(response_data)

    except Exception as e:
        logger.critical(f"Error crítico no manejado en /api/chat/message: {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": "Error interno del servidor al procesar tu mensaje"
        }), 500

@app.route('/api/chat/feedback', methods=['POST'])
def handle_feedback():
    """Registra retroalimentación del usuario"""
    try:
        data = request.json
        logger.info(f"Feedback recibido: {json.dumps(data) if data else 'Sin datos'}")

        if not data: 
            return jsonify({
                "status": "error",
                "message": "Datos JSON requeridos"
            }), 400

        user_id = data.get('user_id')
        rating = data.get('rating')
        comment = data.get('comment', '')

        if not user_id or sessions.get(user_id) is None:
            logger.warning(f"Feedback rechazado: Sesión no válida para user_id {user_id}")
            return jsonify({
                "status": "error",
                "message": "Sesión no válida"
            }), 400

        if rating is None or not isinstance(rating, int) or not (1 <= rating <= 5):
            logger.warning(f"Feedback rechazado: Rating inválido {rating} para {user_id}")
            return jsonify({
                "status": "error",
                "message": "Calificación inválida. Debe ser un número entero entre 1 y 5."
            }), 400

        conversation_history = sessions[user_id]
        full_history = conversation_history.get_full_history()

        if not full_history:
            logger.warning(f"Feedback rechazado: No hay historial para {user_id}")
            return jsonify({
                "status": "error",
                "message": "No hay historial de conversación para calificar"
            }), 400

        last_exchange = full_history[-1]

        try:
            record_feedback(
                query=last_exchange['query'],
                response=last_exchange['response'],
                provider="claude",
                rating=rating,
                user_comment=comment,
                session_id=user_id
            )
            logger.info(f"Retroalimentación registrada para el usuario {user_id}: {rating}/5")
            return jsonify({
                "status": "success",
                "message": "¡Gracias por tu retroalimentación!"
            })
        except Exception as feedback_error:
            logger.error(f"Error al registrar retroalimentación para {user_id}: {str(feedback_error)}", exc_info=True)
            return jsonify({
                "status": "success",
                "message": "¡Gracias por tu retroalimentación! (Nota: Hubo un pequeño problema guardándola, pero la hemos recibido)."
            })

    except Exception as e:
        logger.critical(f"Error crítico no manejado en /api/chat/feedback: {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": "Error interno del servidor al registrar tu retroalimentación"
        }), 500

@app.route('/api/chat/support', methods=['POST'])
def request_support():
    """Procesa solicitudes de soporte humano"""
    try:
        data = request.json
        logger.info(f"Solicitud de soporte recibida: {json.dumps(data) if data else 'Sin datos'}")

        if not data: 
            return jsonify({
                "status": "error",
                "message": "Datos JSON requeridos"
            }), 400

        user_id = data.get('user_id')
        contact_info = data.get('contact_info', {})

        if not user_id or sessions.get(user_id) is None:
            return jsonify({
                "status": "error",
                "message": "Sesión no válida"
            }), 400

        if not isinstance(contact_info, dict) or not all(k in contact_info for k in ['name', 'email', 'phone']):
            return jsonify({
                "status": "error",
                "message": "Información de contacto incompleta. Se requiere nombre, email y teléfono."
            }), 400

        conversation_history = sessions[user_id]
        full_history = conversation_history.get_full_history()

        last_query = ""
        last_response = ""
        if full_history:
            last_exchange = full_history[-1]
            last_query = last_exchange.get('query', '')
            last_response = last_exchange.get('response', '')

        try:
            from support_system_improved import create_support_ticket
            ticket_id = create_support_ticket(
                query=last_query,
                response=last_response,
                conversation_history=full_history,
                contact_info=contact_info,
                priority="media",
                reason="Solicitud de soporte humano desde el widget de chat"
            )
            
            logger.info(f"Ticket de soporte creado: {ticket_id}")
            return jsonify({
                "status": "success",
                "message": f"Hemos recibido tu solicitud. Tu número de folio es: {ticket_id}. Te contactaremos pronto en {contact_info['email']}.",
                "ticket_id": ticket_id
            })
            
        except ValueError as e:
            logger.warning(f"Error de validación: {str(e)}")
            return jsonify({
                "status": "error",
                "message": str(e)
            }), 400
            
        except Exception as e:
            logger.error(f"Error al crear ticket: {str(e)}")
            return jsonify({
                "status": "error",
                "message": "Error al procesar tu solicitud. Por favor, inténtalo de nuevo."
            }), 500

    except Exception as e:
        logger.critical(f"Error crítico: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Error interno del servidor"
        }), 500

# --- NUEVOS ENDPOINTS PARA SHOPIFY ---

@app.route('/api/shopify/sync-products', methods=['POST'])
def shopify_sync_products():
    """Sincronizar productos desde Shopify"""
    try:
        shop = validate_shopify_store()
        if not shop:
            return jsonify({
                "success": False,
                "error": "Dominio de tienda de Shopify inválido"
            }), 400
        
        data = request.json
        if not data:
            return jsonify({
                "success": False,
                "error": "Datos JSON requeridos"
            }), 400
            
        products = data.get('products', [])
        config = data.get('config', {})
        
        if not isinstance(products, list):
            return jsonify({
                "success": False,
                "error": "Formato de productos inválido"
            }), 400
        
        # Guardar configuración de la tienda
        current_config = shop_configs[shop]
        current_config.update(config)
        current_config['lastSyncAt'] = datetime.now().isoformat()
        shop_configs[shop] = current_config
        
        # Procesar y almacenar productos
        processed_products = []
        for product in products:
            processed_product = {
                **product,
                'shop': shop,
                'search_text': f"{product.get('title', '')} {product.get('description', '')} {product.get('category', '')} {' '.join(product.get('tags', []))}".lower(),
                'price_numeric': float(product.get('price', '0').replace('$', '').replace(',', '') or 0),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            processed_products.append(processed_product)
        
        # Almacenar productos
        shop_products[shop] = processed_products
        
        logger.info(f"Sincronizados {len(processed_products)} productos para {shop}")
        
        return jsonify({
            "success": True,
            "message": f"{len(processed_products)} productos sincronizados correctamente",
            "products_count": len(processed_products),
            "shop": shop,
            "sync_time": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error sincronizando productos: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Error interno del servidor",
            "details": str(e)
        }), 500

@app.route('/api/shopify/chat', methods=['POST'])
def shopify_chat():
    """Endpoint de chat desde tiendas Shopify"""
    try:
        shop = validate_shopify_store()
        if not shop:
            return jsonify({
                "success": False,
                "error": "Dominio de tienda de Shopify inválido"
            }), 400
        
        data = request.json
        if not data:
            return jsonify({
                "success": False,
                "error": "Datos JSON requeridos"
            }), 400
            
        message = data.get('message', '').strip()
        user_id = data.get('user_id')
        context = data.get('context', {})
        
        if not message or not user_id:
            return jsonify({
                "success": False,
                "error": "Mensaje y user_id son requeridos"
            }), 400
        
        # Obtener configuración y productos de la tienda
        config = shop_configs.get(shop, {})
        products = shop_products.get(shop, [])
        
        # Verificar horarios de negocio si están habilitados
        if config.get('businessHours', {}).get('enabled', False):
            if not is_business_hours(config['businessHours']):
                return jsonify({
                    "success": True,
                    "response": "Gracias por contactarnos. Nuestro horario de atención es de lunes a viernes de 9:00 AM a 6:00 PM, y sábados de 10:00 AM a 4:00 PM. Te responderemos en nuestro próximo horario de atención.",
                    "out_of_hours": True
                })
        
        # Procesar mensaje y buscar productos relevantes
        chat_response = process_shopify_chat_message(message, products, config, context)
        
        # Registrar interacción
        logger.info(f"[{shop}] {user_id}: {message}")
        logger.info(f"[{shop}] Bot: {chat_response['response']}")
        
        return jsonify({
            "success": True,
            **chat_response,
            "shop": shop,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error procesando chat de Shopify: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Error procesando mensaje",
            "details": str(e)
        }), 500

@app.route('/api/shopify/config', methods=['GET'])
def shopify_get_config():
    """Obtener configuración de una tienda Shopify"""
    try:
        shop = validate_shopify_store()
        if not shop:
            return jsonify({
                "success": False,
                "error": "Dominio de tienda de Shopify inválido"
            }), 400
        
        config = shop_configs.get(shop, {
            "enabled": True,
            "primaryColor": "#8B4513",
            "welcomeMessage": "¡Hola! ¿En qué puedo ayudarte con nuestros productos de panadería?",
            "supportEmail": "",
            "categories": ["Panes", "Pasteles", "Masa Madre", "Ingredientes"]
        })
        
        return jsonify({
            "success": True,
            "enabled": config.get('enabled', True),
            "config": config
        })
        
    except Exception as e:
        logger.error(f"Error obteniendo configuración: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# --- FUNCIONES AUXILIARES PARA SHOPIFY ---

def process_shopify_chat_message(message, products, config, context={}):
    """Procesar mensaje de chat desde Shopify"""
    lower_message = message.lower()
    
    # Detección de intención básica
    intents = detect_shopify_intent(lower_message)
    response = ''
    suggested_products = []
    detected_intent = 'general'
    
    if 'product_search' in intents:
        detected_intent = 'product_search'
        suggested_products = search_shopify_products(lower_message, products)
        
        if suggested_products:
            response = f"Encontré {len(suggested_products)} producto{'s' if len(suggested_products) > 1 else ''} que podrían interesarte:"
        else:
            response = 'No encontré productos específicos con esos términos, pero puedo ayudarte a encontrar algo más. ¿Qué tipo de producto de panadería estás buscando?'
    
    elif 'price_inquiry' in intents:
        detected_intent = 'price_inquiry'
        price_products = search_shopify_products(lower_message, products)
        
        if price_products:
            response = 'Aquí tienes información de precios:'
            suggested_products = price_products
        else:
            response = 'Para darte información precisa de precios, ¿me podrías decir qué producto específico te interesa?'
    
    elif 'support_request' in intents:
        detected_intent = 'intent_to_handoff'
        response = 'Entiendo que necesitas ayuda especializada. Por favor, presiona el botón de abajo que dice "Hablar con alguien" para que nuestro equipo te contacte directamente.'
    
    elif 'greeting' in intents:
        detected_intent = 'greeting'
        response = config.get('welcomeMessage', '¡Hola! Bienvenido a nuestra panadería. ¿En qué puedo ayudarte hoy?')
    
    else:
        # Búsqueda general en productos
        general_results = search_shopify_products(lower_message, products, threshold=0.3)
        
        if general_results:
            detected_intent = 'general_product_match'
            response = 'Basándome en tu consulta, estos productos podrían interesarte:'
            suggested_products = general_results[:3]
        else:
            detected_intent = 'general'
            response = get_general_shopify_response(lower_message, config)
    
    return {
        'response': response,
        'products': suggested_products[:4],  # Máximo 4 productos
        'detected_intent': detected_intent,
        'context_used': bool(context.get('page_url'))
    }

def detect_shopify_intent(message):
    """Detectar intenciones en mensajes de Shopify"""
    intents = []
    
    patterns = {
        'greeting': r'\b(hola|buenos días|buenas tardes|buenas noches|saludos|hey)\b',
        'product_search': r'\b(busco|quiero|necesito|me interesa|pan|pastel|masa madre|ingredientes|harina)\b',
        'price_inquiry': r'\b(precio|cuesta|cuánto|costo|vale)\b',
        'availability': r'\b(disponible|hay|tienen|stock|inventario)\b',
        'support_request': r'\b(ayuda|hablar|contactar|problema|queja|soporte|asesor|persona|humano)\b'
    }
    
    import re
    for intent, pattern in patterns.items():
        if re.search(pattern, message, re.IGNORECASE):
            intents.append(intent)
    
    return intents

def search_shopify_products(query, products, threshold=0.5):
    """Buscar productos con sistema de scoring"""
    if not products:
        return []
    
    query_words = query.lower().split()
    query_words = [word for word in query_words if len(word) > 2]
    
    scored_products = []
    for product in products:
        score = 0
        search_text = product.get('search_text', '').lower()
        title = product.get('title', '').lower()
        category = product.get('category', '').lower()
        
        # Coincidencia exacta en título
        if query.lower() in title:
            score += 2
        
        # Coincidencias por palabra
        for word in query_words:
            if word in search_text:
                score += 1
            if word in title:
                score += 1.5
            if word in category:
                score += 1
        
        if score >= threshold:
            product_copy = product.copy()
            product_copy['relevance_score'] = score
            scored_products.append(product_copy)
    
    # Ordenar por relevancia
    scored_products.sort(key=lambda x: x['relevance_score'], reverse=True)
    return scored_products

def get_general_shopify_response(message, config):
    """Respuesta general para Shopify"""
    responses = [
        'Soy tu asistente especializado en productos de panadería. Puedo ayudarte a encontrar panes, pasteles, ingredientes y más. ¿Qué estás buscando específicamente?',
        'Estoy aquí para ayudarte con cualquier pregunta sobre nuestros productos. Puedo verificar precios, disponibilidad y darte recomendaciones. ¿En qué puedo asistirte?',
        'Como especialista en panadería, puedo ayudarte a encontrar exactamente lo que necesitas. ¿Te interesa algún producto en particular?'
    ]
    
    import random
    return random.choice(responses)

def is_business_hours(business_hours):
    """Verificar si está en horario de negocio"""
    if not business_hours.get('enabled', False):
        return True
    
    # Implementación básica - puedes expandirla según necesidades
    from datetime import datetime
    import pytz
    
    try:
        timezone = business_hours.get('timezone', 'America/Mexico_City')
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        
        day_name = now.strftime('%A').lower()
        current_time = now.strftime('%H:%M')
        
        schedule = business_hours.get('schedule', {})
        day_schedule = schedule.get(day_name, {})
        
        if day_schedule.get('closed', False):
            return False
        
        open_time = day_schedule.get('open', '09:00')
        close_time = day_schedule.get('close', '18:00')
        
        return open_time <= current_time <= close_time
        
    except Exception:
        # Si hay error con horarios, asumir que está abierto
        return True

@app.route('/api/shopify/chatbot-script', methods=['GET'])
def serve_chatbot_script():
    """Servir el script del chatbot personalizado por tienda"""
    shop = request.args.get('shop')
    
    if not shop:
        return "// Error: shop parameter required", 400
    
    # Obtener configuración de la tienda
    config = shop_configs.get(shop, {})
    
    # Generar script personalizado
    script_content = f"""
// Chatbot para {shop}
(function() {{
  if (window.masaMadreChatbotLoaded) return;
  window.masaMadreChatbotLoaded = true;

  const config = {{
    primaryColor: '{config.get("primaryColor", "#8B4513")}',
    welcomeMessage: '{config.get("welcomeMessage", "¡Hola! ¿En qué puedo ayudarte?")}',
    apiUrl: '{request.host_url}',
    shop: '{shop}'
  }};

  // Cargar el script principal del chatbot
  const script = document.createElement('script');
  script.src = '{request.host_url}static/chatbot.js';
  script.onload = function() {{
    if (window.initMasaMadreChat) {{
      window.initMasaMadreChat(config);
    }}
  }};
  document.head.appendChild(script);
}})();
"""
    
    return script_content, 200, {'Content-Type': 'application/javascript'}


# --- PUNTO DE ENTRADA ---
if __name__ == "__main__":
    port = int(os.getenv('PORT', 5000))
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() in ('true', '1', 't')
    logger.info(f"Iniciando API del chatbot en el puerto {port} (Debug: {debug_mode})")
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
