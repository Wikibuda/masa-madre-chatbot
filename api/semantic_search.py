#!/usr/bin/env python3
"""
Sistema de Búsqueda Semántica para Masa Madre Monterrey
- Integración con Claude para generación de respuestas
- Historial de conversación para contexto continuo
- Sistema de retroalimentación para mejora continua
"""

import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from pinecone import Pinecone
from anthropic import Anthropic
from langchain.prompts import PromptTemplate
from conversation_history import ConversationHistory
from feedback_system import record_feedback
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
    template = """Eres un asistente de panadería especializado en masa madre para Masa Madre Monterrey.
Basándote en la siguiente información, responde a la consulta del cliente de manera útil, amable y profesional.
Si no estás seguro de algo, indica que verificarás la información.

{context}

{conversation_context}

Consulta del cliente: {question}

Respuesta:"""
    
    QA_CHAIN_PROMPT = PromptTemplate.from_template(template)
    
    # Configurar cliente Claude
    client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    
    def generate_response(prompt):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=512,
                temperature=0.3,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Error al generar respuesta con Claude: {str(e)}")
            return "Lo siento, estoy teniendo problemas para procesar tu consulta. Por favor, inténtalo de nuevo más tarde."
    
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
                sale_text = "\n\n🔔 OFERTA VIGENTE: "
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
        context = "\n\n".join([doc['page_content'] for doc in docs])
        
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
        if conversation_history:
            conversation_history.add_exchange(query, response, docs)
        
        return {
            "result": response,
            "source_documents": docs
        }
    
    return qa_chain

