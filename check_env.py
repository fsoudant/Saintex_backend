import os
from dotenv import load_dotenv
load_dotenv()
print(repr(os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS')))
