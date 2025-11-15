from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    model_name: str = "htdemucs_6s"
    device: str = "auto"
    results_dir: str = "results"
    max_file_size_mb: int = 100
    
    class Config:
        env_file = ".env"

settings = Settings()