def generate_chatbot_response(query, user_id=None, conversation_history=None):
    """
    Genera una respuesta para el chatbot usando búsqueda semántica con Claude
    
    Args:
        query (str): Consulta del usuario
        user_id (str): ID único del usuario (opcional)
        conversation_history (ConversationHistory): Historial existente (opcional)
    
    Returns:
        dict: Diccionario con la respuesta, fuentes y proveedor utilizado
    """
    try:
        # Usar el historial proporcionado o crear uno nuevo
        if conversation_history is None:
            conversation_history = ConversationHistory(user_id=user_id)
        
        # Usar siempre Claude
        logger.info("✅ Usando Claude para generar respuesta")
        print("✅ Usando Claude para generar respuesta")
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
        
        # Mostrar la respuesta al usuario
        print("\n" + "="*50)
        print(f"🤖 Respuesta del chatbot:")
        print(f"\n{response}\n")
        
        # Mostrar fuentes utilizadas
        print("Fuentes utilizadas:")
        for i, source in enumerate(sources, 1):
            print(f"\n{i}. {source['title']}")
            print(f"   Categoría: {source['category']}")
            print(f"   Precio: {source['price']}")
            print(f"   Disponibilidad: {source['availability']}")
            print(f"   URL: {source['url']}")
        
        # Retroalimentación discreta - MUY IMPORTANTE: No interrumpe el flujo
        print("\n¿Esta respuesta fue útil? 👍 👎  (responde con estos emojis)")
        
        # Verificar si el usuario respondió con emojis de retroalimentación
        if query.strip() in ["👍", "👎"]:
            rating = 5 if query.strip() == "👍" else 1
            record_feedback(
                query=conversation_history.get_full_history()[-2]['query'],
                response=conversation_history.get_full_history()[-2]['response'],
                provider="claude",
                rating=rating,
                user_comment="",
                session_id=user_id
            )
            print(f"✅ ¡Gracias por tu retroalimentación! ({'5 estrellas' if rating == 5 else '1 estrella'})")
        
        # Verificar si el usuario solicita soporte humano
        elif "agente" in query.lower() or "humano" in query.lower() or "representante" in query.lower():
            print("\n" + "="*50)
            print("🔄 Conectando con un agente humano...")
            print("Un representante se pondrá en contacto contigo en breve.")
            print("Mientras tanto, ¿podrías compartir tu correo electrónico o número de teléfono?")
            contact_info = input("Tu información de contacto: ")
            
            # Determinar prioridad
            priority = "alta" if "urgente" in query.lower() or "rapido" in query.lower() else "media"
            
            # Registrar en un sistema de tickets
            try:
                from support_system import create_support_ticket
                create_support_ticket(
                    query=query,
                    response=response,
                    conversation_history=conversation_history.get_full_history(),
                    contact_info=contact_info,
                    priority=priority,
                    reason="Solicitud de soporte humano por el usuario"
                )
                print("✅ Ticket de soporte creado. Un representante se contactará contigo pronto.")
            except Exception as e:
                logger.error(f"❌ Error al crear ticket de soporte: {str(e)}")
                print("⚠️ Hubo un problema al crear tu ticket. Por favor, contacta directamente a soporte@masamadremonterrey.com")
        
        # Verificar si debe mostrarse el widget detallado (solo en casos específicos)
        else:
            # Palabras clave que indican frustración
            frustration_keywords = [
                'no entiendo', 'repetir', 'no funciona', 'error', 'mal', 
                'incorrecto', 'frustrado', 'confundido', 'ayuda', 'soporte',
                'agente', 'humano', 'representante', 'no sirve'
            ]
            
            # Verificar si hay señales de frustración
            should_show = False
            if any(keyword in query.lower() for keyword in frustration_keywords):
                should_show = True
            
            # Si el usuario ha hecho más de 3 preguntas sin resolver su problema
            elif len(conversation_history.get_full_history()) > 3:
                should_show = True
            
            # Si la última respuesta fue muy corta (posible error)
            elif len(response) < 50:
                should_show = True
            
            # Si el usuario calificó negativamente antes
            elif any(ex.get('feedback_rating', 5) < 3 for ex in conversation_history.get_full_history()):
                should_show = True
            
            # Mostrar widget detallado si se cumplen las condiciones
            if should_show:
                print("\n" + "="*50)
                print("🙏 Notamos que estás teniendo dificultades. ¿Te gustaría calificar esta conversación para ayudarnos a mejorar?")
                print("1. Muy útil (5 estrellas)")
                print("2. Útil (4 estrellas)")
                print("3. Neutral (3 estrellas)")
                print("4. Poco útil (2 estrellas)")
                print("5. No útil (1 estrella)")
                
                try:
                    rating_input = input("Califica (1-5, Enter para omitir): ")
                    if rating_input.strip():
                        rating = int(rating_input)
                        if 1 <= rating <= 5:
                            comment = input("Comentarios adicionales: ")
                            # Registrar retroalimentación
                            record_feedback(
                                query=query,
                                response=response,
                                provider="claude",
                                rating=rating,
                                user_comment=comment,
                                session_id=user_id
                            )
                            print("✅ ¡Gracias por tu retroalimentación!")
                        else:
                            print("⚠️  Calificación inválida. Debe ser un número entre 1 y 5.")
                except ValueError:
                    print("⚠️  Entrada inválida. Se requiere un número entre 1 y 5.")
        
        # Devolver los datos
        return {
            'response': response,
            'sources': sources,
            'provider': "claude",
            'conversation_history': conversation_history
        }
    
    except Exception as e:
        error_msg = f"❌ Error al generar respuesta: {str(e)}"
        logger.error(error_msg)
        print(error_msg)
        
        # Mostrar mensaje de error al usuario
        error_response = (
            "Lo siento, estoy teniendo problemas para procesar tu consulta. "
            "Por favor, inténtalo de nuevo más tarde."
        )
        print("\n" + "="*50)
        print(f"🤖 Respuesta del chatbot (error):")
        print(f"\n{error_response}\n")
        
        # Registrar el error en el sistema de retroalimentación
        try:
            record_feedback(
                query=query,
                response=error_response,
                provider="claude",
                rating=1,
                user_comment=f"Error técnico: {str(e)}",
                session_id=user_id
            )
        except Exception as fb_error:
            logger.error(f"❌ Error al registrar retroalimentación de error: {str(fb_error)}")
        
        return {
            'response': error_response,
            'sources': [],
            'provider': "claude"
        }


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

def handle_feedback(query, chatbot_response, user_id):
    """Maneja la retroalimentación del usuario de manera separada"""
    print("\n" + "="*50)
    print("🔍 ¿Te fue útil esta respuesta?")
    print("1. 👍 Muy útil (5 estrellas)")
    print("2. 👍 Útil (4 estrellas)")
    print("3. 👍 Neutral (3 estrellas)")
    print("4. 👎 Poco útil (2 estrellas)")
    print("5. 👎 No útil (1 estrella)")
    
    try:
        rating_input = input("Selecciona una opción (1-5, o presiona Enter para omitir): ")
        if rating_input.strip():
            rating = int(rating_input)
            if 1 <= rating <= 5:
                comment = input("Comentario adicional (opcional): ")
                # Registrar retroalimentación
                record_feedback(
                    query=query,
                    response=chatbot_response['response'],
                    provider="claude",
                    rating=rating,
                    user_comment=comment,
                    session_id=user_id
                )
                print("✅ ¡Gracias por tu retroalimentación!")
            else:
                print("⚠️  Calificación inválida. Debe ser un número entre 1 y 5.")
    except ValueError:
        print("⚠️  Entrada inválida. Se requiere un número entre 1 y 5.")

