#!/usr/bin/env python3
"""
API para el Chatbot de Masa Madre Monterrey
- Proporciona endpoints para el widget de chat
"""
# Asegurar que el path a lib esté incluido
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../lib'))

import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from flask_cors import CORS

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

# Configurar CORS para permitir solicitudes desde el frontend
# Ajusta los orígenes según tu configuración (Shopify, localhost, etc.)
CORS(app, resources={
    r"/api/*": {
        "origins": [
            "https://masamadremonterrey.com",
            "https://www.masamadremonterrey.com",
            "https://account.masamadremonterrey.com",
            "http://localhost:8080",
            "*",
            "http://127.0.0.1:8080",
            "file://"
        ]
    }
})

# --- ALMACENAMIENTO DE SESIONES (En producción, usar Redis o DB) ---
# Usar defaultdict para evitar KeyError al acceder a sesiones inexistentes
from collections import defaultdict
sessions = defaultdict(lambda: None)


# --- NUEVOS ENDPOINTS PARA TIENDA CON CHATBOT ---



// api-extension.js - Extensiones para la API existente del chatbot
// Agregar estos endpoints al servidor existente de masa-madre-chatbot-api

const express = require('express');
const router = express.Router();

// Middleware para validar tienda de Shopify
const validateShopifyStore = (req, res, next) => {
  const shop = req.get('X-Shop-Domain') || req.body.shop || req.query.shop;
  
  if (!shop || !shop.includes('.myshopify.com')) {
    return res.status(400).json({
      success: false,
      error: 'Dominio de tienda de Shopify inválido'
    });
  }
  
  req.shop = shop;
  next();
};

// Base de datos en memoria para configuraciones de tiendas (en producción usar Redis/MongoDB)
const shopConfigs = new Map();
const shopProducts = new Map();

// === ENDPOINTS PARA CONFIGURACIÓN ===

// Obtener configuración de una tienda
router.get('/config', validateShopifyStore, (req, res) => {
  const config = shopConfigs.get(req.shop) || {
    enabled: true,
    primaryColor: '#8B4513',
    welcomeMessage: '¡Hola! ¿En qué puedo ayudarte con nuestros productos de panadería?',
    supportEmail: '',
    categories: ['Panes', 'Pasteles', 'Masa Madre', 'Ingredientes'],
    businessHours: {
      enabled: false,
      timezone: 'America/Mexico_City',
      schedule: {
        monday: { open: '09:00', close: '18:00' },
        tuesday: { open: '09:00', close: '18:00' },
        wednesday: { open: '09:00', close: '18:00' },
        thursday: { open: '09:00', close: '18:00' },
        friday: { open: '09:00', close: '18:00' },
        saturday: { open: '10:00', close: '16:00' },
        sunday: { closed: true }
      }
    }
  };
  
  res.json({
    success: true,
    enabled: config.enabled,
    config
  });
});

// === ENDPOINTS PARA SINCRONIZACIÓN DE PRODUCTOS ===

