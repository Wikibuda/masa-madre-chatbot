import os
import json
import pandas as pd

#import pandas as pd
# Con esto:
try:
    import pandas as pd
except ImportError:
    pd = None
    print("⚠️ Pandas no está disponible. Funcionalidad de análisis limitada.")

from datetime import datetime
from dotenv import load_dotenv
from pinecone import Pinecone
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("feedback_system.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()


def initialize_feedback_system():
    """Inicializa el sistema de retroalimentación"""
    feedback_file = "chatbot_feedback.json"
    
    # Crear archivo si no existe
    if not os.path.exists(feedback_file):
        with open(feedback_file, 'w') as f:
            json.dump([], f)
        logger.info(f"✅ Archivo de retroalimentación creado: {feedback_file}")
    
    # Configurar Pinecone para almacenamiento adicional (opcional)
    pinecone_api_key = os.getenv('PINECONE_API_KEY')
    if pinecone_api_key:
        try:
            pc = Pinecone(api_key=pinecone_api_key)
            index_name = os.getenv('PINECONE_FEEDBACK_INDEX', 'chatbot-feedback')
            environment = os.getenv('PINECONE_ENVIRONMENT', 'us-east-1-aws')
            
            # Verificar si el índice existe
            indexes = pc.list_indexes().names()
            if index_name in indexes:
                # OBTENER INFORMACIÓN DEL ÍNDICE EXISTENTE
                index_info = pc.describe_index(index_name)
                
                # SOLO ELIMINAR SI LAS DIMENSIONES SON INCORRECTAS
                if index_info.dimension != 1024:
                    logger.info(f"🔄 Eliminando índice existente '{index_name}' (dimensiones incorrectas: {index_info.dimension} → 1024)...")
                    pc.delete_index(index_name)
                else:
                    logger.info(f"✅ Índice de retroalimentación ya existe con dimensiones correctas ({index_info.dimension})")
            else:
                logger.info(f"✅ Índice de retroalimentación no existe, se creará uno nuevo")
            
            # Si el índice no existe o fue eliminado, crearlo
            if index_name not in pc.list_indexes().names():
                pc.create_index(
                    name=index_name,
                    dimension=1024,
                    metric='cosine',
                    spec={'serverless': {'cloud': 'aws', 'region': environment}}
                )
                logger.info(f"✅ Índice de retroalimentación creado en Pinecone: {index_name} (1024 dimensiones)")
            
            index = pc.Index(index_name)
            logger.info(f"✅ Conexión establecida con el índice de retroalimentación en Pinecone")
            return {"file": feedback_file, "pinecone": index}
        except Exception as e:
            logger.error(f"❌ Error al conectar con Pinecone: {str(e)}")
            logger.error("   Verifica que tu PINECONE_ENVIRONMENT tenga el formato correcto")
            logger.error("   Para AWS: us-east-1-aws, us-west-2-aws, etc.")
            logger.error("   Para GCP: us-east1-gcp, us-west1-gcp, etc.")
    
    logger.info("✅ Sistema de retroalimentación inicializado (solo archivo local)")
    return {"file": feedback_file, "pinecone": None}


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
            # Generar embedding para la consulta (usando Mistral)
            from mistralai import Mistral
            client = Mistral(api_key=os.getenv('MISTRAL_API_KEY'))
            response_embedding = client.embeddings.create(
                model="mistral-embed",
                inputs=[query]
            )
            embedding = response_embedding.data[0].embedding
            
            # Preparar metadatos COMPATIBLES CON PINECONE
            metadata = {
                "timestamp": feedback_record["timestamp"],
                "query": query[:200],  # Limitar longitud
                "provider": provider,
                "rating": str(rating),  # Convertir a string
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


def analyze_feedback():
    """Analiza la retroalimentación acumulada y genera insights"""
    feedback_file = "chatbot_feedback.json"
    
    if not os.path.exists(feedback_file):
        logger.warning("⚠️ No hay retroalimentación registrada aún")
        return {
            "total_feedback": 0,
            "average_rating": 0,
            "feedback_by_provider": {},
            "common_issues": []
        }
    
    # Cargar datos
    with open(feedback_file, 'r') as f:
        feedback_data = json.load(f)
    
    total = len(feedback_data)
    
    if total == 0:
        return {
            "total_feedback": 0,
            "average_rating": 0,
            "feedback_by_provider": {},
            "common_issues": []
        }
    
    # Calcular promedio de calificaciones
    avg_rating = sum(item["rating"] for item in feedback_data) / total
    
    # Analizar por proveedor
    feedback_by_provider = {}
    for item in feedback_data:
        provider = item["provider"]
        if provider not in feedback_by_provider:
            feedback_by_provider[provider] = {"count": 0, "sum_rating": 0}
        feedback_by_provider[provider]["count"] += 1
        feedback_by_provider[provider]["sum_rating"] += item["rating"]
    
    for provider, data in feedback_by_provider.items():
        feedback_by_provider[provider]["avg_rating"] = data["sum_rating"] / data["count"]
    
    # Identificar problemas comunes a partir de comentarios
    low_rated = [item for item in feedback_data if item["rating"] <= 2]
    common_issues = []
    
    if low_rated:
        # Aquí podrías implementar análisis de texto más avanzado
        # Por ahora, simplemente recopilamos comentarios
        for item in low_rated:
            if item["comment"]:
                common_issues.append({
                    "query": item["query"],
                    "comment": item["comment"],
                    "rating": item["rating"]
                })
    
    # Generar reporte
    report = {
        "total_feedback": total,
        "average_rating": round(avg_rating, 2),
        "feedback_by_provider": feedback_by_provider,
        "common_issues": common_issues[:5]  # Mostrar máximo 5 problemas comunes
    }
    
    logger.info(f"\n📊 Reporte de Retroalimentación:\n"
                f"   Total de retroalimentación: {report['total_feedback']}\n"
                f"   Calificación promedio: {report['average_rating']}/5\n")
    
    for provider, data in report['feedback_by_provider'].items():
        logger.info(f"   - {provider.capitalize()}: {data['count']} respuestas, promedio {data['avg_rating']:.2f}/5")
    
    if report['common_issues']:
        logger.info("\n   🔍 Problemas comunes identificados:")
        for i, issue in enumerate(report['common_issues'], 1):
            logger.info(f"      {i}. '{issue['query']}' - {issue['comment'][:50]}{'...' if len(issue['comment']) > 50 else ''}")
    
    return report

def generate_improvement_suggestions():
    """Genera sugerencias específicas para mejorar el chatbot"""
    report = analyze_feedback()
    
    if report["total_feedback"] < 5:
        logger.info("⚠️ Se necesitan al menos 5 registros de retroalimentación para generar sugerencias útiles")
        return []
    
    suggestions = []
    
    # Sugerencia 1: Si el promedio es bajo
    if report["average_rating"] < 4.0:
        suggestions.append(
            "El promedio de calificación es bajo ({:.2f}/5). Considera revisar las respuestas más mal calificadas "
            "y ajustar el prompt del chatbot para mejorar la calidad de las respuestas.".format(report["average_rating"])
        )
    
    # Sugerencia 2: Comparación entre proveedores
    if len(report["feedback_by_provider"]) > 1:
        providers = list(report["feedback_by_provider"].keys())
        if report["feedback_by_provider"][providers[0]]["avg_rating"] > report["feedback_by_provider"][providers[1]]["avg_rating"]:
            better_provider = providers[0]
            worse_provider = providers[1]
        else:
            better_provider = providers[1]
            worse_provider = providers[0]
        
        suggestions.append(
            "El proveedor '{}' obtiene mejores calificaciones ({:.2f}/5) que '{} ({:.2f}/5). "
            "Considera usar '{}' como proveedor principal.".format(
                better_provider,
                report["feedback_by_provider"][better_provider]["avg_rating"],
                worse_provider,
                report["feedback_by_provider"][worse_provider]["avg_rating"],
                better_provider
            )
        )
    
    # Sugerencia 3: Basada en problemas comunes
    if report["common_issues"]:
        suggestions.append(
            "Se identificaron problemas comunes en consultas específicas. Revisa las consultas con calificación baja "
            "y ajusta el sistema de búsqueda semántica para mejorar los resultados en esos casos."
        )
    
    # Sugerencia 4: Si hay muchos comentarios negativos sobre información de productos
    low_rated = [item for item in report["common_issues"] if "producto" in item["comment"].lower() or "precio" in item["comment"].lower()]
    if len(low_rated) > len(report["common_issues"]) * 0.5:
        suggestions.append(
            "Varios usuarios reportaron problemas con información de productos. Considera actualizar el proceso de "
            "extracción de información para incluir más detalles relevantes de los productos."
        )
    
    # Sugerencia 5: Si hay muchos comentarios sobre respuestas demasiado largas/cortas
    length_issues = [item for item in report["common_issues"] if "largo" in item["comment"].lower() or "corto" in item["comment"].lower()]
    if len(length_issues) > len(report["common_issues"]) * 0.3:
        suggestions.append(
            "Algunos usuarios mencionaron que las respuestas son demasiado largas o cortas. Ajusta el parámetro "
            "'max_tokens' en la configuración del modelo para optimizar la longitud de las respuestas."
        )
    
    # Guardar sugerencias en un archivo
    with open("improvement_suggestions.txt", "w") as f:
        f.write(f"Reporte de Retroalimentación - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*70 + "\n\n")
        f.write(f"Total de retroalimentación: {report['total_feedback']}\n")
        f.write(f"Calificación promedio: {report['average_rating']}/5\n\n")
        
        f.write("Sugerencias para mejorar el chatbot:\n")
        for i, suggestion in enumerate(suggestions, 1):
            f.write(f"{i}. {suggestion}\n")
        
        if not suggestions:
            f.write("No se identificaron áreas críticas de mejora con los datos actuales.\n")
    
    logger.info(f"✅ {len(suggestions)} sugerencias de mejora generadas y guardadas en improvement_suggestions.txt")
    return suggestions


def record_conversation_feedback(conversation, rating, user_comment="", session_id=None):
    """
    Registra la retroalimentación para toda la conversación
    
    Args:
        conversation (list): Historial completo de la conversación
        rating (int): Calificación (1-5)
        user_comment (str): Comentario adicional del usuario
        session_id (str): ID de sesión opcional
    """
    feedback_system = initialize_feedback_system()
    
    # Crear registro de retroalimentación
    feedback_record = {
        "timestamp": datetime.now().isoformat(),
        "conversation_length": len(conversation),
        "first_query": conversation[0]["query"] if conversation else "",
        "last_query": conversation[-1]["query"] if conversation else "",
        "provider": "claude",
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
        
        logger.info(f"✅ Retroalimentación de conversación registrada: {rating}/5 estrellas")
    except Exception as e:
        logger.error(f"❌ Error al guardar retroalimentación de conversación: {str(e)}")
    
    # Guardar en Pinecone si está configurado
    if feedback_system["pinecone"]:
        try:
            # Generar embedding de la primera consulta
            if conversation:
                from mistralai import Mistral
                client = Mistral(api_key=os.getenv('MISTRAL_API_KEY'))
                response_embedding = client.embeddings.create(
                    model="mistral-embed",
                    inputs=[conversation[0]["query"]]
                )
                embedding = response_embedding.data[0].embedding
                
                # Preparar metadatos
                metadata = {
                    "timestamp": feedback_record["timestamp"],
                    "session_id": session_id or "",
                    "conversation_length": str(len(conversation)),
                    "rating": str(rating),
                    "has_comment": "true" if user_comment else "false"
                }
                
                # Añadir comentario si existe (limitado)
                if user_comment:
                    metadata["comment"] = user_comment[:100]
                
                # Subir a Pinecone
                feedback_id = f"conv_feedback_{int(datetime.now().timestamp())}"
                feedback_system["pinecone"].upsert(vectors=[{
                    'id': feedback_id,
                    'values': embedding,
                    'metadata': metadata
                }])
                
                logger.info(f"✅ Retroalimentación de conversación guardada en Pinecone (ID: {feedback_id})")
                
        except Exception as e:
            logger.error(f"❌ Error al guardar retroalimentación de conversación en Pinecone: {str(e)}")
    
    return feedback_record


def main():
    """Flujo principal para el sistema de retroalimentación"""
    logger.info("="*70)
    logger.info(f"🚀 Iniciando Sistema de Retroalimentación - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*70)
    
    # Inicializar sistema
    initialize_feedback_system()
    
    # Analizar retroalimentación existente
    analyze_feedback()
    
    # Generar sugerencias de mejora
    generate_improvement_suggestions()
    
    # Mostrar cómo integrar con el chatbot
    integrate_with_chatbot()
    
    logger.info("\n" + "="*70)
    logger.info("✅ Sistema de retroalimentación listo para integrarse con tu chatbot")
    logger.info("   Siguientes pasos:")
    logger.info("   1. Integra el widget de retroalimentación en tu interfaz de chat")
    logger.info("   2. Ejecuta este sistema periódicamente para analizar la retroalimentación")
    logger.info("   3. Implementa las sugerencias de mejora identificadas")
    logger.info("="*70)

if __name__ == "__main__":
    main()