def verify_pinecone_connection():
    """Verifica la conexión con Pinecone para monitoreo en producción"""
    try:
        from conversation_history import ConversationHistory
        test_history = ConversationHistory(user_id="test_connection")
        
        # Intentar subir un vector de prueba
        test_history.add_exchange(
            "Consulta de prueba",
            "Respuesta de prueba para verificar conexión con Pinecone",
            []
        )
        
        # Verificar estadísticas
        if test_history.pinecone_index:
            stats = test_history.pinecone_index.describe_index_stats()
            logger.info(f"📊 Verificación de Pinecone exitosa. Total de vectores: {stats.total_vector_count}")
            return True
        
        logger.warning("⚠️ No hay conexión con Pinecone (funcionalidad de historial deshabilitada)")
        return False
        
    except Exception as e:
        logger.error(f"❌ Error al verificar conexión con Pinecone: {str(e)}")
        return False

def should_show_feedback_widget(query, response, conversation_history):
    """Determina si debe mostrarse el widget de retroalimentación detallada"""
    # Palabras clave que indican frustración
    frustration_keywords = [
        'no entiendo', 'repetir', 'no funciona', 'error', 'mal', 
        'incorrecto', 'frustrado', 'confundido', 'ayuda', 'soporte',
        'agente', 'humano', 'representante', 'no sirve'
    ]
    
    # Verificar si hay señales de frustración en la consulta actual
    if any(keyword in query.lower() for keyword in frustration_keywords):
        return True
    
    # Si el usuario ha hecho más de 3 preguntas sin resolver su problema
    if len(conversation_history.get_full_history()) > 3:
        return True
    
    # Si la última respuesta fue muy corta (posible error)
    if len(response) < 50:
        return True
    
    # Si el usuario calificó negativamente antes
    recent_feedback = [ex for ex in conversation_history.get_full_history() 
                      if 'feedback_rating' in ex]
    if recent_feedback and min(r['feedback_rating'] for r in recent_feedback) < 3:
        return True
    
    return False


def handle_feedback_at_end(user_id, conversation_history):
    """Muestra un widget de retroalimentación simple al final de la conversación"""
    if not conversation_history or not conversation_history.get_full_history():
        return
    
    # Detectar si el usuario está terminando la conversación
    last_query = conversation_history.get_full_history()[-1]['query'].lower()
    if any(phrase in last_query for phrase in ["gracias", "adiós", "adios", "hasta luego", "chao", "salir", "exit", "quit"]):
        print("\n" + "="*50)
        print("🙏 ¡Gracias por usar nuestro asistente de panadería!")
        print("¿Fue útil esta conversación? Responde con 1-5 estrellas")
        
        try:
            rating_input = input("Calificación (1-5): ")
            if rating_input.strip():
                rating = int(rating_input)
                if 1 <= rating <= 5:
                    # Registrar retroalimentación para toda la conversación
                    from feedback_system import record_conversation_feedback
                    record_conversation_feedback(
                        conversation=conversation_history.get_full_history(),
                        rating=rating,
                        user_comment="",
                        session_id=user_id
                    )
                    print("✅ ¡Gracias por tu retroalimentación!")
                else:
                    print("⚠️  Calificación inválida. Debe ser un número entre 1 y 5.")
        except ValueError:
            print("⚠️  Entrada inválida. Se requiere un número entre 1 y 5.")

def handle_human_support_request(query, response, conversation_history, user_id):
    """Gestiona la solicitud de soporte humano"""
    print("\n" + "="*50)
    print("🔄 Conectando con un agente humano...")
    print("Un representante se pondrá en contacto contigo en breve.")
    print("Mientras tanto, ¿podrías compartir tu correo electrónico o número de teléfono?")
    contact_info = input("Tu información de contacto: ")
    
    # Determinar prioridad
    priority = "alta" if "urgente" in query.lower() or "rapido" in query.lower() else "media"
    
    # Registrar en un sistema de tickets
    try:
        from support_system import create_support_ticket
        create_support_ticket(
            query=query,
            response=response,
            conversation_history=conversation_history.get_full_history(),
            contact_info=contact_info,
            priority=priority,
            reason="Solicitud de soporte humano por el usuario"
        )
        print("✅ Ticket de soporte creado. Un representante se contactará contigo pronto.")
    except Exception as e:
        logger.error(f"❌ Error al crear ticket de soporte: {str(e)}")
        print("⚠️ Hubo un problema al crear tu ticket. Por favor, contacta directamente a soporte@masamadremonterrey.com")

