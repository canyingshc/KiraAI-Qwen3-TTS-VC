from core.provider import ModelType, BaseProvider
from .model_clients import DashscopeTTSClient


class DashscopeTTSProvider(BaseProvider):
    models = {
        ModelType.TTS: DashscopeTTSClient,
    }

    def __init__(self, provider_id, provider_name, provider_config):
        super().__init__(provider_id, provider_name, provider_config)