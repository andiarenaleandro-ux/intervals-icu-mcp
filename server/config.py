from dotenv import load_dotenv
import os

load_dotenv()

class Settings:
    athlete_id: str = os.getenv("INTERVALS_ATHLETE_ID", "")
    api_key: str = os.getenv("INTERVALS_API_KEY", "")
    fit_files_dir: str = os.getenv("FIT_FILES_DIR", "fit_files")
    base_url: str = "https://intervals.icu/api/v1"

    def auth(self) -> tuple[str, str]:
        return ("API_KEY", self.api_key)

    def validate(self):
        if not self.athlete_id or not self.api_key:
            raise ValueError(
                "Faltan variables de entorno: INTERVALS_ATHLETE_ID y/o INTERVALS_API_KEY. "
                "Copiá .env.example a .env y completá tus datos."
            )

settings = Settings()
