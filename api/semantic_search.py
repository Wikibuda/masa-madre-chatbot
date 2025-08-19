#!/usr/bin/env python3
"""
Sistema de Búsqueda Semántica para Masa Madre Monterrey
- Integración con Claude para generación de respuestas
- Historial de conversación para contexto continuo
"""
# --- INICIO DE CAMBIOS: Eliminadas importaciones no esenciales para esta función pura ---
# Se eliminan imports relacionados con retroalimentación automática y soporte humano
# que se manejarán en otros niveles (API o frontend).
# --- FIN DE CAMBIOS ---

import os
import json
import logging
from dotenv import load_dotenv
from pinecone import Pinecone
from anthropic import Anthropic
from langchain.prompts import PromptTemplate
# conversation_history se sigue usando para contexto
# from conversation_history import ConversationHistory 
# feedback_system se sigue usando para registrar errores internos
# from feedback_system import record_feedback 
from mistralai import Mistral

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("semantic_search.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()

def get_pinecone_index():
    """Obtiene el índice de Pinecone para búsqueda semántica"""
    pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
    index_name = os.getenv('PINECONE_INDEX_NAME', 'masa-madre-products')
    # Usar Mistral para embeddings
    client = Mistral(api_key=os.getenv('MISTRAL_API_KEY'))
    
    class MistralEmbeddings:
        def embed_documents(self, texts):
            response = client.embeddings.create(
                model="mistral-embed",
                inputs=texts
            )
            return [data.embedding for data in response.data]
            
        def embed_query(self, text):
            response = client.embeddings.create(
                model="mistral-embed",
                inputs=[text]
            )
            return response.data[0].embedding
    
    # Crear índice de Pinecone
    index = pc.Index(index_name)
    return index, MistralEmbeddings()

def create_claude_qa_chain(conversation_history=None):
    """Crea una cadena de preguntas y respuestas usando Claude"""
    # Configurar template de prompt
    template = """Eres Pancho, un asistente virtual amigable, experto y entusiasta de la panadería artesanal con masa madre para Masa Madre Monterrey. Tu objetivo es ser útil, claro y directo.

**Instrucciones de Comportamiento:**

1.  **Personalidad y Tono:** Sé amable, profesional y entusiasta sobre la panadería. Usa emojis de forma moderada (😊, 🍞, 🙏). Evita ser excesivamente formal o promocional.
2.  **Claridad y Concisión:** Prioriza respuestas claras y directas. Evita bloques de texto muy largos. Usa viñetas o párrafos cortos cuando sea apropiado.
3.  **Uso de Información Recuperada ({context}):**
    *   Utiliza la información proporcionada en `{context}` para responder con precisión.
    *   Si la información en `{context}` no es relevante para la `{question}`, ignórala.
    *   Si no tienes información suficiente, admite honestamente que no la tienes o que verificarás.
4.  **Sugerencias de Productos/Servicios ({context}):**
    *   **Primera Interacción:** En la primera respuesta del día o sesión, puedes mencionar brevemente 1-2 productos o servicios destacados si es relevante o como ejemplo de lo que puedes ayudar.
    *   **Preguntas Explícitas:** Solo muestra sugerencias de productos/servicios cuando el usuario pregunte específicamente por ellos o cuando tu respuesta implique mencionar un producto/servicio específico del `{context}`.
    *   **Interacciones Posteriores:** En respuestas generales o de seguimiento, **no** agregues automáticamente una lista de sugerencias de productos/servicios. El enfoque debe estar en la pregunta del usuario.
5.  **Historial de Conversación ({conversation_context}):**
    *   Usa el `{conversation_context}` para mantener la coherencia y recordar puntos discutidos.
    *   No repitas información ya dada a menos que sea necesario para aclarar.
6.  **Derivación a Soporte Humano:**
    *   Reconoce solicitudes explícitas de hablar con un humano (ej: "quiero hablar con alguien", "agente", "humano", "representante", "soporte").
    *   **No** ofrezcas alternativas indirectas (redes sociales, WhatsApp). En su lugar, indica que puedes ayudar a conectarlo.
    *   **Acción:** Si detectas una solicitud de humano, responde con algo como: "Entiendo que prefieres hablar con alguien directamente. Estoy listo para ayudarte con eso. Por favor, ¿podrías dejarme tu correo electrónico o número de teléfono para que un representante se pueda poner en contacto contigo?" Luego, espera la información de contacto. (Este flujo requiere integración con el endpoint `/api/chat/support` del backend).
7.  **Ofertas y Promociones:**
    *   Solo menciona ofertas si son relevantes para la consulta o si se pregunta por productos en promoción.
8.  **Formato de Respuesta:**
    *   **Respuesta Principal:** El texto principal de tu respuesta.
    *   **(Opcional) Fuentes Relevantes:** Si mencionaste un producto o página específica del `{context}`, puedes incluir un enlace. Ejemplo:
        ```
        Puedes encontrar más detalles aquí: [Nombre del Producto](URL_del_producto)
        ```
    *   **No** agregues una sección fija de "Productos relacionados" a menos que sea una solicitud explícita.

**Consulta del cliente:** {question}

Respuesta:"""
    
    QA_CHAIN_PROMPT = PromptTemplate.from_template(template)
    
    # Configurar cliente Claude
    client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    
    def generate_response(prompt):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514", # Asegurar modelo correcto
                max_tokens=512,
                temperature=0.3,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Error al generar respuesta con Claude: {str(e)}")
            # Lanzar la excepción para que sea manejada por el nivel superior (API)
            raise Exception(f"Error al comunicarse con el servicio de IA: {str(e)}") from e

    # Obtener vector store
    index, embeddings = get_pinecone_index()
    
    def similarity_search(query, k=3):
        """Realiza búsqueda semántica y formatea los resultados"""
        # Generar embedding de la consulta
        query_embedding = embeddings.embed_query(query)
        
        # Buscar en Pinecone
        results = index.query(
            vector=query_embedding,
            top_k=k,
            include_metadata=True
        )
        
        # Formatear resultados
        documents = []
        for match in results['matches']:
            # Decodificar sale_info si existe
            sale_info = []
            if match['metadata'].get('sale_info'):
                try:
                    sale_info = json.loads(match['metadata']['sale_info'])
                except:
                    pass
            
            # Construir contenido alternativo
            content = f"Título: {match['metadata']['title']}\n"
            content += f"Categoría: {match['metadata']['category']}\n"
            content += f"Precio: {match['metadata']['price_range']}\n"
            content += f"Disponibilidad: {match['metadata']['availability']}\n"
            content += f"URL: {match['metadata']['source_url']}\n"
            
            # Formatear información de oferta
            sale_text = ""
            if match['metadata'].get('has_active_sale') == 'True' and sale_info:
                sale_text = "\n🔔 OFERTA VIGENTE: "
                for i, sale in enumerate(sale_info[:2], 1):
                    sale_text += f"\n{i}. {sale['variant_title']}: De ${sale['original_price']:.2f} a ${sale['current_price']:.2f} MXN ({sale['discount_percent']}% OFF)"
            
            # Crear documento con el contenido alternativo
            doc = {
                'page_content': content + sale_text,
                'metadata': {
                    'title': match['metadata']['title'],
                    'url': match['metadata']['source_url'],
                    'price_range': match['metadata']['price_range'],
                    'availability': match['metadata']['availability'],
                    'category': match['metadata']['category']
                }
            }
            documents.append(doc)
            
        return documents
    
    # Crear cadena de QA personalizada
    def qa_chain(query):
        # Recuperar documentos relevantes
        docs = similarity_search(query, k=3)
        
        # Formatear contexto
        context = "\n".join([doc['page_content'] for doc in docs])
        
        # Añadir historial de conversación si existe
        conversation_context = ""
        if conversation_history:
            conversation_context = conversation_history.get_context()
            
        # Crear prompt completo
        prompt = QA_CHAIN_PROMPT.format(
            context=context,
            conversation_context=conversation_context,
            question=query
        )
        
        # Obtener respuesta de Claude
        response = generate_response(prompt)
        
        # Añadir el intercambio al historial (CORRECCIÓN CLAVE)
        # Esta acción sigue siendo parte de la generación de la respuesta, ya que el historial
        # debe actualizarse con cada interacción.
        if conversation_history:
            conversation_history.add_exchange(query, response, docs)
            
        return {
            "result": response,
            "source_documents": docs
        }
        
    return qa_chain

# --- CAMBIO PRINCIPAL: generate_chatbot_response refactorizada ---
def generate_chatbot_response(query, user_id=None, conversation_history=None):
    """
    Genera una respuesta para el chatbot usando búsqueda semántica con Claude.
    Esta función se enfoca únicamente en generar la respuesta basada en la consulta.
    La interacción con el usuario (feedback, soporte) se maneja en otros niveles.

    Args:
        query (str): Consulta del usuario.
        user_id (str): ID único del usuario (opcional, para registro de errores).
        conversation_history (ConversationHistory): Historial existente (opcional).

    Returns:
        dict: Diccionario con 'response' (str), 'sources' (list[dict]) y 'provider' (str).

    Raises:
        Exception: Si ocurre un error durante la generación de la respuesta.
    """
    try:
        # Usar siempre Claude
        logger.info("✅ Usando Claude para generar respuesta")
        # No imprimir en consola, ya que no es un entorno interactivo
        # print("✅ Usando Claude para generar respuesta") # Eliminado

        qa_chain = create_claude_qa_chain(conversation_history=conversation_history)
        
        # Generar respuesta
        result = qa_chain(query)
        
        # Extraer información relevante
        response = result['result']
        sources = []
        for doc in result['source_documents']:
            metadata = doc['metadata']
            sources.append({
                'title': metadata.get('title', 'Producto sin título'),
                'url': metadata.get('url', ''),
                'price': metadata.get('price_range', 'Consultar'),
                'availability': metadata.get('availability', 'No disponible'),
                'category': metadata.get('category', 'otro')
            })
        
        # --- CAMBIO: Eliminadas todas las interacciones con el usuario ---
        # Se eliminan los print, input, y lógica de feedback/soporte automático.
        # Esta función ya no muestra respuestas, fuentes ni solicita feedback.
        # Esa lógica se mueve a la capa de la API (chat_api.py) o al frontend.
        # ---
        
        # Devolver los datos estructurados
        return {
            'response': response,
            'sources': sources,
            'provider': "claude"
            # conversation_history ya no se devuelve, se actualiza internamente
        }
        
    except Exception as e:
        error_msg = f"❌ Error interno al generar respuesta: {str(e)}"
        logger.error(error_msg)
        # No imprimir errores en consola
        # print(error_msg) # Eliminado
        
        # Registrar el error en el sistema de retroalimentación para diagnóstico
        # Esto es útil para el equipo de desarrollo, no para el usuario.
        try:
            # Importación local para evitar dependencias circulares si no se usan
            from feedback_system import record_feedback
            error_response_for_logging = (
                "Error interno del sistema al procesar la consulta. "
                "El equipo ha sido notificado."
            )
            record_feedback(
                query=query,
                response=error_response_for_logging,
                provider="claude",
                rating=1, # Calificación automática baja para errores
                user_comment=f"Error técnico interno: {str(e)}",
                session_id=user_id
            )
        except Exception as fb_error:
            logger.error(f"❌ Error al registrar retroalimentación de error interno: {str(fb_error)}")
            
        # Relanzar la excepción para que la API la maneje
        raise Exception("Lo siento, estoy teniendo problemas para procesar tu consulta. Por favor, inténtalo de nuevo más tarde.") from e

# --- FUNCIONES AUXILIARES (NUEVAS O REFACTORIZADAS) ---
# Estas funciones se pueden usar desde chat_api.py para lógica adicional si se requiere

def detect_user_difficulties(query, response, conversation_history):
    """
    (Nueva función) Analiza señales para determinar si el usuario podría estar teniendo dificultades.
    Esta lógica puede ser usada por la API para decidir si mostrar el widget de feedback.

    Args:
        query (str): La consulta del usuario.
        response (str): La respuesta generada.
        conversation_history (ConversationHistory): El historial de la conversación.

    Returns:
        dict: {'detected': bool, 'reason': str}
    """
    signals = []
    
    # Palabras clave que indican frustración
    frustration_keywords = [
        'no entiendo', 'repetir', 'no funciona', 'error', 'mal', 
        'incorrecto', 'frustrado', 'confundido', 'ayuda', 'problema'
    ]
    
    if any(keyword in query.lower() for keyword in frustration_keywords):
        signals.append("frustration_keyword_in_query")
        
    # Si la respuesta es muy corta (posible error o respuesta incompleta)
    if len(response) < 50:
        signals.append("short_response")
        
    # Si hay un historial y es largo, podría indicar dificultades
    history_length = len(conversation_history.get_full_history()) if conversation_history else 0
    if history_length > 4: # Por ejemplo, más de 4 interacciones
        signals.append("long_conversation")

    # Se podría añadir lógica para revisar historial de feedback negativo si se almacena
        
    detected = len(signals) > 0
    reason = ", ".join(signals) if signals else "no_signals"
    
    return {
        'detected': detected,
        'reason': reason
    }

# --- FUNCIONES MANTENIDAS (con posibles ajustes menores) ---

def search_products(query, top_k=3):
    """Busca productos relevantes usando Mistral y Pinecone"""
    # Inicializar Pinecone
    pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
    index = pc.Index(os.getenv('PINECONE_INDEX_NAME', 'masa-madre-products'))
    
    # Generar embedding con Mistral
    client = Mistral(api_key=os.getenv('MISTRAL_API_KEY'))
    response = client.embeddings.create(
        model="mistral-embed",
        inputs=[query]
    )
    query_embedding = response.data[0].embedding
    
    # Buscar en Pinecone
    results = index.query(
        vector=query_embedding,
        top_k=top_k,
        include_metadata=True
    )
    
    # Formatear resultados
    formatted_results = []
    for match in results['matches']:
        # Decodificar sale_info si existe
        sale_info = []
        if match['metadata'].get('sale_info'):
            try:
                sale_info = json.loads(match['metadata']['sale_info'])
            except:
                pass
                
        formatted_results.append({
            'id': match['id'],
            'score': match['score'],
            'metadata': {
                'title': match['metadata']['title'],
                'url': match['metadata']['source_url'],
                'price': match['metadata']['price_range'],
                'availability': match['metadata']['availability'],
                'sale_info': sale_info,
                'has_active_sale': match['metadata'].get('has_active_sale', 'False')
            }
        })
        
    return formatted_results

# --- FUNCIONES ELIMINADAS ---
# Las siguientes funciones se han eliminado o comentado porque su lógica se mueve:
# - `handle_feedback`: Su lógica se maneja en /api/chat/feedback
# - `verify_pinecone_connection`: Puede ser una utilidad separada o manejada por la API.
# - `should_show_feedback_widget`: Su lógica se mueve a `detect_user_difficulties`.
# - `handle_feedback_at_end`: Parte del flujo de interacción, no de generación.
# - `handle_human_support_request`: Su lógica se maneja en /api/chat/support.
# El bloque `if __name__ == "__main__":` también se elimina o se adapta para pruebas sin interactividad.

if __name__ == "__main__":
    # Bloque de prueba simplificado sin interacción
    print("Este módulo está diseñado para ser usado por la API.")
    print("Para pruebas, importa y llama a `generate_chatbot_response` directamente.")
    # Ejemplo de cómo podría usarse para pruebas (requiere mocks):
    # from conversation_history import ConversationHistory
    # history = ConversationHistory(user_id="test")
    # response = generate_chatbot_response("¿Tienen pan de calabaza?", "test_user", history)
    # print(response)