if __name__ == "__main__":
    # Configuración inicial
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
    
    # Obtener ID del usuario (en producción vendría de la sesión web)
    user_id = input("Ingresa tu ID de usuario (o presiona Enter para uno temporal): ").strip()
    if not user_id:
        user_id = f"user_{int(datetime.now().timestamp())}"
    
    print(f"\n👋 ¡Hola! Soy tu asistente de panadería especializado en masa madre.")
    print(f"Tu ID de sesión: {user_id}")
    print("Escribe 'salir' para terminar la conversación.\n")
    
    # Inicializar historial de conversación
    conversation_history = ConversationHistory(user_id=user_id)
    
    # Bucle de conversación PRINCIPAL
    while True:
        # Solicitar consulta
        query = input("🔍 Tu consulta: ").strip()
        
        if not query:
            continue
            
        # Manejar comandos especiales de salida
        if query.lower() in ['salir', 'exit', 'quit', 'adiós', 'adios', 'gracias']:
            # Manejar retroalimentación al final
            if len(conversation_history.get_full_history()) > 1:
                print("\n" + "="*50)
                print("🙏 ¡Gracias por usar nuestro asistente de panadería!")
                print("¿Fue útil esta conversación? Responde con 1-5 estrellas")
                
                try:
                    rating_input = input("Calificación (1-5): ")
                    if rating_input.strip():
                        rating = int(rating_input)
                        if 1 <= rating <= 5:
                            from feedback_system import record_conversation_feedback
                            record_conversation_feedback(
                                conversation=conversation_history.get_full_history(),
                                rating=rating,
                                user_comment="",
                                session_id=user_id
                            )
                            print("✅ ¡Gracias por tu retroalimentación!")
                        else:
                            print("⚠️  Calificación inválida. Debe ser un número entre 1 y 5.")
                except ValueError:
                    print("⚠️  Entrada inválida. Se requiere un número entre 1 y 5.")
            
            print("\n👋 ¡Hasta luego! No dudes en volver si tienes más preguntas.")
            break
        
        # Mostrar resultados de búsqueda semántica
        print(f"🔍 Consulta: '{query}'\n")
        
        print("📝 Resultados de búsqueda semántica:")
        try:
            results = search_products(query)
            for i, result in enumerate(results, 1):
                print(f"\n{i}. {result['metadata']['title']}")
                print(f"   Similitud: {result['score']:.4f}")
                print(f"   Precio: {result['metadata']['price']}")
                print(f"   Disponibilidad: {result['metadata']['availability']}")
                
                # Mostrar información de oferta si existe
                if result['metadata']['has_active_sale'] == 'True' and result['metadata']['sale_info']:
                    print("   🎁 Oferta:")
                    for sale in result['metadata']['sale_info'][:2]:
                        print(f"      - {sale['variant_title']}: ${sale['original_price']:.2f} → ${sale['current_price']:.2f} ({sale['discount_percent']}% OFF)")
                
                print(f"   URL: {result['metadata']['url']}")
        except Exception as e:
            logger.error(f"❌ Error al realizar búsqueda semántica: {str(e)}")
            print("⚠️  Hubo un problema al buscar productos relacionados. Continuando con la generación de respuesta...")
        
        # Generar respuesta con historial
        try:
            chatbot_response = generate_chatbot_response(
                query, 
                user_id=user_id,
                conversation_history=conversation_history
            )
            
            # Actualizar historial de conversación
            if 'conversation_history' in chatbot_response:
                conversation_history = chatbot_response['conversation_history']
        except Exception as e:
            logger.error(f"❌ Error al generar respuesta del chatbot: {str(e)}")
            print("\n" + "="*50)
            print("🤖 Respuesta del chatbot (error):")
            print("\nLo siento, estoy teniendo problemas para procesar tu consulta. Por favor, inténtalo de nuevo más tarde.")
            
            # Registrar error en el historial
            conversation_history.add_exchange(
                query,
                "Error técnico - Consulta no procesada",
                []
            )
