# support_system.py
import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
# Importar Header para manejar codificación UTF-8 en correos
from email.header import Header 
from datetime import datetime
import logging
from dotenv import load_dotenv

# Configurar logging
logger = logging.getLogger(__name__)

def initialize_support_system():
    """Inicializa el sistema de soporte"""
    # Cargar variables de entorno
    load_dotenv()
    
    # Crear archivo de tickets si no existe
    tickets_file = "support_tickets.json"
    if not os.path.exists(tickets_file):
        with open(tickets_file, 'w') as f:
            json.dump([], f)
        logger.info(f"✅ Archivo de tickets creado: {tickets_file}")
    
    # Configurar notificaciones por correo
    email_enabled = bool(os.getenv('SUPPORT_EMAIL_ENABLED', 'false').lower() == 'true')
    if email_enabled:
        logger.info("✅ Notificaciones por correo habilitadas para el sistema de soporte")
    else:
        logger.info("ℹ️ Notificaciones por correo deshabilitadas (SUPPORT_EMAIL_ENABLED = false)")
    
    return {
        "tickets_file": tickets_file,
        "email_enabled": email_enabled
    }

def create_support_ticket(query, response, conversation_history, contact_info, priority, reason):
    """
    Crea un ticket de soporte
    
    Args:
        query (str): Consulta del usuario
        response (str): Última respuesta del chatbot
        conversation_history (list): Historial completo de la conversación
        contact_info (str): Información de contacto del usuario
        priority (str): Prioridad del ticket ("alta", "media", "baja")
        reason (str): Razón de la derivación
    
    Returns:
        str: El ID del ticket creado (e.g., "TICKET-1234567890")
    """
    support_system = initialize_support_system()
    
    # Generar el ID del ticket primero para usarlo en logs y posibles errores
    ticket_id = f"TICKET-{int(datetime.now().timestamp())}"
    
    # Crear ticket como diccionario
    ticket = {
        "ticket_id": ticket_id, # Usar el ID generado
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "last_response": response,
        "conversation_history": conversation_history,
        "contact_info": contact_info,
        "priority": priority,
        "reason": reason,
        "status": "abierto"
    }
    
    # Guardar en archivo
    try:
        # Leer tickets existentes
        try:
            with open(support_system["tickets_file"], 'r') as f:
                tickets = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # Si el archivo no existe o está corrupto, empezar con una lista vacía
            tickets = []
            logger.info(f"Archivo de tickets no encontrado o vacío. Creando uno nuevo: {support_system['tickets_file']}")
        
        # Añadir el nuevo ticket
        tickets.append(ticket)
        
        # Guardar la lista actualizada
        with open(support_system["tickets_file"], 'w') as f:
            json.dump(tickets, f, indent=2, ensure_ascii=False) # ensure_ascii=False para caracteres especiales
        
        logger.info(f"✅ Ticket creado: {ticket['ticket_id']} (Prioridad: {priority})")
        
    except Exception as e:
        error_msg = f"❌ Error al guardar ticket {ticket_id}: {str(e)}"
        logger.error(error_msg)
        # Dependiendo de la política, podrías relanzar la excepción
        # para que el backend la capture y maneje adecuadamente.
        # raise Exception(error_msg) 
        
    # Enviar notificación por correo si está habilitado
    if support_system.get("email_enabled", False): # Uso de .get para evitar KeyError
        try:
            send_support_notification(ticket)
        except Exception as e:
            logger.error(f"❌ Error al enviar notificación por correo para ticket {ticket_id}: {str(e)}")
            # No se relanza esta excepción para no romper la creación del ticket por fallo de email
    
    # --- CAMBIO CLAVE: Devolver solo el ID del ticket como string ---
    # El backend (chat_api.py) espera un identificador simple.
    return ticket_id
    # --- FIN CAMBIO CLAVE ---

