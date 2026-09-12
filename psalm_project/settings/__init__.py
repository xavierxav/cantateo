import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
# The .env file is located in the project root (3 levels up from this file)
env_path = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Default to development unless prod is explicitly requested.
django_env = os.environ.get('DJANGO_ENV', '').strip().lower()

if django_env in {'production', 'prod'}:
    from .production import *
else:
    from .development import *