// Sincronizar todos los productos de una tienda
router.post('/sync-products', validateShopifyStore, (req, res) => {
  try {
    const { products, config } = req.body;
    
    if (!Array.isArray(products)) {
      return res.status(400).json({
        success: false,
        error: 'Formato de productos inválido'
      });
    }
    
    // Guardar configuración de la tienda
    shopConfigs.set(req.shop, {
      ...shopConfigs.get(req.shop),
      ...config,
      lastSyncAt: new Date().toISOString()
    });
    
    // Procesar y almacenar productos
    const processedProducts = products.map(product => ({
      ...product,
      shop: req.shop,
      search_text: `${product.title} ${product.description} ${product.category} ${product.tags?.join(' ')}`.toLowerCase(),
      price_numeric: parseFloat(product.price) || 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    }));
    
    // Almacenar productos (en producción usar base de datos con índices de búsqueda)
    shopProducts.set(req.shop, processedProducts);
    
    console.log(`✅ Sincronizados ${processedProducts.length} productos para ${req.shop}`);
    
    res.json({
      success: true,
      message: `${processedProducts.length} productos sincronizados correctamente`,
      products_count: processedProducts.length,
      shop: req.shop,
      sync_time: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error sincronizando productos:', error);
    res.status(500).json({
      success: false,
      error: 'Error interno del servidor',
      details: error.message
    });
  }
});

// Actualizar un producto específico
router.post('/product-update', validateShopifyStore, (req, res) => {
  try {
    const { action, product, product_id } = req.body;
    const currentProducts = shopProducts.get(req.shop) || [];
    
    switch (action) {
      case 'create':
      case 'update':
        const processedProduct = {
          ...product,
          shop: req.shop,
          search_text: `${product.title} ${product.description} ${product.category} ${product.tags?.join(' ')}`.toLowerCase(),
          price_numeric: parseFloat(product.price) || 0,
          updated_at: new Date().toISOString()
        };
        
        const existingIndex = currentProducts.findIndex(p => p.shopify_id === product.shopify_id);
        
        if (existingIndex >= 0) {
          currentProducts[existingIndex] = processedProduct;
        } else {
          processedProduct.created_at = new Date().toISOString();
          currentProducts.push(processedProduct);
        }
        
        shopProducts.set(req.shop, currentProducts);
        
        res.json({
          success: true,
          action,
          message: `Producto ${action === 'create' ? 'creado' : 'actualizado'} correctamente`
        });
        break;
        
      case 'delete':
        const filteredProducts = currentProducts.filter(p => p.shopify_id !== product_id);
        shopProducts.set(req.shop, filteredProducts);
        
        res.json({
          success: true,
          action,
          message: 'Producto eliminado correctamente'
        });
        break;
        
      default:
        res.status(400).json({
          success: false,
          error: 'Acción no válida. Use: create, update, delete'
        });
    }
    
  } catch (error) {
    console.error('Error actualizando producto:', error);
    res.status(500).json({
      success: false,
      error: 'Error actualizando producto',
      details: error.message
    });
  }
});

// === ENDPOINT PRINCIPAL DE CHAT ===

router.post('/chat', validateShopifyStore, async (req, res) => {
  try {
    const { message, user_id, context } = req.body;
    
    if (!message || !user_id) {
      return res.status(400).json({
        success: false,
        error: 'Mensaje y user_id son requeridos'
      });
    }
    
    const config = shopConfigs.get(req.shop) || {};
    const products = shopProducts.get(req.shop) || [];
    
    // Validar horarios de negocio si están habilitados
    if (config.businessHours?.enabled && !isBusinessHours(config.businessHours)) {
      return res.json({
        success: true,
        response: `Gracias por contactarnos. Nuestro horario de atención es de lunes a viernes de 9:00 AM a 6:00 PM, y sábados de 10:00 AM a 4:00 PM. Te responderemos en nuestro próximo horario de atención.`,
        out_of_hours: true
      });
    }
    
    // Procesar mensaje y buscar productos relevantes
    const chatResponse = await processChatMessage(message, products, config, context);
    
    // Registrar interacción (en producción, guardar en base de datos)
    console.log(`💬 [${req.shop}] ${user_id}: ${message}`);
    console.log(`🤖 [${req.shop}] Bot: ${chatResponse.response}`);
    
    res.json({
      success: true,
      ...chatResponse,
      shop: req.shop,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error procesando chat:', error);
    res.status(500).json({
      success: false,
      error: 'Error procesando mensaje',
      details: error.message
    });
  }
});

// === FUNCIONES AUXILIARES ===

async function processChatMessage(message, products, config, context = {}) {
  const lowerMessage = message.toLowerCase();
  
  // Detección de intención básica
  const intents = detectIntent(lowerMessage);
  let response = '';
  let suggestedProducts = [];
  let detectedIntent = 'general';
  
  if (intents.includes('product_search')) {
    detectedIntent = 'product_search';
    suggestedProducts = searchProducts(lowerMessage, products);
    
    if (suggestedProducts.length > 0) {
      response = `Encontré ${suggestedProducts.length} producto${suggestedProducts.length > 1 ? 's' : ''} que podrían interesarte:`;
    } else {
      response = 'No encontré productos específicos con esos términos, pero puedo ayudarte a encontrar algo más. ¿Qué tipo de producto de panadería estás buscando?';
    }
  }
  else if (intents.includes('price_inquiry')) {
    detectedIntent = 'price_inquiry';
    const priceProducts = searchProducts(lowerMessage, products);
    
    if (priceProducts.length > 0) {
      response = 'Aquí tienes información de precios:';
      suggestedProducts = priceProducts;
    } else {
      response = 'Para darte información precisa de precios, ¿me podrías decir qué producto específico te interesa?';
    }
  }
  else if (intents.includes('availability')) {
    detectedIntent = 'availability';
    const availableProducts = searchProducts(lowerMessage, products).filter(p => 
      p.availability === 'En stock'
    );
    
    if (availableProducts.length > 0) {
      response = 'Estos productos están disponibles ahora:';
      suggestedProducts = availableProducts;
    } else {
      response = 'Déjame verificar la disponibilidad de nuestros productos. ¿Qué producto específico te interesa?';
    }
  }
  else if (intents.includes('support_request')) {
    detectedIntent = 'intent_to_handoff';
    response = 'Entiendo que necesitas ayuda especializada. Por favor, presiona el botón de abajo que dice "Hablar con alguien" para que nuestro equipo te contacte directamente.';
  }
  else if (intents.includes('greeting')) {
    detectedIntent = 'greeting';
    response = config.welcomeMessage || '¡Hola! Bienvenido a nuestra panadería. ¿En qué puedo ayudarte hoy? Puedo ayudarte a encontrar productos, verificar precios y disponibilidad.';
  }
  else if (intents.includes('hours_inquiry')) {
    detectedIntent = 'hours_inquiry';
    if (config.businessHours?.enabled) {
      response = getBusinessHoursMessage(config.businessHours);
    } else {
      response = 'Para información sobre nuestros horarios, te recomiendo contactar directamente a la tienda. ¿Hay algo más en lo que pueda ayudarte?';
    }
  }
  else {
    // Búsqueda general en productos
    const generalResults = searchProducts(lowerMessage, products, 0.3);
    
    if (generalResults.length > 0) {
      detectedIntent = 'general_product_match';
      response = 'Basándome en tu consulta, estos productos podrían interesarte:';
      suggestedProducts = generalResults.slice(0, 3);
    } else {
      detectedIntent = 'general';
      response = getGeneralResponse(lowerMessage, config);
    }
  }
  
  return {
    response,
    products: suggestedProducts.slice(0, 4), // Máximo 4 productos
    detected_intent: detectedIntent,
    context_used: !!context.page_url
  };
}

function detectIntent(message) {
  const intents = [];
  
  // Patterns de intenciones
  const patterns = {
    greeting: /\b(hola|buenos días|buenas tardes|buenas noches|saludos|hey)\b/i,
    product_search: /\b(busco|quiero|necesito|me interesa|pan|pastel|masa madre|ingredientes|harina)\b/i,
    price_inquiry: /\b(precio|cuesta|cuánto|costo|vale)\b/i,
    availability: /\b(disponible|hay|tienen|stock|inventario)\b/i,
    support_request: /\b(ayuda|hablar|contactar|problema|queja|soporte|asesor|persona|humano)\b/i,
    hours_inquiry: /\b(horario|hora|abierto|cerrado|cuándo)\b/i
  };
  
  for (const [intent, pattern] of Object.entries(patterns)) {
    if (pattern.test(message)) {
      intents.push(intent);
    }
  }
  
  return intents;
}

function searchProducts(query, products, threshold = 0.5) {
  if (!products || products.length === 0) return [];
  
  const queryWords = query.toLowerCase().split(/\s+/).filter(word => word.length > 2);
  
  return products
    .map(product => {
      let score = 0;
      const searchText = product.search_text || '';
      
      // Coincidencia exacta en título (alta puntuación)
      if (product.title.toLowerCase().includes(query.toLowerCase())) {
        score += 2;
      }
      
      // Coincidencias por palabra
      queryWords.forEach(word => {
        if (searchText.includes(word)) {
          score += 1;
        }
        if (product.title.toLowerCase().includes(word)) {
          score += 1.5;
        }
        if (product.category.toLowerCase().includes(word)) {
          score += 1;
        }
      });
      
      return { ...product, relevance_score: score };
    })
    .filter(product => product.relevance_score >= threshold)
    .sort((a, b) => b.relevance_score - a.relevance_score);
}

function getGeneralResponse(message, config) {
  const responses = [
    'Soy tu asistente especializado en productos de panadería. Puedo ayudarte a encontrar panes, pasteles, ingredientes y más. ¿Qué estás buscando específicamente?',
    'Estoy aquí para ayudarte con cualquier pregunta sobre nuestros productos. Puedo verificar precios, disponibilidad y darte recomendaciones. ¿En qué puedo asistirte?',
    'Como especialista en panadería, puedo ayudarte a encontrar exactamente lo que necesitas. ¿Te interesa algún producto en particular?'
  ];
  
  return responses[Math.floor(Math.random() * responses.length)];
}

function isBusinessHours(businessHours) {
  if (!businessHours.enabled) return true;
  
  const now = new Date();
  const timezone = businessHours.timezone || 'America/Mexico_City';
  const localTime = new Date(now.toLocaleString("en-US", {timeZone: timezone}));
  
  const day = localTime.toLocaleDateString('en-US', {weekday: 'lowercase'});
  const currentTime = localTime.toTimeString().slice(0, 5);
  
  const daySchedule = businessHours.schedule[day];
  
  if (!daySchedule || daySchedule.closed) {
    return false;
  }
  
  return currentTime >= daySchedule.open && currentTime <= daySchedule.close;
}

function getBusinessHoursMessage(businessHours) {
  const schedule = businessHours.schedule;
  let message = 'Nuestros horarios de atención son:\n';
  
  Object.entries(schedule).forEach(([day, hours]) => {
    const dayName = day.charAt(0).toUpperCase() + day.slice(1);
    if (hours.closed) {
      message += `${dayName}: Cerrado\n`;
    } else {
      message += `${dayName}: ${hours.open} - ${hours.close}\n`;
    }
  });
  
  return message.trim();
}

// === ENDPOINTS DE MONITOREO ===

router.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    shops_configured: shopConfigs.size,
    total_products: Array.from(shopProducts.values()).reduce((total, products) => total + products.length, 0)
  });
});

