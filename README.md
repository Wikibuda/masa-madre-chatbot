```markdown
# 🥖 Sistema de Chatbot para Masa Madre Monterrey

Este repositorio contiene el sistema de chatbot para Masa Madre Monterrey, un asistente de panadería especializado en masa madre.

## 🌟 Tecnologías utilizadas

- **Python 3.11+**: Lenguaje principal
- **Flask**: API backend
- **Pinecone**: Búsqueda semántica
- **Claude (Anthropic)**: Generación de respuestas de alta calidad
- **Mistral**: Embeddings y procesamiento de texto
- **LangChain v0.3**: Framework para cadenas de LLM

## 📦 Estructura del Proyecto

```
masa-madre-chatbot/
├── api/                # Backend del chatbot
│   └── app.py          # Punto de entrada de la API
├── frontend/           # Widget de chat para el sitio web
│   ├── chat_widget.html # Widget principal
│   └── assets/         # Estilos y scripts
├── lib/                # Librerías compartidas
│   ├── conversation_history.py  # Gestión del historial
│   ├── feedback_system.py     # Sistema de retroalimentación
│   ├── semantic_search.py     # Búsqueda semántica
│   ├── shopify_api.py         # Integración con Shopify
│   └── support_system.py      # Soporte humano
├── .env.example        # Plantilla de variables de entorno
├── .gitignore
├── requirements.txt    # Dependencias
└── README.md           # Documentación
```

## ⚙️ Configuración

1. **Clona el repositorio**:
   ```bash
   git clone https://github.com/tu-usuario/masa-madre-chatbot.git
   cd masa-madre-chatbot
   ```

2. **Crea un entorno virtual**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # En Mac/Linux
   # venv\Scripts\activate   # En Windows
   ```

3. **Instala dependencias**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configura variables de entorno**:
   ```bash
   cp .env.example .env
   nano .env  # O tu editor preferido
   ```
   
   Completa con tus credenciales:
   ```
   PINECONE_API_KEY=tu_api_key_de_pinecone
   ANTHROPIC_API_KEY=tu_api_key_de_anthropic
   MISTRAL_API_KEY=tu_api_key_de_mistral
   ```

5. **Ejecuta la API**:
   ```bash
   python api/app.py
   ```

## 🌐 Despliegue en Render

1. Crea una cuenta en [Render](https://render.com)
2. Crea un nuevo "Web Service" conectado a tu repositorio de GitHub
3. Configura las variables de entorno en Render
4. Elige el plan gratuito para empezar

## 📞 Soporte

Para soporte técnico, contacta a tu equipo de desarrollo o abre un issue en este repositorio.
```
