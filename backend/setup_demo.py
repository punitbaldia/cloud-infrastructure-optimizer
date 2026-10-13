"""Create local configuration with a unique administrator password. Never overwrites .env."""
import secrets
from pathlib import Path
path=Path(__file__).resolve().parent/".env"
if not path.exists():
    password=secrets.token_urlsafe(18)
    path.write_text("AUTH_ENABLED=true\nADMIN_USERNAME=admin\nADMIN_PASSWORD="+password+
                    "\nCLOUD_MODE=mock\nADAPTER_MODULE=app.cloud.mock\nJOB_MODE=local\n",encoding="utf-8")
    print("Created backend/.env with a unique password. Read ADMIN_PASSWORD there to sign in.")
else:
    print("Existing backend/.env preserved. Ensure ADMIN_PASSWORD has at least 12 characters.")