router.get('/stats/:shop', validateShopifyStore, (req, res) => {
  const products = shopProducts.get(req.shop) || [];
  const config = shopConfigs.get(req.shop);
  
  res.json({
    shop: req.shop,
    products_count: products.length,
    categories: [...new Set(products.map(p => p.category))],
    last_sync: config?.lastSyncAt || null,
    enabled: config?.enabled || false
  });
});

module.exports = router;


# --- NUEVOS ENDPOINTS PARA TIENDA CON CHATBOT ---




# --- ENDPOINTS DE LA API ---

@app.route('/api/health', methods=['GET'])
def health_check():
    """Endpoint para verificar el estado del servicio"""
    logger.debug("🔍 Solicitud de health check recibida")
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
        logger.info(f"📩 Datos de inicialización recibidos: {json.dumps(data) if data else 'Sin datos'}")

        # Validar datos de entrada
        if not data:
            logger.error("❌ Error: Solicitud sin datos JSON")
            return jsonify({
                "status": "error",
                "message": "Datos JSON requeridos"
            }), 400

        user_id = data.get('user_id')
        if not user_id:
            # Generar un user_id si no se proporciona
            user_id = f"user_{int(datetime.now().timestamp() * 1000)}" # Más específico con milisegundos
            logger.info(f"🆕 Generando user_id para nueva sesión: {user_id}")

        # Verificar si la sesión ya existe (opcional)
        # Si se permite reiniciar sesión, simplemente se sobreescribe

        # Crear historial de conversación
        conversation_history = ConversationHistory(user_id=user_id)
        sessions[user_id] = conversation_history # Almacenar en el diccionario de sesiones

        welcome_message = "¡Hola! 😊 Bienvenido a Masa Madre Monterrey.\n\nSoy tu asistente virtual y estoy aquí para ayudarte con todo lo relacionado con nuestros panes artesanales de masa madre. ¿En qué puedo ayudarte hoy? 🍞"

        logger.info(f"✅ Sesión iniciada para el usuario: {user_id}")
        return jsonify({
            "status": "success",
            "user_id": user_id,
            "message": "Sesión de chat iniciada",
            "welcome_message": welcome_message
        })

    except Exception as e:
        logger.critical(f"❌ Error crítico al iniciar sesión: {str(e)}", exc_info=True) # exc_info=True para stack trace
        return jsonify({
            "status": "error",
            "message": "Error interno del servidor al iniciar la sesión de chat"
        }), 500


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

        # --- NUEVO: Detección temprana de intención de hablar con humano ---
        # Definir patrones para intenciones específicas
        support_keywords = [
            "humano", "agente", "representante", "persona", "soporte", 
            "hablar con alguien", "quiero hablar", "contactar", "conectar",
            "asesor", "ayuda humana", "humano por favor", "humano ahora"
        ]
        
        # Verificar intención de soporte
        lower_message = message.lower()
        is_human_request = any(keyword in lower_message for keyword in support_keywords)
        # --- FIN NUEVO ---

        # --- GENERACIÓN DE RESPUESTA CON MANEJO DE ERRORES ---
        chatbot_response = None
        try:
            logger.info(f"🤖 Generando respuesta para user_id: {user_id}, mensaje: '{message[:50]}...'")
            # Pasar la bandera de intención detectada
            chatbot_response = generate_chatbot_response(
                query=message,
                user_id=user_id,
                conversation_history=conversation_history,
                detected_human_intent=is_human_request # Pasar la bandera
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
        provider_info = chatbot_response.get('provider', 'unknown')

        # Validar tipos
        if not isinstance(response_text, str):
            logger.warning(f"⚠️ 'response' no es string, es {type(response_text)}. Convirtiendo.")
            response_text = str(response_text)
        if not isinstance(sources_list, list):
            logger.warning(f"⚠️ 'sources' no es lista, es {type(sources_list)}. Convirtiendo.")
            sources_list = list(sources_list) if hasattr(sources_list, '__iter__') else []

        # --- NUEVO: Determinar la intención detectada para la respuesta ---
        # Priorizar la intención calculada en chat_api.py
        # Si semantic_search.py también la calcula, puedes usarla como fallback
        # Por ahora, usamos la calculada aquí.
        backend_detected_intent = "intent_to_handoff" if is_human_request else "general"
        # --- FIN NUEVO ---

        # Preparar respuesta para el frontend
        response_data = {
            "status": "success",
            "response": response_text,
            "sources": sources_list,
            "user_id": user_id,
            # --- NUEVO: Incluir señal explícita de intención ---
            "detected_intent": backend_detected_intent # Incluir la intención detectada
            # --- FIN NUEVO ---
        }

        logger.info(f"📤 Mensaje procesado y respuesta enviada para el usuario {user_id} (Intent: {backend_detected_intent})")
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

# En chat_api.py, modificar el endpoint /api/chat/support
@app.route('/api/chat/support', methods=['POST'])
def request_support():
    try:
        data = request.json
        logger.info(f"🆘 Solicitud de soporte recibida: {json.dumps(data) if data else 'Sin datos'}")

        if not data: 
            return jsonify({
                "status": "error",
                "message": "Datos JSON requeridos"
            }), 400

        user_id = data.get('user_id')
        contact_info = data.get('contact_info', {})  # Ahora es un objeto, no una cadena

        # Validaciones
        if not user_id or sessions.get(user_id) is None:
            return jsonify({
                "status": "error",
                "message": "Sesión no válida"
            }), 400

        # Validar que contact_info sea un objeto con los campos requeridos
        if not isinstance(contact_info, dict) or not all(k in contact_info for k in ['name', 'email', 'phone']):
            return jsonify({
                "status": "error",
                "message": "Información de contacto incompleta. Se requiere nombre, email y teléfono."
            }), 400

        # Obtener historial completo
        conversation_history = sessions[user_id]
        full_history = conversation_history.get_full_history()

        # Preparar datos para el ticket
        last_query = ""
        last_response = ""
        if full_history:
            last_exchange = full_history[-1]
            last_query = last_exchange.get('query', '')
            last_response = last_exchange.get('response', '')

        # Crear ticket de soporte
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
            
            logger.info(f"✅ Ticket de soporte creado: {ticket_id}")
            return jsonify({
                "status": "success",
                "message": f"✅ Hemos recibido tu solicitud. Tu número de folio es: {ticket_id}. Te contactaremos pronto en {contact_info['email']}.",
                "ticket_id": ticket_id
            })
            
        except ValueError as e:
            # Error de validación
            logger.warning(f"⚠️ Error de validación: {str(e)}")
            return jsonify({
                "status": "error",
                "message": str(e)
            }), 400
            
        except Exception as e:
            logger.error(f"❌ Error al crear ticket: {str(e)}")
            return jsonify({
                "status": "error",
                "message": "Error al procesar tu solicitud. Por favor, inténtalo de nuevo."
            }), 500

    except Exception as e:
        logger.critical(f"❌ Error crítico: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Error interno del servidor"
        }), 500


# --- PUNTO DE ENTRADA ---
if __name__ == "__main__":
    port = int(os.getenv('PORT', 5000))
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() in ('true', '1', 't')
    logger.info(f"🚀 Iniciando API del chatbot en el puerto {port} (Debug: {debug_mode})")
    app.run(host='0.0.0.0', port=port, debug=debug_mode) # Usar variable de entorno para debug

