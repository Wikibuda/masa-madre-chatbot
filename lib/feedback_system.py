import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from pinecone import Pinecone

# Configurar logging
logger = logging.getLogger(__name__)

def initialize_feedback_system():
    """Inicializa el sistema de retroalimentación"""
    # Cargar variables de entorno
    load_dotenv()
    
    # Crear archivo de feedback si no existe
    feedback_file = "chatbot_feedback.json"
    if not os.path.exists(feedback_file):
        with open(feedback_file, 'w') as f:
            json.dump([], f)
        logger.info(f"✅ Archivo de retroalimentación creado: {feedback_file}")
    
    # Configurar Pinecone si está habilitado
    pinecone_client = None
    if os.getenv('PINECONE_API_KEY') and os.getenv('FEEDBACK_PINECONE_ENABLED', 'true').lower() == 'true':
        try:
            pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
            index_name = os.getenv('PINECONE_FEEDBACK_INDEX', 'chatbot-feedback')
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
                logger.info(f"✅ Índice de retroalimentación creado en Pinecone: {index_name}")
            
            pinecone_client = pc.Index(index_name)
            logger.info(f"✅ Conexión establecida con el índice de retroalimentación en Pinecone")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo conectar a Pinecone para retroalimentación: {str(e)}")
    
    return {
        "file": feedback_file,
        "pinecone": pinecone_client
    }

def record_feedback(query, response, provider, rating, user_comment="", session_id=None):
    """
    Registra la retroalimentación del usuario
    
    Args:
        query: Consulta del usuario
        response: Respuesta del chatbot
        provider: Proveedor usado (claude)
        rating: Calificación (1-5)
        user_comment: Comentario adicional del usuario
        session_id: ID de sesión opcional para agrupar interacciones
    """
    feedback_system = initialize_feedback_system()
    
    # Crear registro de retroalimentación
    feedback_record = {
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "response": response,
        "provider": provider,
        "rating": rating,
        "comment": user_comment,
        "session_id": session_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    }
    
    # Guardar en archivo JSON
    try:
        with open(feedback_system["file"], 'r') as f:
            feedback_data = json.load(f)
        
        feedback_data.append(feedback_record)
        
        with open(feedback_system["file"], 'w') as f:
            json.dump(feedback_data, f, indent=2)
        
        logger.info(f"✅ Retroalimentación registrada: {rating}/5 estrellas")
    except Exception as e:
        logger.error(f"❌ Error al guardar retroalimentación en archivo: {str(e)}")
    
    # Guardar en Pinecone si está configurado
    if feedback_system["pinecone"]:
        try:
            # Generar embedding para la consulta
            from mistralai import Mistral
            client = Mistral(api_key=os.getenv('MISTRAL_API_KEY'))
            response_embedding = client.embeddings.create(
                model="mistral-embed",
                inputs=[query]
            )
            embedding = response_embedding.data[0].embedding
            
            # Preparar metadatos
            metadata = {
                "timestamp": feedback_record["timestamp"],
                "query": query[:200],
                "provider": provider,
                "rating": str(rating),
                "has_comment": "true" if user_comment else "false"
            }
            
            # Añadir comentario si existe (limitado)
            if user_comment:
                metadata["comment"] = user_comment[:100]
            
            # Subir a Pinecone
            feedback_id = f"feedback_{int(datetime.now().timestamp())}"
            feedback_system["pinecone"].upsert(vectors=[{
                'id': feedback_id,
                'values': embedding,
                'metadata': metadata
            }])
            
            # Verificar que se subió correctamente
            results = feedback_system["pinecone"].fetch(ids=[feedback_id])
            if feedback_id in results.vectors:
                logger.info(f"✅ Retroalimentación guardada en Pinecone (ID: {feedback_id})")
                # Obtener estadísticas actualizadas
                stats = feedback_system["pinecone"].describe_index_stats()
                logger.info(f"   Total de vectores en Pinecone: {stats.total_vector_count}")
            else:
                logger.warning("⚠️ Vector subido pero no se puede recuperar (verifica los metadatos)")
                
        except Exception as e:
            logger.error(f"❌ Error al guardar retroalimentación en Pinecone: {str(e)}")
    
    return feedback_record


def get_feedback_summary():
    """
    Obtiene un resumen básico de la retroalimentación sin usar pandas
    """
    feedback_system = initialize_feedback_system()
    
    try:
        with open(feedback_system["file"], 'r') as f:
            feedback_data = json.load(f)
        
        if not feedback_data:  # ✅ CORRECCIÓN: feedback_data en lugar de feedback_
            return {
                "total_feedback": 0,
                "average_rating": 0,
                "low_ratings": 0,
                "recent_feedback": []
            }
        
        # Cálculos básicos sin pandas
        total = len(feedback_data)
        sum_ratings = sum(item["rating"] for item in feedback_data)
        average = sum_ratings / total
        low_ratings = sum(1 for item in feedback_data if item["rating"] <= 2)
        
        # Obtener feedback reciente (últimos 5)
        recent = feedback_data[-5:][::-1]  # Últimos 5, ordenados de más reciente a más antiguo
        
        return {
            "total_feedback": total,
            "average_rating": round(average, 2),
            "low_ratings": low_ratings,
            "low_ratings_percentage": round((low_ratings / total) * 100, 1),
            "recent_feedback": [{
                "timestamp": item["timestamp"],
                "rating": item["rating"],
                "comment": item["comment"][:100] + "..." if len(item["comment"]) > 100 else item["comment"]
            } for item in recent]
        }
    except Exception as e:
        logger.error(f"❌ Error al obtener resumen de retroalimentación: {str(e)}")
        return {
            "total_feedback": 0,
            "average_rating": 0,
            "low_ratings": 0,
            "recent_feedback": []
        }
