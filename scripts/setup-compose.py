import secrets
from pathlib import Path
path=Path(__file__).resolve().parents[1]/".env"
if not path.exists():
    path.write_text("POSTGRES_PASSWORD="+secrets.token_hex(24)+"\n",encoding="utf-8")
    print("Created root .env with a unique database password.")
else:
    print("Root .env preserved.")
