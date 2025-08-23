# support_system_improved.py
import os
import json
import smtplib
import re
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from datetime import datetime
import logging
from dotenv import load_dotenv

# Configurar logging
logger = logging.getLogger(__name__)

class SupportSystem:
    def __init__(self):
        load_dotenv()
        self.tickets_file = "support_tickets.json"
        self.email_enabled = bool(os.getenv('SUPPORT_EMAIL_ENABLED', 'false').lower() == 'true')
        self.initialize_system()
        
    def initialize_system(self):
        """Inicializa el sistema de soporte"""
        if not os.path.exists(self.tickets_file):
            with open(self.tickets_file, 'w') as f:
                json.dump([], f)
            logger.info(f"✅ Archivo de tickets creado: {self.tickets_file}")
    
    def validate_contact_info(self, contact_info):
        """Valida la información de contacto"""
        errors = []
        
        # Validar nombre
        name = contact_info.get('name', '')
        if not name or len(name.strip()) < 2:
            errors.append("El nombre debe tener al menos 2 caracteres")
        elif len(name.strip()) > 100:
            errors.append("El nombre es demasiado largo")
            
        # Validar email
        email = contact_info.get('email', '')
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not email or not re.match(email_regex, email):
            errors.append("El formato del email no es válido")
            
        # Validar teléfono
        phone = contact_info.get('phone', '')
        cleaned_phone = re.sub(r'[\s\-\(\)]', '', phone)
        if not cleaned_phone or not cleaned_phone.isdigit():
            errors.append("El teléfono solo debe contener números")
        elif len(cleaned_phone) < 10:
            errors.append("El teléfono debe tener al menos 10 dígitos")
        elif len(cleaned_phone) > 15:
            errors.append("El teléfono es demasiado largo")
            
        return errors
    
    def create_support_ticket(self, query, response, conversation_history, contact_info, priority, reason):
        """Crea un ticket de soporte con validación"""
        # Validar información de contacto
        validation_errors = self.validate_contact_info(contact_info)
        if validation_errors:
            raise ValueError(f"Información de contacto inválida: {', '.join(validation_errors)}")
        
        # Generar ID del ticket
        ticket_id = f"TICKET-{int(datetime.now().timestamp())}"
        
        # Crear ticket
        ticket = {
            "ticket_id": ticket_id,
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "last_response": response,
            "conversation_history": self.sanitize_conversation_history(conversation_history),
            "contact_info": contact_info,
            "priority": priority,
            "reason": reason,
            "status": "abierto"
        }
        
        # Guardar ticket
        try:
            with open(self.tickets_file, 'r') as f:
                tickets = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            tickets = []
            
        tickets.append(ticket)
        
        with open(self.tickets_file, 'w', encoding='utf-8') as f:
            json.dump(tickets, f, indent=2, ensure_ascii=False)
            
        logger.info(f"✅ Ticket creado: {ticket_id}")
        
        # Enviar notificación por correo
        if self.email_enabled:
            try:
                self.send_support_notification(ticket)
            except Exception as e:
                logger.error(f"❌ Error al enviar notificación por correo: {str(e)}")
        
        return ticket_id
    
    def send_support_notification(self, ticket):
        """Envía notificaciones por correo al equipo y al cliente"""
        # Configuración
        sender_email = os.getenv('SUPPORT_EMAIL_SENDER')
        receiver_email = os.getenv('SUPPORT_EMAIL_RECIPIENT')
        smtp_server = os.getenv('SUPPORT_EMAIL_SMTP_SERVER')
        smtp_port = int(os.getenv('SUPPORT_EMAIL_SMTP_PORT', 587))
        smtp_user = os.getenv('SUPPORT_EMAIL_USER')
        smtp_password = os.getenv('SUPPORT_EMAIL_PASSWORD')
        
        if not all([sender_email, receiver_email, smtp_server, smtp_user, smtp_password]):
            raise ValueError("Configuración de correo incompleta")
        
        # Enviar correo al equipo de soporte
        self.send_email_to_team(ticket, sender_email, receiver_email, smtp_server, smtp_port, smtp_user, smtp_password)
        
        # Enviar correo de confirmación al cliente
        self.send_confirmation_to_client(ticket, sender_email, smtp_server, smtp_port, smtp_user, smtp_password)
    
    def send_email_to_team(self, ticket, sender, receiver, server, port, user, password):
        """Envía correo al equipo de soporte"""
        subject = f"🆕 NUEVO TICKET de soporte - {ticket['ticket_id']} - Prioridad: {ticket['priority'].upper()}"
        
        # Crear cuerpo del correo en HTML
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #8B4513;">Nuevo Ticket de Soporte</h2>
            
            <div style="background-color: #f9f9f9; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                <p><strong>ID del Ticket:</strong> {ticket['ticket_id']}</p>
                <p><strong>Fecha:</strong> {ticket['timestamp']}</p>
                <p><strong>Prioridad:</strong> <span style="color: {'#d9534f' if ticket['priority'] == 'alta' else '#f0ad4e' if ticket['priority'] == 'media' else '#5bc0de'}">{ticket['priority'].upper()}</span></p>
                <p><strong>Razón:</strong> {ticket['reason']}</p>
            </div>
            
            <div style="background-color: #fff8e1; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                <h3 style="color: #8B4513;">Información de Contacto</h3>
                <p><strong>Nombre:</strong> {ticket['contact_info']['name']}</p>
                <p><strong>Email:</strong> {ticket['contact_info']['email']}</p>
                <p><strong>Teléfono:</strong> {ticket['contact_info']['phone']}</p>
            </div>
            
            <div style="background-color: #e8f5e9; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                <h3 style="color: #8B4513;">Última Consulta</h3>
                <p>{ticket['query']}</p>
            </div>
            
            <div style="background-color: #e3f2fd; padding: 15px; border-radius: 5px;">
                <h3 style="color: #8B4513;">Última Respuesta del Chatbot</h3>
                <p>{ticket['last_response']}</p>
            </div>
            
            <p style="margin-top: 20px; font-size: 0.9em; color: #666;">
                Por favor, atiende este ticket lo antes posible.
            </p>
        </body>
        </html>
        """
        
        # Enviar correo
        self.send_email(sender, receiver, subject, html_content, server, port, user, password)
        logger.info(f"📧 Notificación enviada al equipo de soporte: {receiver}")
    
    def send_confirmation_to_client(self, ticket, sender, server, port, user, password):
        """Envía correo de confirmación al cliente"""
        client_email = ticket['contact_info']['email']
        subject = "✅ Confirmación de tu solicitud de soporte - Masa Madre Monterrey"
        
        # Crear cuerpo del correo en HTML
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #8B4513;">Hemos recibido tu solicitud</h2>
            
            <p>Gracias por contactar a Masa Madre Monterrey. Hemos recibido tu solicitud de soporte y nuestro equipo se pondrá en contacto contigo pronto.</p>
            
            <div style="background-color: #f9f9f9; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <h3 style="color: #8B4513; margin-top: 0;">Resumen de tu solicitud</h3>
                <p><strong>Número de ticket:</strong> {ticket['ticket_id']}</p>
                <p><strong>Fecha:</strong> {ticket['timestamp']}</p>
                <p><strong>Consulta:</strong> {ticket['query']}</p>
            </div>
            
            <p>Te contactaremos en un plazo máximo de 24 horas hábiles a través de {ticket['contact_info']['email']} o {ticket['contact_info']['phone']}.</p>
            
            <p style="margin-top: 30px; font-size: 0.9em; color: #666;">
                Si tienes alguna duda adicional, no dudes en responder este correo.
            </p>
            
            <p style="border-top: 1px solid #eee; padding-top: 20px; margin-top: 30px; font-size: 0.8em; color: #999;">
                Atentamente,<br>
                <strong>Equipo de Soporte - Masa Madre Monterrey</strong>
            </p>
        </body>
        </html>
        """
        
        # Enviar correo
        self.send_email(sender, client_email, subject, html_content, server, port, user, password)
        logger.info(f"📧 Confirmación enviada al cliente: {client_email}")
    
    def send_email(self, sender, receiver, subject, html_content, server, port, user, password):
        """Envía un correo HTML"""
        message = MIMEMultipart('alternative')
        message["From"] = sender
        message["To"] = receiver
        message["Subject"] = Header(subject, 'utf-8')
        
        # Crear versión HTML
        html_part = MIMEText(html_content, 'html', 'utf-8')
        message.attach(html_part)
        
        # Enviar correo
        with smtplib.SMTP(server, port) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.sendmail(sender, receiver, message.as_string())
    
    def sanitize_conversation_history(self, conversation_history):
        """Convierte el historial de conversación a formato serializable"""
        if not isinstance(conversation_history, list):
            return []
        
        serializable_history = []
        for exchange in conversation_history:
            safe_exchange = {}
            for key, value in exchange.items():
                if isinstance(value, (str, int, float, bool)) or value is None:
                    safe_exchange[key] = value
                elif isinstance(value, dict):
                    safe_exchange[key] = value.copy()
                elif isinstance(value, list):
                    safe_list = []
                    for item in value:
                        if isinstance(item, (str, int, float, bool)) or item is None:
                            safe_list.append(item)
                        elif isinstance(item, dict):
                            safe_list.append(item.copy())
                        else:
                            safe_list.append(str(item))
                    safe_exchange[key] = safe_list
                else:
                    safe_exchange[key] = str(value)
            serializable_history.append(safe_exchange)
        
        return serializable_history

# Para mantener compatibilidad con el código existente
def create_support_ticket(query, response, conversation_history, contact_info, priority, reason):
    """Función wrapper para mantener compatibilidad"""
    support_system = SupportSystem()
    return support_system.create_support_ticket(query, response, conversation_history, contact_info, priority, reason)
