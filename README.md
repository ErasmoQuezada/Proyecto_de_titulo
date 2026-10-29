# HSBarber

Aplicacion web de gestion para una barberia, desarrollada con Django.

## Requisitos

- Python 3.10 o superior
- MySQL si se desea usar la configuracion de base de datos por defecto

## Instalacion local

No se versiona la carpeta `.venv`, porque los entornos virtuales contienen archivos especificos del sistema operativo y de la instalacion local. Para crearla despues de clonar el proyecto:

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Si PowerShell bloquea la activacion de scripts, puede ejecutarse:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Edita `.env` y agrega `GEMINI_API_KEY` si se utilizara el chatbot. La plantilla usa SQLite para facilitar el primer arranque local; para MySQL, cambia `DB_ENGINE` a `mysql` y completa las variables de conexion.

## Ejecutar el proyecto

Con el entorno virtual activado:

```bash
python manage.py migrate
python manage.py runserver
```

Luego abre <http://127.0.0.1:8000/>.

Para cargar los datos iniciales de HSBarber:

```bash
python manage.py seed_hsbarber
```