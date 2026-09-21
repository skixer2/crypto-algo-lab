import os
from dotenv import load_dotenv
load_dotenv('/home/node/.openclaw/ipcra_ws/.env')
load_dotenv(os.path.join(os.path.dirname(__file__), '.env.root'))

class Config:
    revolut_api_key = os.getenv('REVOLUT_API_KEY')
    revolut_api_secret = os.getenv('REVOLUT_PRIVATE_ED25519')
