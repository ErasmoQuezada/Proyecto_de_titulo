import os
from dotenv import load_dotenv
from google import genai

# Cargar variables del archivo .env
load_dotenv()

# Obtener la API Key
api_key = os.getenv("GEMINI_API_KEY")

# Crear el cliente de Gemini
client = genai.Client(api_key=api_key)


def responder_gemini(mensaje):
    respuesta = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=mensaje
    )

    return respuesta.text