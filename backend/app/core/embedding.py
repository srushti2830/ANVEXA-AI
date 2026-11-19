from app.core.config import get_settings

_settings = get_settings()

EMBEDDING_MODEL = _settings.embedding_model
EMBEDDING_DIMENSION = _settings.embedding_dimension
