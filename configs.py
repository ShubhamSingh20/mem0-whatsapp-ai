import os
import dotenv

dotenv.load_dotenv()


postgres_db = os.getenv("POSTGRES_DB")
postgres_userName = os.getenv("POSTGRES_USER")
postgres_password = os.getenv("POSTGRES_PASSWORD")
postgres_url = os.getenv("POSTGRES_URL")
postgres_port = os.getenv("POSTGRES_PORT")

BUCKET_URL = os.getenv("BUCKET_URL")
BUCKET_NAME = os.getenv("BUCKET_NAME")
BUCKET_ACCESS_KEY = os.getenv('BUCKET_ACCESS_KEY')
BUCKET_SECRET_KEY = os.getenv('BUCKET_SECRET_KEY')

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

MEM0_API_KEY = os.getenv("MEM0_API_KEY")

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

REDIS_HOST = os.getenv('REDIS_HOST')
REDIS_PORT = int(os.getenv('REDIS_PORT', 14323))
REDIS_DB = int(os.getenv('REDIS_DB', 0))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD')
