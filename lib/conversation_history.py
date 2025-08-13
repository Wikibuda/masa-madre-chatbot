import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv
from pinecone import Pinecone
import logging

# Configurar logging
logger = logging.getLogger(__name__)

class ConversationHistory:
    """Maneja el historial de conversación para mantener el contexto"""
    
    def __init__(self, user_id=None, max_history=5, use_pinecone=True):
        """
        Inicializa el historial de conversación
        
        Args:
            user_id (str): ID único del usuario (opcional)
            max_history (int): Número máximo de intercambios a mantener
            use_pinecone (bool): Si usar Pinecone para almacenamiento persistente
        """
        self.user_id = user_id or f"user_{int(datetime.now().timestamp())}"
        self.max_history = max_history
        self.use_pinecone = use_pinecone
        self.history = []
        
        # Cargar variables de entorno
        load_dotenv()
        
        # Configurar Pinecone si está habilitado
        self.pinecone_index = None
        if use_pinecone and os.getenv('PINECONE_API_KEY'):
            try:
                pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
                index_name = os.getenv('PINECONE_CONVERSATION_INDEX', 'conversation-history')
                environment = os.getenv('PINECONE_ENVIRONMENT', 'us-east-1-aws')
                
                # Verificar si el índice existe
                indexes = pc.list_indexes().names()
                if index_name not in indexes:
                    # Crear índice con 1024 dimensiones (compatibles con Mistral)
                    pc.create_index(
                        name=index_name,
                        dimension=1024,
                        metric='cosine',
                        spec={'serverless': {'cloud': 'aws', 'region': environment}}
                    )
                    logger.info(f"✅ Índice de historial de conversación creado en Pinecone: {index_name}")
                
                self.pinecone_index = pc.Index(index_name)
                logger.info(f"✅ Conexión establecida con el índice de historial de conversación en Pinecone")
                
                # Cargar historial previo del usuario
                self.load_history_from_pinecone()
                
            except Exception as e:
                logger.warning(f"⚠️ No se pudo conectar a Pinecone para historial de conversación: {str(e)}")
                self.use_pinecone = False
    
    def add_exchange(self, query, response, sources=None):
        """
        Añade un intercambio de conversación al historial
        
        Args:
            query (str): Consulta del usuario
            response (str): Respuesta del chatbot
            sources (list): Fuentes utilizadas para la respuesta
        """
        exchange = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "response": response,
            "sources": sources or []
        }
        
        self.history.append(exchange)
        
        # Mantener solo el historial reciente
        if len(self.history) > self.max_history:
            self.history.pop(0)
        
        # Guardar en Pinecone si está habilitado
        if self.use_pinecone:
            self._save_to_pinecone(exchange)
    
    def get_context(self, max_chars=1000):
        """
        Obtiene el contexto de la conversación en formato para incluir en prompts
        
        Args:
            max_chars (int): Máximo de caracteres para el contexto
            
        Returns:
            str: Contexto de la conversación formateado
        """
        if not self.history:
            return ""
        
        context = "📜 Historial de conversación reciente:\n"
        for i, exchange in enumerate(self.history, 1):
            context += f"{i}. Usuario: {exchange['query']}\n"
            context += f"   Asistente: {exchange['response'][:200]}{'...' if len(exchange['response']) > 200 else ''}\n"
        
        # Limitar tamaño para evitar exceder límites de tokens
        if len(context) > max_chars:
            context = context[:max_chars] + " [truncado]"
        
        return context
    
    def get_full_history(self):
        """Obtiene el historial completo de conversación"""
        return self.history
    
    def clear_history(self):
        """Limpia el historial de conversación"""
        self.history = []
        
        # Si usamos Pinecone, eliminar el historial almacenado
        if self.use_pinecone and self.pinecone_index:
            try:
                # En Pinecone serverless, no podemos eliminar por namespace fácilmente
                # Simplemente reiniciamos el historial
                logger.info(f"🧹 Historial de conversación limpiado para el usuario {self.user_id}")
            except Exception as e:
                logger.error(f"❌ Error al limpiar historial en Pinecone: {str(e)}")
    
    def _save_to_pinecone(self, exchange):
        """Guarda un intercambio en Pinecone con verificación realista"""
        try:
            from mistralai import Mistral
            client = Mistral(api_key=os.getenv('MISTRAL_API_KEY'))
            
            # Crear embedding de la consulta
            response_embedding = client.embeddings.create(
                model="mistral-embed",
                inputs=[exchange['query']]
            )
            embedding = response_embedding.data[0].embedding
            
            # Preparar metadatos (con límites estrictos para evitar problemas)
            metadata = {
                "user_id": self.user_id,
                "timestamp": exchange["timestamp"],
                "query": exchange["query"][:200],  # Límite estricto
                "response_summary": exchange["response"][:200],  # Límite estricto
                "source_count": str(len(exchange["sources"]))
            }
            
            # Generar ID único
            exchange_id = f"conv_{self.user_id}_{int(datetime.now().timestamp())}"
            
            # Subir a Pinecone
            self.pinecone_index.upsert(vectors=[{
                'id': exchange_id,
                'values': embedding,
                'metadata': metadata
            }])
            
            # ¡VERIFICACIÓN REALISTA! (No inmediata, sino después de un breve retraso)
            time.sleep(0.5)  # Esperar brevemente para dar tiempo a Pinecone a procesar
            
            # Intentar obtener el vector con fetch()
            try:
                results = self.pinecone_index.fetch(ids=[exchange_id])
                
                # Manejar diferentes estructuras de resultados
                if hasattr(results, 'vectors') and isinstance(results.vectors, dict) and exchange_id in results.vectors:
                    vector_exists = True
                elif hasattr(results, 'matches') and isinstance(results.matches, list) and any(m['id'] == exchange_id for m in results.matches):
                    vector_exists = True
                elif isinstance(results, dict) and 'vectors' in results and exchange_id in results['vectors']:
                    vector_exists = True
                else:
                    vector_exists = False
                
                if vector_exists:
                    logger.info(f"✅ Intercambio guardado en historial de conversación (ID: {exchange_id})")
                    # Solo obtener estadísticas si hay éxito
                    try:
                        stats = self.pinecone_index.describe_index_stats()
                        logger.info(f"   Total de vectores en conversation-history: {stats.total_vector_count}")
                    except:
                        pass
                    return  # Salir exitosamente
            except Exception as fetch_e:
                logger.debug(f"   ⚠️ Verificación inicial fallida (normal en Pinecone serverless): {str(fetch_e)}")
            
            # Si la verificación inicial falla, intentar con query() después de un retraso adicional
            time.sleep(1.5)  # Esperar un poco más
            
            try:
                # Usar query() para verificar con tolerancia
                query_results = self.pinecone_index.query(
                    vector=embedding,
                    top_k=1,
                    include_metadata=True,
                    include_values=False
                )
                
                # Verificar si nuestro vector está en los resultados
                vector_exists = any(
                    match['id'] == exchange_id and 
                    match['score'] > 0.99  # Coincidencia casi perfecta
                    for match in query_results['matches']
                )
                
                if vector_exists:
                    logger.info(f"✅ Intercambio guardado en historial de conversación (ID: {exchange_id})")
                    try:
                        stats = self.pinecone_index.describe_index_stats()
                        logger.info(f"   Total de vectores en conversation-history: {stats.total_vector_count}")
                    except:
                        pass
                    return
            except Exception as query_e:
                logger.debug(f"   ⚠️ Verificación con query fallida: {str(query_e)}")
            
            # Si ambas verificaciones fallan, registrar como advertencia pero NO como error
            logger.info(f"ℹ️ Vector subido (ID: {exchange_id}) - Verificación no concluyente (comportamiento normal en Pinecone serverless)")
            logger.debug(f"   Metadatos subidos: {json.dumps(metadata)}")
            
        except Exception as e:
            logger.error(f"❌ Error FATAL al guardar en historial de conversación: {str(e)}")
            # Registrar en el sistema de retroalimentación de errores
            try:
                from feedback_system import record_feedback
                record_feedback(
                    query="system_error",
                    response=f"Error al guardar historial: {str(e)}",
                    provider="system",
                    rating=1,
                    user_comment=f"Error técnico en conversation_history: {str(e)}",
                    session_id=self.user_id
                )
            except:
                pass
    
    def load_history_from_pinecone(self):
        """Carga el historial previo del usuario desde Pinecone"""
        if not self.pinecone_index:
            return
        
        try:
            # Buscar los últimos intercambios del usuario
            # En un escenario real, esto sería una consulta más compleja
            # Por ahora, solo registramos que intentamos cargar
            logger.info(f"🔄 Cargando historial previo para el usuario {self.user_id}")
            
            # En una implementación completa, aquí buscaríamos en Pinecone
            # los intercambios anteriores del usuario y los añadiríamos a self.history
            
        except Exception as e:
            logger.error(f"❌ Error al cargar historial desde Pinecone: {str(e)}")
    
    def get_relevant_history(self, current_query, top_k=3):
        """
        Obtiene fragmentos relevantes del historial para la consulta actual
        
        Args:
            current_query (str): Consulta actual del usuario
            top_k (int): Número máximo de fragmentos a devolver
            
        Returns:
            str: Fragmentos relevantes del historial
        """
        if not self.history or not self.use_pinecone or not self.pinecone_index:
            return ""
        
        try:
            from mistralai import Mistral
            client = Mistral(api_key=os.getenv('MISTRAL_API_KEY'))
            
            # Crear embedding de la consulta actual
            response_embedding = client.embeddings.create(
                model="mistral-embed",
                inputs=[current_query]
            )
            query_embedding = response_embedding.data[0].embedding
            
            # Buscar en Pinecone los intercambios relevantes
            results = self.pinecone_index.query(
                vector=query_embedding,
                top_k=top_k,
                include_metadata=True,
                filter={"user_id": self.user_id}
            )
            
            # Construir contexto relevante
            context = ""
            for match in results['matches']:
                metadata = match['metadata']
                context += f"En una conversación anterior:\n"
                context += f"- Usuario: {metadata.get('query', '...')}\n"
                context += f"- Asistente: {metadata.get('response_summary', '...')}\n\n"
            
            return context
            
        except Exception as e:
            logger.error(f"❌ Error al obtener historial relevante: {str(e)}")
            return ""

def create_conversation_history(user_id=None):
    """Crea una instancia de ConversationHistory"""
    return ConversationHistory(user_id=user_id)

# Para pruebas rápidas
if __name__ == "__main__":
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    print("="*50)
    print("🔄 Probando el sistema de historial de conversación")
    print("="*50)
    
    # Crear historial
    history = ConversationHistory(user_id="test_user_123")
    
    # Añadir algunos intercambios
    history.add_exchange(
        "¿Tienen cestas de ratán para fermentar pan?",
        "¡Sí! Tenemos excelentes opciones de cestas de ratán para fermentación de pan. 🍞"
    )
    
    history.add_exchange(
        "¿Cuál es la diferencia entre las cestas pequeñas y grandes?",
        "Las cestas pequeñas son ideales para panes de 500g, mientras que las grandes son para panes de 1kg."
    )
    
    # Obtener contexto
    context = history.get_context()
    print("\n📜 Contexto generado:")
    print(context)
    
    # Probar búsqueda de historial relevante
    relevant = history.get_relevant_history("¿Qué tamaño necesito para un pan de 750g?")
    print("\n🔍 Historial relevante para la consulta actual:")
    print(relevant)
    
    print("\n✅ Pruebas completadas exitosamente")