def send_support_notification(ticket):
    """Envía una notificación por correo al equipo de soporte"""
    load_dotenv()
    
    # Configuración del correo
    sender_email = os.getenv('SUPPORT_EMAIL_SENDER')
    receiver_email = os.getenv('SUPPORT_EMAIL_RECIPIENT')
    smtp_server = os.getenv('SUPPORT_EMAIL_SMTP_SERVER')
    smtp_port = int(os.getenv('SUPPORT_EMAIL_SMTP_PORT', 587))
    smtp_user = os.getenv('SUPPORT_EMAIL_USER')
    smtp_password = os.getenv('SUPPORT_EMAIL_PASSWORD')
    
    # Verificar que las credenciales estén configuradas
    if not all([sender_email, receiver_email, smtp_server, smtp_user, smtp_password]):
        logger.warning("⚠️ Configuración de correo incompleta. No se enviará notificación.")
        return

    # Crear mensaje
    subject = f"[{ticket['priority'].upper()}] Nuevo ticket de soporte - {ticket['ticket_id']}"
    
    # Formatear historial de conversación
    conversation_text = ""
    for i, exchange in enumerate(ticket['conversation_history'], 1):
        conversation_text += f"{i}. Usuario: {exchange['query']}\n"
        conversation_text += f"   Asistente: {exchange['response']}\n\n"
    
    body = f"""
Nuevo ticket de soporte creado:

ID: {ticket['ticket_id']}
Fecha: {ticket['timestamp']}
Prioridad: {ticket['priority'].upper()}
Razón: {ticket['reason']}
Información de contacto: {ticket['contact_info']}

Historial de la conversación:
{conversation_text}

Última consulta del usuario:
{ticket['query']}

Última respuesta del chatbot:
{ticket['last_response']}

Por favor, atiende este ticket lo antes posible.
"""
    
    # Crear mensaje de correo CON CODIFICACIÓN UTF-8
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    # Codificar el asunto en UTF-8 para evitar errores con caracteres especiales
    message["Subject"] = Header(subject, 'utf-8') 
    
    # Agregar cuerpo con codificación UTF-8
    message.attach(MIMEText(body, "plain", "utf-8"))
    
    # Enviar correo
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(sender_email, receiver_email, message.as_string())
        logger.info(f"📧 Notificación de soporte enviada a {receiver_email}")
    except Exception as e:
        logger.error(f"❌ Error al enviar notificación de soporte: {str(e)}")
        # Relanzar la excepción para que el llamador (create_support_ticket) la maneje si es necesario
        raise

def get_open_tickets():
    """Obtiene todos los tickets abiertos"""
    support_system = initialize_support_system()
    
    try:
        with open(support_system["tickets_file"], 'r') as f:
            tickets = json.load(f)
        
        return [t for t in tickets if t['status'] == 'abierto']
    except Exception as e:
        logger.error(f"❌ Error al obtener tickets abiertos: {str(e)}")
        return []

def close_ticket(ticket_id, resolution_notes=""):
    """Cierra un ticket de soporte"""
    support_system = initialize_support_system()
    
    try:
        with open(support_system["tickets_file"], 'r') as f:
            tickets = json.load(f)
        
        for ticket in tickets:
            if ticket['ticket_id'] == ticket_id:
                ticket['status'] = 'cerrado'
                ticket['resolution_timestamp'] = datetime.now().isoformat()
                ticket['resolution_notes'] = resolution_notes
                break
        
        with open(support_system["tickets_file"], 'w') as f:
            json.dump(tickets, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✅ Ticket cerrado: {ticket_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Error al cerrar ticket: {str(e)}")
        return False

# Para pruebas rápidas
if __name__ == "__main__":
    # Configurar logging para pruebas
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__) 
    
    print("="*50)
    print("🔄 Probando el sistema de soporte")
    print("="*50)
    
    # Crear un ticket de prueba
    test_ticket_id = create_support_ticket( # Recibir solo el ID
        query="¿Cómo puedo personalizar mis cestas de ratán?",
        response="Lo siento, no tengo información específica sobre personalización de cestas.",
        conversation_history=[
            {
                "timestamp": "2025-08-12T19:00:00",
                "query": "¿Tienen cestas de ratán para fermentar pan?",
                "response": "¡Sí! Tenemos excelentes opciones de cestas de ratán para fermentación de pan. 🍞"
            },
            {
                "timestamp": "2025-08-12T19:00:30",
                "query": "¿Puedo personalizarlas con mi logo?",
                "response": "No tengo información específica sobre personalización de cestas."
            }
        ],
        contact_info="usuario@example.com",
        priority="alta",
        reason="Consulta compleja fuera del alcance del chatbot"
    )
    
    print("\n✅ Ticket de prueba creado exitosamente")
    print(f"   ID del ticket: {test_ticket_id}") # Imprimir el ID devuelto
    print(f"   Prioridad: alta") # Imprimir prioridad usada
    
    # Listar tickets abiertos
    open_tickets = get_open_tickets()
    print(f"\nℹ️ Tickets abiertos: {len(open_tickets)}")
    
    # Cerrar el ticket de prueba (usando el ID devuelto)
    if close_ticket(test_ticket_id, "El cliente fue contactado y se le proporcionó información sobre personalización"):
        print(f"\n✅ Ticket {test_ticket_id} cerrado exitosamente")
    else:
        print(f"\n⚠️ No se pudo cerrar el ticket {test_ticket_id}")
    
    print("\n✅ Pruebas completadas exitosamente")

